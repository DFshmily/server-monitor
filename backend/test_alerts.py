"""End-to-end test of the alert engine: rule trigger -> event + Telegram push."""
import asyncio
import os
import time

os.environ.setdefault("MONITOR_API_KEY", "monitor-secret-key-2026")

from app.core.database import get_db, audit_log
from app.services.alerts import check_threshold_rules, check_offline, _send_telegram

RULES = []


async def setup():
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO alert_rules (server_name, metric, operator, threshold, enabled, created_at) VALUES ('oracle', 'memory', '>', 1, 1, ?)",
        (int(time.time()),),
    )
    RULES.append(cur.lastrowid)
    await db.commit()
    print("✅ 测试规则已建 (oracle memory > 1%，必触发)")


async def run():
    await check_threshold_rules()
    db = await get_db()
    cur = await db.execute(
        "SELECT server_name, metric, value, message, kind FROM alert_events WHERE metric='memory' ORDER BY id DESC LIMIT 1"
    )
    ev = await cur.fetchone()
    print("✅ 事件落库:", dict(ev) if ev else "无")

    # cooldown: 立即再跑一次不应重复触发
    before = (await (await db.execute("SELECT COUNT(*) n FROM alert_events WHERE metric='memory'")).fetchone())["n"]
    await check_threshold_rules()
    after = (await (await db.execute("SELECT COUNT(*) n FROM alert_events WHERE metric='memory'")).fetchone())["n"]
    print("✅ cooldown 生效（事件数不变）:", before == after, f"({before} -> {after})")

    # Telegram 推送测试
    ok = await _send_telegram("🧪 测试：监控告警推送通道已就绪 ✅")
    print("✅ Telegram 推送:", "成功" if ok else "未配置/失败")


async def cleanup():
    db = await get_db()
    await db.execute(f"DELETE FROM alert_rules WHERE id IN ({','.join('?' for _ in RULES)})", RULES)
    await db.execute("DELETE FROM alert_events WHERE metric='memory' AND message LIKE '%oracle%'")
    await db.commit()
    await db.close()


async def main():
    await setup()
    try:
        await run()
    finally:
        await cleanup()


asyncio.run(main())
