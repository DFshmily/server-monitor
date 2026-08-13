"""Heartbeat check engine (Healthchecks.io style): monitor cron jobs / scheduled tasks.

任务按时 curl 心跳 URL → 后端记录 last_ping；超过 interval+grace 未收到 → 告警。
"""
import asyncio
import logging
import time

from app.core.database import get_db
from app.services.alerts import _notify, _in_maintenance

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 30          # 扫描周期(秒)
ALERT_COOLDOWN = 6 * 3600    # 同任务超时告警冷却(6h)
RECOVERY_WINDOW = 6 * 3600

# 内存态: {check_id: {"status": "ok"|"missed"}}
_state: dict[int, dict] = {}


def heartbeat_status(check: dict, now: int | None = None) -> str:
    """状态: ok(正常) / late(即将超时) / missed(已超时) / new(从未收到)。"""
    now = now or int(time.time())
    if not check["last_ping"]:
        # 从未收到心跳: 创建超过 interval+grace 才报 missed
        if now - check["created_at"] > check["interval"] + check["grace"]:
            return "missed"
        return "new"
    if now - check["last_ping"] > check["interval"] + check["grace"]:
        return "missed"
    if now - check["last_ping"] > check["interval"]:
        return "late"
    return "ok"


async def record_ping(slug: str) -> bool:
    """收到一次心跳。返回 False 表示 slug 不存在。

    注意：不直接改内存状态——状态迁移(missed→ok 恢复通知)由 check_heartbeats 扫描驱动。
    """
    db = await get_db()
    now = int(time.time())
    cur = await db.execute("SELECT * FROM heartbeat_checks WHERE slug = ?", (slug,))
    check = await cur.fetchone()
    if not check:
        return False
    await db.execute(
        "UPDATE heartbeat_checks SET last_ping = ?, last_ping_success = 1 WHERE id = ?",
        (now, check["id"]),
    )
    await db.commit()
    return True


async def check_heartbeats() -> None:
    """扫描所有启用的心跳项：超时告警 + 恢复通知。"""
    db = await get_db()
    now = int(time.time())
    cur = await db.execute("SELECT * FROM heartbeat_checks WHERE enabled = 1")
    checks = await cur.fetchall()

    for check in checks:
        cid = check["id"]
        st = heartbeat_status(check, now)
        prev = _state.get(cid, {}).get("status", "ok")

        if st == "missed":
            _state[cid] = {"status": "missed", "missed_at": now}
            # 告警(冷却去重): 上次告警在 6h 内则跳过
            cur = await db.execute(
                "SELECT id FROM alert_events WHERE metric = 'heartbeat' AND server_name = ? "
                "AND kind = 'heartbeat_missed' AND created_at > ? LIMIT 1",
                (check["name"], now - ALERT_COOLDOWN),
            )
            if not await cur.fetchone():
                wait = now - check["last_ping"] if check["last_ping"] else now - check["created_at"]
                msg = (f"💔 任务心跳丢失 [{check['name']}]：已 {wait // 3600} 小时 "
                       f"{wait % 3600 // 60} 分钟未收到心跳，任务可能未执行")
                await db.execute(
                    "INSERT INTO alert_events (rule_id, server_name, metric, value, message, kind, created_at) "
                    "VALUES (NULL, ?, 'heartbeat', ?, ?, 'heartbeat_missed', ?)",
                    (check["name"], float(wait), msg, now),
                )
                await db.commit()
                if not await _in_maintenance("*"):
                    await _notify(msg)
        elif st in ("ok", "late") and prev == "missed":
            _state[cid] = {"status": "ok", "missed_at": None}
            # 恢复通知: 之前 missed 过
            cur = await db.execute(
                "SELECT id FROM alert_events WHERE metric = 'heartbeat' AND server_name = ? "
                "AND kind = 'heartbeat_missed' AND created_at > ? LIMIT 1",
                (check["name"], now - RECOVERY_WINDOW),
            )
            if await cur.fetchone():
                msg = f"💚 任务心跳已恢复 [{check['name']}]：已收到新心跳"
                await db.execute(
                    "INSERT INTO alert_events (rule_id, server_name, metric, value, message, kind, created_at) "
                    "VALUES (NULL, ?, 'heartbeat', 0, ?, 'heartbeat_recovered', ?)",
                    (check["name"], msg, now),
                )
                await db.commit()
                if not await _in_maintenance("*"):
                    await _notify(msg)
        elif st == "new":
            _state[cid] = {"status": "new"}


async def heartbeat_loop() -> None:
    while True:
        try:
            await check_heartbeats()
        except Exception as e:
            logger.warning("heartbeat loop error: %s", e)
        await asyncio.sleep(CHECK_INTERVAL)
