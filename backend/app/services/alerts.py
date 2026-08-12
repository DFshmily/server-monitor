"""Alert engine: threshold rules, offline detection, Telegram/Bark push."""
import json
import logging
import time
import urllib.request
import urllib.error
import urllib.parse

from app.core.config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    BARK_KEY,
    BARK_GROUP,
    TRAFFIC_QUOTA_GB,
)
from app.core.database import get_db

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────
CHECK_INTERVAL = 15          # seconds between alert sweeps
COOLDOWN_SECONDS = 1800      # don't re-alert same rule+server for 30 min
OFFLINE_AFTER_SECONDS = 120  # no data for 120s => server offline
OFFLINE_COOLDOWN_SECONDS = 600
RECOVERY_WINDOW = 6 * 3600   # only send "recovered" if it fired within 6h

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
        if metric == "cert_days":
            # certificates: {domain: {days_left, issuer, ...}} -> min days
            certs = data.get("certificates") or {}
            days = [c.get("days_left") for c in certs.values() if c.get("days_left") is not None]
            if not days:
                return None, None
            return min(days), "天"
        if metric == "traffic_month_total_gb":
            tm = data.get("traffic_month") or {}
            total = tm.get("total_bytes", 0)
            if not total:
                return None, None
            return round(total / (1024 ** 3), 2), "GB"
        if metric == "traffic_used_percent":
            tm = data.get("traffic_month") or {}
            # 优先用 agent 按本机配额算好的百分比(每服务器可独立配置配额)
            if tm.get("used_percent") is not None:
                return tm.get("used_percent"), "%"
            # 回退: 后端全局配额(旧配置兼容)
            if TRAFFIC_QUOTA_GB <= 0:
                return None, None
            total = tm.get("total_bytes", 0)
            if not total:
                return None, None
            return round(total / (1024 ** 3) / TRAFFIC_QUOTA_GB * 100, 2), "%"
        if metric.startswith("custom:"):
            # 自定义监控项: metric 格式 "custom:项名称"
            item = metric.split(":", 1)[1]
            c = (data.get("custom") or {}).get(item)
            if c and c.get("ok") and c.get("value") is not None:
                return c["value"], c.get("unit") or ""
            return None, None
        if metric == "apt_updates":
            au = data.get("apt_updates") or {}
            if au.get("ok"):
                return au.get("count", 0), "个"
            return None, None
    except Exception:
        return None, None
    return None, None


def _cert_weakest(data: dict):
    """Return (domain, days_left) of the certificate expiring soonest, or None."""
    certs = data.get("certificates") or {}
    best = None
    for domain, c in certs.items():
        dl = c.get("days_left")
        if dl is None:
            continue
        if best is None or dl < best[1]:
            best = (domain, dl)
    return best


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


