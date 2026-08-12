"""Background aggregation service.

Aggregates raw metrics into time-bucketed averages and cleans up old data.
"""
import asyncio
import json
import logging
import time
from app.core.config import RETENTION_REALTIME, RETENTION_1MIN, RETENTION_5MIN, RETENTION_1H, RETENTION_1D
from app.core.database import get_db

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = {
    "1min": 60,
    "5min": 300,
    "1h": 3600,
    "1d": 86400,
}

RETENTION_DAYS = {
    "1min": RETENTION_1MIN,
    "5min": RETENTION_5MIN,
    "1h": RETENTION_1H,
    "1d": RETENTION_1D,
}


def _get_nested(obj: dict, *keys, default=0):
    """Safely get nested dict value."""
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k, None)
            if obj is None:
                return default
        else:
            return default
    return obj


async def _aggregate_interval(interval: str, window: int) -> None:
    """Aggregate raw data into the given interval bucket."""
    db = await get_db()
    now = int(time.time())
    bucket_start = now - window

    # Find distinct servers with recent raw data
    cursor = await db.execute(
        "SELECT DISTINCT server_name FROM metrics_raw WHERE timestamp >= ?",
        (bucket_start,),
    )
    servers = [r["server_name"] for r in await cursor.fetchall()]

    for server in servers:
        cursor = await db.execute(
            "SELECT data FROM metrics_raw WHERE server_name = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (server, bucket_start, now),
        )
        rows = await cursor.fetchall()
        if not rows:
            continue

        records = [json.loads(r["data"]) for r in rows]

        def avg(*keys):
            vals = []
            for rec in records:
                v = _get_nested(rec, *keys)
                if isinstance(v, (int, float)):
                    vals.append(v)
            return sum(vals) / len(vals) if vals else 0.0

        # Get disk percent from first partition with mountpoint '/'
        def get_disk_percent(rec):
            partitions = _get_nested(rec, "disk", "partitions", default=[])
            if isinstance(partitions, list):
                for p in partitions:
                    if isinstance(p, dict) and p.get("mountpoint") == "/":
                        return p.get("percent", 0)
                if partitions:
                    return partitions[0].get("percent", 0) if isinstance(partitions[0], dict) else 0
            return 0

        # Get total network bytes from all interfaces
        def get_net_total(rec, direction):
            interfaces = _get_nested(rec, "network", "interfaces", default={})
            if isinstance(interfaces, dict):
                key = "bytes_recv" if direction == "recv" else "bytes_sent"
                return sum(v.get(key, 0) for v in interfaces.values() if isinstance(v, dict))
            return 0

        # Get network rates (agent-computed)
        def get_net_rate(rec, direction):
            key = "total_recv_rate" if direction == "recv" else "total_sent_rate"
            v = _get_nested(rec, "network", key, default=0)
            return v if isinstance(v, (int, float)) else 0

        # Persistent lifetime counters (monotonic, survive reboots)
        def get_lifetime(rec, direction):
            key = "lifetime_bytes_recv" if direction == "recv" else "lifetime_bytes_sent"
            v = _get_nested(rec, "network", key, default=0)
            return v if isinstance(v, (int, float)) else 0

        disk_percents = [get_disk_percent(rec) for rec in records]
        net_recv_vals = [get_net_total(rec, "recv") for rec in records]
        net_sent_vals = [get_net_total(rec, "sent") for rec in records]

        # Compute network rate (bytes per second between samples)
        net_in_rate = 0
        net_out_rate = 0
        if len(net_recv_vals) >= 2:
            net_in_rate = max(0, (net_recv_vals[-1] - net_recv_vals[0]) / max(1, len(net_recv_vals) - 1))
            net_out_rate = max(0, (net_sent_vals[-1] - net_sent_vals[0]) / max(1, len(net_sent_vals) - 1))

        agg = {
            "cpu": {
                "percent": round(avg("cpu", "percent"), 2),
                "iowait": round(avg("cpu", "iowait"), 2),
                "steal": round(avg("cpu", "steal"), 2),
                "user": round(avg("cpu", "user"), 2),
                "system": round(avg("cpu", "system"), 2),
            },
            "memory": {
                "percent": round(avg("memory", "percent"), 2),
                "used": int(avg("memory", "used")),
                "total": int(avg("memory", "total")),
            },
            "disk": {
                "percent": round(sum(disk_percents) / len(disk_percents), 2) if disk_percents else 0,
                "partitions": [{"mountpoint": "/", "percent": round(sum(disk_percents) / len(disk_percents), 2)}],
                "io": {
                    "read_bytes": int(avg("disk", "io", "read_bytes")),
                    "write_bytes": int(avg("disk", "io", "write_bytes")),
                },
            },
            "network": {
                "bytes_recv_rate": int(net_in_rate),
                "bytes_sent_rate": int(net_out_rate),
                "total_recv_rate": int(sum(get_net_rate(rec, "recv") for rec in records) / len(records)),
                "total_sent_rate": int(sum(get_net_rate(rec, "sent") for rec in records) / len(records)),
                "total_bytes_recv": int(net_recv_vals[-1]) if net_recv_vals else 0,
                "total_bytes_sent": int(net_sent_vals[-1]) if net_sent_vals else 0,
                "bytes_recv_total": int(net_recv_vals[-1]) if net_recv_vals else 0,
                "bytes_sent_total": int(net_sent_vals[-1]) if net_sent_vals else 0,
                "lifetime_bytes_recv": int(max(get_lifetime(rec, "recv") for rec in records)) if records else 0,
                "lifetime_bytes_sent": int(max(get_lifetime(rec, "sent") for rec in records)) if records else 0,
                "interfaces": _get_nested(records[-1], "network", "interfaces", default={}) if records else {},
            },
            "load": {
                "load1": round(avg("load", "load1"), 2),
                "load5": round(avg("load", "load5"), 2),
                "load15": round(avg("load", "load15"), 2),
            },
            "samples": len(records),
        }

        await db.execute(
            "INSERT INTO metrics_agg (server_name, timestamp, interval, data) VALUES (?, ?, ?, ?)",
            (server, bucket_start, interval, json.dumps(agg)),
        )

    await db.commit()


async def _cleanup_old_data() -> None:
    """Delete data older than retention limits."""
    db = await get_db()
    now = int(time.time())

    cutoff_raw = now - RETENTION_REALTIME * 86400
    await db.execute("DELETE FROM metrics_raw WHERE timestamp < ?", (cutoff_raw,))

    for interval, days in RETENTION_DAYS.items():
        cutoff = now - days * 86400
        await db.execute(
            "DELETE FROM metrics_agg WHERE interval = ? AND timestamp < ?",
            (interval, cutoff),
        )
    await db.commit()
    logger.info("Cleanup completed")


async def aggregator_loop() -> None:
    """Main aggregation loop, runs every 60 seconds."""
    await asyncio.sleep(5)
    while True:
        try:
            now = int(time.time())
            await _aggregate_interval("1min", INTERVAL_SECONDS["1min"])

            if now % 300 < 60:
                await _aggregate_interval("5min", INTERVAL_SECONDS["5min"])

            if now % 3600 < 60:
                await _aggregate_interval("1h", INTERVAL_SECONDS["1h"])

            if now % 86400 < 60:
                await _aggregate_interval("1d", INTERVAL_SECONDS["1d"])

            if now % 3600 < 60:
                await _cleanup_old_data()

        except Exception:
            logger.exception("Aggregation error")

        await asyncio.sleep(60)
