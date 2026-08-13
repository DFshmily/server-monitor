"""Heartbeat checks API: 公开 ping 端点 + admin CRUD."""
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db, audit_log
from app.api.auth import require_admin
from app.services.heartbeats import record_ping, heartbeat_status

router = APIRouter(prefix="/api", tags=["heartbeats"])


# ── 公开: 心跳接收（URL 即密钥，无需鉴权）────────────────────────
@router.get("/heartbeat/{slug}")
async def ping_get(slug: str):
    ok = await record_ping(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="心跳不存在")
    return {"ok": True, "ts": int(time.time())}


@router.post("/heartbeat/{slug}")
async def ping_post(slug: str):
    ok = await record_ping(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="心跳不存在")
    return {"ok": True, "ts": int(time.time())}


# ── 管理端 CRUD ──────────────────────────────────────────────────
class HeartbeatRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    interval: int = Field(default=86400, ge=60, le=30 * 86400)   # 秒
    grace: int = Field(default=3600, ge=60, le=30 * 86400)        # 秒


class HeartbeatUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    interval: int | None = Field(default=None, ge=60, le=30 * 86400)
    grace: int | None = Field(default=None, ge=60, le=30 * 86400)
    enabled: bool | None = None


def _fmt_seconds(sec: int) -> str:
    if sec % 86400 == 0:
        return f"{sec // 86400} 天"
    if sec % 3600 == 0:
        return f"{sec // 3600} 小时"
    return f"{sec // 60} 分钟"


def _decorate(check: dict) -> dict:
    check["status"] = heartbeat_status(check)
    check["interval_label"] = _fmt_seconds(check["interval"])
    check["grace_label"] = _fmt_seconds(check["grace"])
    check["last_ping_label"] = (
        "-" if not check["last_ping"]
        else f"{check['last_ping']} ({heartbeat_status(check)})"
    )
    return check


@router.get("/heartbeats", dependencies=[Depends(require_admin)])
async def list_heartbeats():
    db = await get_db()
    cur = await db.execute("SELECT * FROM heartbeat_checks ORDER BY id DESC")
    return [_decorate(dict(r)) for r in await cur.fetchall()]


@router.post("/heartbeats", dependencies=[Depends(require_admin)])
async def create_heartbeat(req: HeartbeatRequest, admin: dict = Depends(require_admin)):
    db = await get_db()
    slug = secrets.token_urlsafe(12)
    cur = await db.execute(
        "INSERT INTO heartbeat_checks (name, slug, interval, grace, enabled, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (req.name.strip(), slug, req.interval, req.grace, int(time.time())),
    )
    await db.commit()
    await audit_log(admin["email"], "create_heartbeat", f"{req.name} ({_fmt_seconds(req.interval)})")
    return {"ok": True, "id": cur.lastrowid, "slug": slug}


@router.put("/heartbeats/{hb_id}", dependencies=[Depends(require_admin)])
async def update_heartbeat(hb_id: int, req: HeartbeatUpdate, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("SELECT * FROM heartbeat_checks WHERE id = ?", (hb_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="心跳不存在")
    updates = {}
    for col in ("name", "interval", "grace", "enabled"):
        val = getattr(req, col)
        if val is not None:
            updates[col] = val
    if updates:
        sets = ", ".join(f"{c} = ?" for c in updates)
        await db.execute(f"UPDATE heartbeat_checks SET {sets} WHERE id = ?", [*updates.values(), hb_id])
        await db.commit()
        await audit_log(admin["email"], "update_heartbeat", f"心跳 {hb_id} 更新")
    return {"ok": True}


@router.delete("/heartbeats/{hb_id}", dependencies=[Depends(require_admin)])
async def delete_heartbeat(hb_id: int, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("DELETE FROM heartbeat_checks WHERE id = ?", (hb_id,))
    await db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="心跳不存在")
    await audit_log(admin["email"], "delete_heartbeat", f"删除心跳 {hb_id}")
    return {"ok": True}
