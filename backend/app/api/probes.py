"""Probe rules API: CRUD + test + results + uptime stats (admin)."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db, audit_log
from app.api.auth import require_admin
from app.services import probes

router = APIRouter(prefix="/api/probes", tags=["probes"])

VALID_TYPES = ("http", "tcp", "ping", "dns")


class ProbeRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str
    target: str = Field(min_length=1, max_length=512)
    expected: str = Field(default="", max_length=256)
    interval: int = Field(default=60, ge=10, le=86400)
    timeout: int = Field(default=10, ge=1, le=30)


class ProbeRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: str | None = None
    target: str | None = Field(default=None, min_length=1, max_length=512)
    expected: str | None = Field(default=None, max_length=256)
    interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: int | None = Field(default=None, ge=1, le=30)
    enabled: bool | None = None


def _validate_target(type_: str, target: str):
    """校验更新后的 type/target 组合。"""
    if type_ not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"类型必须是 {', '.join(VALID_TYPES)}")
    if type_ == "tcp" and ":" not in target:
        raise HTTPException(status_code=400, detail="TCP 目标格式应为 host:port")
    if type_ == "http" and not target.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="HTTP 目标应以 http:// 或 https:// 开头")


def _validate_rule(req: ProbeRuleRequest):
    if req.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"类型必须是 {', '.join(VALID_TYPES)}")
    if req.type == "tcp" and ":" not in req.target:
        raise HTTPException(status_code=400, detail="TCP 目标格式应为 host:port")
    if req.type == "http" and not req.target.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="HTTP 目标应以 http:// 或 https:// 开头")


@router.get("/rules", dependencies=[Depends(require_admin)])
async def list_rules():
    db = await get_db()
    cur = await db.execute("SELECT * FROM probe_rules ORDER BY id DESC")
    rules = [dict(r) for r in await cur.fetchall()]
    now = int(time.time())
    for r in rules:
        st = probes.state.get(r["id"])
        r["current"] = st or None
        # 24h uptime
        cur = await db.execute(
            "SELECT COUNT(*) as n, COALESCE(SUM(ok),0) as ok_n FROM probe_results "
            "WHERE rule_id = ? AND created_at > ?",
            (r["id"], now - 86400),
        )
        row = await cur.fetchone()
        r["uptime_24h"] = round(row["ok_n"] / row["n"] * 100, 1) if row["n"] else None
        r["checks_24h"] = row["n"]
    return rules


@router.post("/rules", dependencies=[Depends(require_admin)])
async def create_rule(req: ProbeRuleRequest, admin: dict = Depends(require_admin)):
    _validate_rule(req)
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO probe_rules (name, type, target, expected, interval, timeout, enabled, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (req.name.strip(), req.type, req.target.strip(), req.expected.strip(), req.interval, req.timeout, int(time.time())),
    )
    await db.commit()
    rule_id = cur.lastrowid
    await audit_log(admin["email"], "create_probe", f"{req.type} {req.target} ({req.name})")
    return {"ok": True, "id": rule_id}


@router.put("/rules/{rule_id}", dependencies=[Depends(require_admin)])
async def update_rule(rule_id: int, req: ProbeRuleUpdate, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("SELECT * FROM probe_rules WHERE id = ?", (rule_id,))
    rule = await cur.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    # 取合并后的 type/target 做组合校验（任一变化都重新校验）
    new_type = req.type if req.type is not None else rule["type"]
    new_target = req.target if req.target is not None else rule["target"]
    _validate_target(new_type, new_target)
    updates = {}
    for col in ("name", "type", "target", "expected", "interval", "timeout", "enabled"):
        val = getattr(req, col)
        if val is not None:
            updates[col] = val
    if updates:
        sets = ", ".join(f"{c} = ?" for c in updates)
        await db.execute(f"UPDATE probe_rules SET {sets} WHERE id = ?", [*updates.values(), rule_id])
        await db.commit()
        # 目标/间隔变了，清掉旧状态缓存，让下一次探测立即按新配置跑
        probes.state.pop(rule_id, None)
        await audit_log(admin["email"], "update_probe", f"规则 {rule_id} 更新")
    return {"ok": True}


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_admin)])
async def delete_rule(rule_id: int, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("SELECT id FROM probe_rules WHERE id = ?", (rule_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.execute("DELETE FROM probe_rules WHERE id = ?", (rule_id,))
    await db.execute("DELETE FROM probe_results WHERE rule_id = ?", (rule_id,))
    await db.commit()
    probes.state.pop(rule_id, None)
    await audit_log(admin["email"], "delete_probe", f"删除规则 {rule_id}")
    return {"ok": True}


@router.post("/rules/{rule_id}/test", dependencies=[Depends(require_admin)])
async def test_rule(rule_id: int):
    """Run one immediate probe (also persisted) and return the result."""
    db = await get_db()
    cur = await db.execute("SELECT * FROM probe_rules WHERE id = ?", (rule_id,))
    rule = await cur.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    result = await probes._run_probe(rule)
    await db.execute(
        "INSERT INTO probe_results (rule_id, ok, latency_ms, status_code, message, created_at) VALUES (?,?,?,?,?,?)",
        (rule_id, int(result["ok"]), result.get("latency_ms"), result.get("status_code"),
         result.get("message", ""), int(time.time())),
    )
    await db.commit()
    probes.state[rule_id] = {"rule_id": rule_id, "name": rule["name"], "type": rule["type"],
                             "target": rule["target"], **result, "ts": int(time.time())}
    return {"ok": bool(result["ok"]), **result}


@router.get("/results", dependencies=[Depends(require_admin)])
async def list_results(rule_id: int, limit: int = 30):
    db = await get_db()
    limit = max(1, min(limit, 200))
    cur = await db.execute(
        "SELECT ok, latency_ms, status_code, message, created_at FROM probe_results "
        "WHERE rule_id = ? ORDER BY id DESC LIMIT ?",
        (rule_id, limit),
    )
    return [dict(r) for r in await cur.fetchall()]