async def _send_bark(text: str) -> bool:
    """Push to Bark (iOS). Uses the official push endpoint; falls back to GET."""
    if not BARK_KEY:
        return False
    # Split title/body on the first '：' or ':' so the notification headline is short
    title, _, body = text.partition("：")
    if not body:
        title, _, body = text.partition(":")
    title = (title or "监控告警")[:30]
    payload = {
        "device_key": BARK_KEY,
        "title": title,
        "body": text[:2000],
        "level": "timeSensitive",
        "icon": "https://dashboard.dfshmily.icu/favicon.ico",
    }
    if BARK_GROUP:
        payload["group"] = BARK_GROUP
    try:
        req = urllib.request.Request(
            "https://api.day.app/push",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
            try:
                rj = json.loads(resp.read().decode() or "{}")
                if rj.get("code") not in (None, 200):
                    logger.warning("Bark push rejected: %s", rj)
                    return False
            except Exception:
                pass
            return code == 200
    except Exception as e:
        logger.warning("Bark push failed: %s", e)
        return False


async def _notify(text: str) -> dict:
    """Send to every configured channel. Returns {channel: ok}."""
    results = {}
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        results["telegram"] = await _send_telegram(text)
    if BARK_KEY:
        results["bark"] = await _send_bark(text)
    if not results:
        logger.info("No notification channel configured, alert not pushed: %s", text[:80])
    return results


async def _in_maintenance(server: str) -> bool:
    """True if `server` is inside an active maintenance window ('*' matches all)."""
    db = await get_db()
    now = int(time.time())
    cur = await db.execute(
        "SELECT id FROM maintenance_windows WHERE start_at <= ? AND end_at >= ? "
        "AND (server_name = '*' OR server_name = ?) LIMIT 1",
        (now, now, server),
    )
    return await cur.fetchone() is not None


async def _recent_event(server: str, metric: str, kind: str, within: int, rule_id: int | None = None) -> bool:
    """True if a same-kind event exists for this server+metric within `within` seconds.

    When rule_id is given, only events of that rule count (recovery must pair
    with the exact rule that fired, not any rule on the same metric).
    """
    db = await get_db()
    sql = "SELECT id FROM alert_events WHERE server_name = ? AND metric = ? AND kind = ? AND created_at > ?"
    params: list = [server, metric, kind, int(time.time()) - within]
    if rule_id is not None:
        sql += " AND rule_id = ?"
        params.append(rule_id)
    sql += " LIMIT 1"
    cur = await db.execute(sql, params)
    return await cur.fetchone() is not None


async def _last_event_kind(server: str, metric: str, kinds: tuple, rule_id: int | None = None) -> str | None:
    """Latest event kind for server+metric among `kinds` (state-machine recovery)."""
    db = await get_db()
    sql = ("SELECT kind FROM alert_events WHERE server_name = ? AND metric = ? "
           f"AND kind IN ({','.join('?' * len(kinds))})")
    params: list = [server, metric, *kinds]
    if rule_id is not None:
        sql += " AND rule_id = ?"
        params.append(rule_id)
    sql += " ORDER BY id DESC LIMIT 1"
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    return row["kind"] if row else None


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
            now = int(time.time())
            if _compare(value, rule["operator"], rule["threshold"]):
                if await _recent_event(server, rule["metric"], "threshold", COOLDOWN_SECONDS):
                    continue
                # Cert alert message: name the weakest domain
                extra = ""
                if rule["metric"] == "cert_days":
                    weakest = _cert_weakest(data)
                    if weakest:
                        extra = f"（最先到期: {weakest[0]}，剩 {weakest[1]} 天）"
                msg = (f"🚨 告警 [{server}] {rule['metric']} {rule['operator']} {rule['threshold']}{unit}，"
                       f"当前 {value:.2f}{unit}{extra}")
                await _record_event(rule["id"], server, rule["metric"], value, msg, "threshold")
                if not await _in_maintenance(server):
                    await _notify(msg)
            else:
                # ── Recovery: 该规则最近一次事件是 threshold(已触发)且现已恢复 ──
                last_kind = await _last_event_kind(server, rule["metric"], ("threshold", "recovered"), rule_id=rule["id"])
                if last_kind != "threshold":
                    continue
                if not await _recent_event(server, rule["metric"], "threshold", RECOVERY_WINDOW, rule_id=rule["id"]):
                    continue
                msg = (f"✅ 已恢复 [{server}] {rule['metric']}："
                       f"{value:.2f}{unit}，不再满足 {rule['operator']} {rule['threshold']}{unit}")
                await _record_event(rule["id"], server, rule["metric"], value, msg, "recovered")
                if not await _in_maintenance(server):
                    await _notify(msg)


async def check_offline() -> None:
    """Detect servers that stopped reporting (heartbeat timeout) + recovery."""
    db = await get_db()
    now = int(time.time())
    cur = await db.execute(
        "SELECT server_name, MAX(timestamp) as ts FROM metrics_raw GROUP BY server_name"
    )
    for row in await cur.fetchall():
        server, ts = row["server_name"], row["ts"]
        if now - ts > OFFLINE_AFTER_SECONDS:
            if await _recent_event(server, "heartbeat", "offline", OFFLINE_COOLDOWN_SECONDS):
                continue
            msg = f"⚠️ 服务器离线 [{server}]：已 {now - ts} 秒无数据上报，可能宕机或网络中断"
            await _record_event(None, server, "heartbeat", float(now - ts), msg, "offline")
            if not await _in_maintenance(server):
                await _notify(msg)
        else:
            # ── 离线恢复: 最近一条 heartbeat 事件是 offline 且数据已恢复 → 发恢复 ──
            last_kind = await _last_event_kind(server, "heartbeat", ("offline", "recovered"))
            if last_kind != "offline":
                continue
            msg = f"✅ 服务器已恢复上线 [{server}]：数据恢复正常上报"
            await _record_event(None, server, "heartbeat", 0.0, msg, "recovered")
            if not await _in_maintenance(server):
                await _notify(msg)


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
