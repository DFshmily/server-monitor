"""Admin APIs: alert rules, alert events, audit logs."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.auth import require_admin

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

VALID_METRICS = {"cpu", "memory", "disk", "load1", "load5", "load15", "net_in", "net_out"}
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


@router.get("/audit", dependencies=[Depends(require_admin)])
async def list_audit(limit: int = 50):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 200),)
    )
    return [dict(r) for r in await cur.fetchall()]
