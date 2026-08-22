"""Service probe engine: HTTP/TCP/Ping/DNS uptime checks with alert push.

Answers the question Uptime Kuma-style external monitors ask:
"can users actually reach this service?" — complementing the internal
metrics (CPU/mem/disk) that agents already report.
"""
import asyncio
import logging
import socket
import time
import urllib.error
import urllib.request

from app.core.database import get_db
from app.services.alerts import _notify

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 5           # loop sweep seconds
PROBE_COOLDOWN = 1800        # alert cooldown per rule (30 min)
RECOVERY_WINDOW = 6 * 3600   # send "recovered" if a failure fired within 6h
MAX_RESULTS_PER_RULE = 500   # keep last N results per rule

# Latest state per rule (in-memory, for fast API reads)
state: dict[int, dict] = {}


# ── Probe implementations ─────────────────────────────────────────
def _probe_http_sync(target: str, timeout: int, expected: str) -> dict:
    """HTTP(S) check: status code + optional keyword + latency (blocking, run in thread)."""
    t0 = time.monotonic()
    result = {"ok": False, "latency_ms": None, "status_code": None, "message": ""}
    try:
        req = urllib.request.Request(target, headers={
            "User-Agent": "Mozilla/5.0 (ServerMonitor Probe)",
            "Accept": "*/*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", "replace")
            result["status_code"] = resp.status
            if expected and expected not in body:
                result["message"] = f"HTTP {resp.status} · 关键词「{expected}」未匹配"
            else:
                result["ok"] = True
                result["message"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["message"] = f"HTTP {e.code}"
    except Exception as e:
        result["message"] = str(e)[:120]
    result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    if result["ok"]:
        result["message"] += f" · {result['latency_ms']}ms"
    return result


async def _probe_tcp(target: str, timeout: int) -> dict:
    host, _, port = target.rpartition(":")
    if not port or not host:
        return {"ok": False, "latency_ms": None, "status_code": None, "message": "目标格式应为 host:port"}
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        latency = round((time.monotonic() - t0) * 1000, 1)
        return {"ok": True, "latency_ms": latency, "status_code": None, "message": f"TCP 连接成功 · {latency}ms"}
    except Exception as e:
        latency = round((time.monotonic() - t0) * 1000, 1)
        return {"ok": False, "latency_ms": latency, "status_code": None, "message": str(e)[:120]}


async def _probe_ping(target: str, timeout: int) -> dict:
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(max(1, timeout - 1)), target,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await asyncio.wait_for(proc.wait(), timeout=timeout + 2)
        latency = round((time.monotonic() - t0) * 1000, 1)
        if rc == 0:
            return {"ok": True, "latency_ms": latency, "status_code": None, "message": f"Ping 可达 · {latency}ms"}
        return {"ok": False, "latency_ms": latency, "status_code": None, "message": "Ping 无响应"}
    except asyncio.TimeoutError:
        return {"ok": False, "latency_ms": None, "status_code": None, "message": "Ping 超时"}
    except Exception as e:
        return {"ok": False, "latency_ms": None, "status_code": None, "message": str(e)[:120]}


async def _probe_dns(target: str, timeout: int) -> dict:
    loop = asyncio.get_event_loop()
    t0 = time.monotonic()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(target, None, type=socket.SOCK_STREAM), timeout=timeout
        )
        latency = round((time.monotonic() - t0) * 1000, 1)
        ips = sorted({str(i[4][0]) for i in infos})
        return {"ok": True, "latency_ms": latency, "status_code": None,
                "message": f"解析成功 · {latency}ms · {','.join(ips[:3])}"}
    except Exception as e:
        latency = round((time.monotonic() - t0) * 1000, 1)
        return {"ok": False, "latency_ms": latency, "status_code": None, "message": f"解析失败 · {str(e)[:80]}"}


def _probe_ssl_sync(target: str, timeout: int) -> dict:
    """TLS certificate check: handshake to target:443, report days_left.

    Target may be a bare domain ("dfshmily.icu") or domain:port.
    ok=True while the certificate is valid AND has more than 15 days left,
    so approaching-expiry turns the probe red before things break.
    """
    import ssl as _ssl
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit():
        host, port = target, "443"
    t0 = time.monotonic()
    result = {"ok": False, "latency_ms": None, "status_code": None, "message": "", "days_left": None}
    try:
        ctx = _ssl.create_default_context()
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                raw = tls.getpeercert()
        cert = dict(raw) if isinstance(raw, dict) else {}
        not_after_raw = cert.get("notAfter")
        if not isinstance(not_after_raw, str):
            result["message"] = "证书数据异常"
            return result
        not_after = _ssl.cert_time_to_seconds(not_after_raw)
        issuer_tuples = cert.get("issuer") or []
        issuer = ""
        for part in issuer_tuples:
            if isinstance(part, tuple) and part and part[0] == "organizationName":
                issuer = str(part[1])
                break
        days_left = int((not_after - time.time()) / 86400)
        result["days_left"] = days_left
        result["ok"] = days_left > 15
        if days_left <= 15:
            result["message"] = f"证书即将到期：仅剩 {days_left} 天（签发 {issuer or '未知'}）"
        else:
            result["message"] = f"证书有效 · 剩 {days_left} 天（{issuer or '未知'} 签发）"
    except Exception as e:
        result["message"] = f"证书检查失败 · {str(e)[:100]}"
    result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return result


async def _probe_ssl(target: str, timeout: int) -> dict:
    return await asyncio.to_thread(_probe_ssl_sync, target, timeout)


async def _run_probe(rule) -> dict:
    t = rule["type"]
    if t == "http":
        return await asyncio.to_thread(_probe_http_sync, rule["target"], rule["timeout"], rule["expected"])
    if t == "tcp":
        return await _probe_tcp(rule["target"], rule["timeout"])
    if t == "ping":
        return await _probe_ping(rule["target"], rule["timeout"])
    if t == "dns":
        return await _probe_dns(rule["target"], rule["timeout"])
    if t == "ssl":
        return await _probe_ssl(rule["target"], rule["timeout"])
    return {"ok": False, "latency_ms": None, "status_code": None, "message": f"未知探测类型 {t}"}


# ── Alert events (reuse alert_events table so admin history shows them) ──
async def _probe_event(rule_id: int, kind: str, within: int) -> bool:
    db = await get_db()
    cur = await db.execute(
        "SELECT id FROM alert_events WHERE metric = 'probe' AND kind = ? AND rule_id = ? AND created_at > ? LIMIT 1",
        (kind, rule_id, int(time.time()) - within),
    )
    return await cur.fetchone() is not None


async def _record_probe_event(rule_id: int, rule_name: str, result: dict, kind: str, message: str):
    db = await get_db()
    await db.execute(
        "INSERT INTO alert_events (rule_id, server_name, metric, value, message, kind, created_at) VALUES (?,?,?,?,?,?,?)",
        (rule_id, rule_name, "probe", result.get("latency_ms") or 0, message, kind, int(time.time())),
    )
    await db.commit()


# ── Main loop ─────────────────────────────────────────────────────
async def probe_loop() -> None:
    """Background sweep: run each enabled rule on its interval, alert on state change."""
    last_run: dict[int, float] = {}
    while True:
        try:
            db = await get_db()
            cur = await db.execute("SELECT * FROM probe_rules WHERE enabled = 1")
            rules = await cur.fetchall()
            now = time.time()
            for rule in rules:
                rule_id = rule["id"]
                if now - last_run.get(rule_id, 0) < rule["interval"]:
                    continue
                last_run[rule_id] = now
                try:
                    result = await _run_probe(rule)
                except Exception as e:
                    result = {"ok": False, "latency_ms": None, "status_code": None,
                              "message": f"探测异常: {str(e)[:100]}"}

                await db.execute(
                    "INSERT INTO probe_results (rule_id, ok, latency_ms, status_code, message, created_at) VALUES (?,?,?,?,?,?)",
                    (rule_id, int(result["ok"]), result.get("latency_ms"),
                     result.get("status_code"), result.get("message", ""), int(now)),
                )
                await db.execute(
                    "DELETE FROM probe_results WHERE rule_id = ? AND id NOT IN "
                    "(SELECT id FROM probe_results WHERE rule_id = ? ORDER BY id DESC LIMIT ?)",
                    (rule_id, rule_id, MAX_RESULTS_PER_RULE),
                )
                await db.commit()

                prev_ok = state.get(rule_id, {}).get("ok")
                state[rule_id] = {
                    "rule_id": rule_id,
                    "name": rule["name"],
                    "type": rule["type"],
                    "target": rule["target"],
                    **result,
                    "ts": int(now),
                }

                # Alert on failure (cooldown); recovery when a failure happened recently
                if not result["ok"]:
                    if not await _probe_event(rule_id, "probe_down", PROBE_COOLDOWN):
                        msg = (f"🔴 服务不可达 [{rule['name']}] {rule['type']} {rule['target']}："
                               f"{result.get('message', '')}")
                        await _record_probe_event(rule_id, rule["name"], result, "probe_down", msg)
                        await _notify(msg)
                else:
                    if prev_ok is False or await _probe_event(rule_id, "probe_down", RECOVERY_WINDOW):
                        if not await _probe_event(rule_id, "probe_recovered", PROBE_COOLDOWN):
                            msg = (f"✅ 服务已恢复 [{rule['name']}] {rule['type']} {rule['target']}："
                                   f"{result.get('message', '')}")
                            await _record_probe_event(rule_id, rule["name"], result, "probe_recovered", msg)
                            await _notify(msg)
        except Exception as e:
            logger.warning("probe loop error: %s", e)
        await asyncio.sleep(CHECK_INTERVAL)
