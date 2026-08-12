"""Admin APIs: alert rules, alert events, audit logs."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.auth import require_admin
from app.services.alerts import _notify

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

VALID_METRICS = {
    "cpu", "memory", "disk", "load1", "load5", "load15",
    "net_in", "net_out",
    "cert_days", "traffic_month_total_gb", "traffic_used_percent",
}
VALID_OPS = {">", ">=", "<", "<="}


class RuleRequest(BaseModel):
    server_name: str = Field(default="*", min_length=1, max_length=64)
    metric: str
    operator: str = ">"
    threshold: float
    enabled: bool = True


class RuleUpdate(BaseModel):
    server_name: str | None = None
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    enabled: bool | None = None


@router.get("/rules", dependencies=[Depends(require_admin)])
async def list_rules():
    db = await get_db()
    cur = await db.execute("SELECT * FROM alert_rules ORDER BY id")
    return [dict(r) for r in await cur.fetchall()]


@router.post("/rules", dependencies=[Depends(require_admin)])
async def create_rule(req: RuleRequest):
    if req.metric not in VALID_METRICS:
        raise HTTPException(status_code=400, detail="指标必须是 " + ", ".join(sorted(VALID_METRICS)))
    if req.operator not in VALID_OPS:
        raise HTTPException(status_code=400, detail="运算符必须是 > >= < <=")
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO alert_rules (server_name, metric, operator, threshold, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (req.server_name, req.metric, req.operator, req.threshold, int(req.enabled), int(time.time())),
    )
    await db.commit()
    return {"ok": True, "id": cur.lastrowid}


@router.put("/rules/{rule_id}", dependencies=[Depends(require_admin)])
async def update_rule(rule_id: int, req: RuleUpdate):
    db = await get_db()
    cur = await db.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,))
    rule = await cur.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    fields = {}
    if req.server_name is not None:
        fields["server_name"] = req.server_name
    if req.metric is not None:
        if req.metric not in VALID_METRICS:
            raise HTTPException(status_code=400, detail="指标必须是 " + ", ".join(sorted(VALID_METRICS)))
        fields["metric"] = req.metric
    if req.operator is not None:
        if req.operator not in VALID_OPS:
            raise HTTPException(status_code=400, detail="运算符必须是 > >= < <=")
        fields["operator"] = req.operator
    if req.threshold is not None:
        fields["threshold"] = req.threshold
    if req.enabled is not None:
        fields["enabled"] = int(req.enabled)
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        await db.execute(f"UPDATE alert_rules SET {sets} WHERE id = ?", (*fields.values(), rule_id))
        await db.commit()
    return {"ok": True}


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_admin)])
async def delete_rule(rule_id: int):
    db = await get_db()
    cur = await db.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    await db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}


@router.get("/events", dependencies=[Depends(require_admin)])
async def list_events(limit: int = 50):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM alert_events ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 200),)
    )
    return [dict(r) for r in await cur.fetchall()]


@router.get("/stats", dependencies=[Depends(require_admin)])
async def alert_stats(days: int = 14):
    """Alert events per day (Beijing time) for the last N days, by kind."""
    db = await get_db()
    cur = await db.execute(
        """
        SELECT
            strftime('%m-%d', created_at, 'unixepoch', '+8 hours') AS date,
            kind,
            COUNT(*) AS n
        FROM alert_events
        WHERE created_at >= ?
        GROUP BY date, kind
        ORDER BY date
        """,
        (int(time.time()) - days * 86400,),
    )
    rows = await cur.fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["date"], {"date": r["date"], "threshold": 0, "offline": 0, "recovered": 0})
        kind = r["kind"]
        if kind in d:
            d[kind] += r["n"]
    return [out[k] for k in sorted(out)]


@router.post("/test", dependencies=[Depends(require_admin)])
async def test_notify(admin: dict = Depends(require_admin)):
    """Send a test message to every configured notification channel."""
    results = await _notify(
        f"🧪 监控通知测试\n来自 {admin['email']} · {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"如果你收到这条消息，说明通知渠道配置正常 ✅"
    )
    if not results:
        return {"ok": True, "sent": [], "message": "未配置任何通知渠道（Telegram/Bark）"}
    failed = [k for k, ok in results.items() if not ok]
    return {"ok": True, "sent": list(results.keys()), "failed": failed}


@router.get("/audit", dependencies=[Depends(require_admin)])
async def list_audit(limit: int = 50):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 200),)
    )
    return [dict(r) for r in await cur.fetchall()]


# ── 维护模式 ──────────────────────────────────────────────────────
class MaintenanceRequest(BaseModel):
    server_name: str = Field(default="*", min_length=1, max_length=64)
    start_at: int   # unix 秒
    end_at: int
    note: str = Field(default="", max_length=256)


@router.get("/maintenance", dependencies=[Depends(require_admin)])
async def list_maintenance():
    db = await get_db()
    now = int(time.time())
    cur = await db.execute("SELECT * FROM maintenance_windows ORDER BY start_at DESC")
    windows = [dict(r) for r in await cur.fetchall()]
    for w in windows:
        w["active"] = w["start_at"] <= now <= w["end_at"]
        w["expired"] = w["end_at"] < now
    return windows


@router.post("/maintenance", dependencies=[Depends(require_admin)])
async def create_maintenance(req: MaintenanceRequest, admin: dict = Depends(require_admin)):
    if req.end_at <= req.start_at:
        raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")
    if req.server_name != "*" and req.server_name not in ("oracle", "tencent"):
        raise HTTPException(status_code=400, detail="服务器必须是 oracle / tencent / * (全部)")
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO maintenance_windows (server_name, start_at, end_at, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (req.server_name, req.start_at, req.end_at, req.note.strip(), int(time.time())),
    )
    await db.commit()
    from app.core.database import audit_log
    await audit_log(admin["email"], "create_maintenance",
                    f"{req.server_name} {req.start_at}→{req.end_at} {req.note}")
    return {"ok": True, "id": cur.lastrowid}


@router.delete("/maintenance/{window_id}", dependencies=[Depends(require_admin)])
async def delete_maintenance(window_id: int):
    db = await get_db()
    cur = await db.execute("DELETE FROM maintenance_windows WHERE id = ?", (window_id,))
    await db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="窗口不存在")
    return {"ok": True}
