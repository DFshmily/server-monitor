"""Alert engine: threshold rules, offline detection, Telegram push."""
import json
import logging
import time
import urllib.request
import urllib.error

from app.core.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from app.core.database import get_db

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────
CHECK_INTERVAL = 15          # seconds between alert sweeps
COOLDOWN_SECONDS = 1800      # don't re-alert same rule+server for 30 min
OFFLINE_AFTER_SECONDS = 90   # no data for 90s => server offline
OFFLINE_COOLDOWN_SECONDS = 600

# Metric path -> (extractor fn, unit label)
def _extract_metric(data: dict, metric: str):
    """Return (value, unit_label) for a supported metric, or None."""
    try:
        if metric == "cpu":
            return data.get("cpu", {}).get("percent"), "%"
        if metric == "memory":
            return data.get("memory", {}).get("percent"), "%"
        if metric == "disk":
            parts = data.get("disk", {}).get("partitions") or []
            root = next((p for p in parts if p.get("mountpoint") == "/"), parts[0] if parts else None)
            if root is None:
                return None, None
            return root.get("percent"), "%"
        if metric == "load1":
            return data.get("load", {}).get("load1"), ""
        if metric == "load5":
            return data.get("load", {}).get("load5"), ""
        if metric == "load15":
            return data.get("load", {}).get("load15"), ""
        if metric == "net_in":
            nd = data.get("network", {})
            if "bytes_recv_rate" in nd:
                return nd.get("bytes_recv_rate"), "B/s"
            return None, None
        if metric == "net_out":
            nd = data.get("network", {})
            if "bytes_sent_rate" in nd:
                return nd.get("bytes_sent_rate"), "B/s"
            return None, None
    except Exception:
        return None, None
    return None, None


def _compare(value: float, op: str, threshold: float) -> bool:
    try:
        if op == ">":
            return value > threshold
        if op == ">=":
            return value >= threshold
        if op == "<":
            return value < threshold
        if op == "<=":
            return value <= threshold
    except TypeError:
        return False
    return False


def _fmt_bytes(n) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


async def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning("Telegram push failed: %s", e)
        return False


async def _recent_event(server: str, metric: str, kind: str, within: int) -> bool:
    """True if a same-kind event exists for this server+metric within `within` seconds."""
    db = await get_db()
    cur = await db.execute(
        "SELECT id FROM alert_events WHERE server_name = ? AND metric = ? AND kind = ? AND created_at > ? LIMIT 1",
        (server, metric, kind, int(time.time()) - within),
    )
    return await cur.fetchone() is not None


async def _record_event(rule_id, server, metric, value, message, kind="threshold"):
    db = await get_db()
    await db.execute(
        "INSERT INTO alert_events (rule_id, server_name, metric, value, message, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rule_id, server, metric, value, message, kind, int(time.time())),
    )
    await db.commit()


async def check_threshold_rules() -> None:
    """Evaluate all enabled rules against each server's latest metrics."""
    db = await get_db()
    cur = await db.execute("SELECT * FROM alert_rules WHERE enabled = 1")
    rules = await cur.fetchall()

    # Latest timestamp per server
    cur = await db.execute(
        "SELECT server_name, MAX(timestamp) as ts FROM metrics_raw GROUP BY server_name"
    )
    latest_ts = {r["server_name"]: r["ts"] for r in await cur.fetchall()}

    for rule in rules:
        targets = []
        if rule["server_name"] == "*":
            targets = list(latest_ts.keys())
        else:
            targets = [rule["server_name"]]

        for server in targets:
            # skip stale servers (offline check handles them)
            if server not in latest_ts or latest_ts[server] < int(time.time()) - OFFLINE_AFTER_SECONDS:
                continue
            cur = await db.execute(
                "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1",
                (server,),
            )
            row = await cur.fetchone()
            if not row:
                continue
            data = json.loads(row["data"])
            value, unit = _extract_metric(data, rule["metric"])
            if value is None:
                continue
            if _compare(value, rule["operator"], rule["threshold"]):
                if await _recent_event(server, rule["metric"], "threshold", COOLDOWN_SECONDS):
                    continue
                msg = (f"🚨 告警 [{server}] {rule['metric']} {rule['operator']} {rule['threshold']}{unit}，"
                       f"当前 {value:.2f}{unit}")
                await _record_event(rule["id"], server, rule["metric"], value, msg, "threshold")
                await _send_telegram(msg)


async def check_offline() -> None:
    """Detect servers that stopped reporting (heartbeat timeout)."""
    db = await get_db()
    now = int(time.time())
    cur = await db.execute(
        "SELECT server_name, MAX(timestamp) as ts FROM metrics_raw GROUP BY server_name"
    )
    for row in await cur.fetchall():
        server, ts = row["server_name"], row["ts"]
        if now - ts <= OFFLINE_AFTER_SECONDS:
            continue
        if await _recent_event(server, "heartbeat", "offline", OFFLINE_COOLDOWN_SECONDS):
            continue
        msg = f"⚠️ 服务器离线 [{server}]：已 {now - ts} 秒无数据上报，可能宕机或网络中断"
        await _record_event(None, server, "heartbeat", float(now - ts), msg, "offline")
        await _send_telegram(msg)


async def alert_loop() -> None:
    """Background sweep: threshold rules + offline detection every CHECK_INTERVAL."""
    while True:
        try:
            await check_threshold_rules()
            await check_offline()
        except Exception as e:
            logger.warning("alert loop error: %s", e)
        await asyncio_sleep(CHECK_INTERVAL)


# tiny alias to keep import light
import asyncio
asyncio_sleep = asyncio.sleep
