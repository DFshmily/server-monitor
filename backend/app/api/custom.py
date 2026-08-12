"""Custom command monitors API: admin CRUD (agent pulls config via /api/agent/custom-config)."""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db, audit_log
from app.api.auth import require_admin

router = APIRouter(prefix="/api/custom-commands", tags=["custom-commands"])

VALID_SERVERS = ("oracle", "tencent")


class CustomCommandRequest(BaseModel):
    server_name: str
    name: str = Field(min_length=1, max_length=32)
    cmd: str = Field(min_length=1, max_length=512)
    interval: int = Field(default=60, ge=10, le=86400)
    unit: str = Field(default="", max_length=16)
    timeout: int = Field(default=5, ge=1, le=30)


class CustomCommandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    cmd: str | None = Field(default=None, min_length=1, max_length=512)
    interval: int | None = Field(default=None, ge=10, le=86400)
    unit: str | None = Field(default=None, max_length=16)
    timeout: int | None = Field(default=None, ge=1, le=30)
    enabled: bool | None = None


def _check_server(server_name: str):
    if server_name not in VALID_SERVERS:
        raise HTTPException(status_code=400, detail="服务器必须是 oracle / tencent")


@router.get("", dependencies=[Depends(require_admin)])
async def list_commands():
    db = await get_db()
    cur = await db.execute("SELECT * FROM custom_commands ORDER BY server_name, id")
    return [dict(r) for r in await cur.fetchall()]


@router.post("", dependencies=[Depends(require_admin)])
async def create_command(req: CustomCommandRequest, admin: dict = Depends(require_admin)):
    _check_server(req.server_name)
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO custom_commands (server_name, name, cmd, interval, unit, timeout, enabled, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (req.server_name, req.name.strip(), req.cmd.strip(), req.interval, req.unit.strip(), req.timeout, int(time.time())),
    )
    await db.commit()
    await audit_log(admin["email"], "create_custom_cmd", f"{req.server_name} {req.name}")
    return {"ok": True, "id": cur.lastrowid}


@router.put("/{cmd_id}", dependencies=[Depends(require_admin)])
async def update_command(cmd_id: int, req: CustomCommandUpdate, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("SELECT * FROM custom_commands WHERE id = ?", (cmd_id,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="命令不存在")
    updates = {}
    for col in ("name", "cmd", "interval", "unit", "timeout", "enabled"):
        val = getattr(req, col)
        if val is not None:
            updates[col] = val
    if updates:
        sets = ", ".join(f"{c} = ?" for c in updates)
        await db.execute(f"UPDATE custom_commands SET {sets} WHERE id = ?", [*updates.values(), cmd_id])
        await db.commit()
        await audit_log(admin["email"], "update_custom_cmd", f"命令 {cmd_id} 更新")
    return {"ok": True}


@router.delete("/{cmd_id}", dependencies=[Depends(require_admin)])
async def delete_command(cmd_id: int, admin: dict = Depends(require_admin)):
    db = await get_db()
    cur = await db.execute("DELETE FROM custom_commands WHERE id = ?", (cmd_id,))
    await db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="命令不存在")
    await audit_log(admin["email"], "delete_custom_cmd", f"删除命令 {cmd_id}")
    return {"ok": True}
