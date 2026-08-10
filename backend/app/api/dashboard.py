"""Dashboard query endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from app.core.database import get_db
from app.core.config import API_KEY
from app.core.auth import decode_token

router = APIRouter(prefix="/api", tags=["dashboard"])


class AliasUpdate(BaseModel):
    alias: str


async def verify_token(authorization: str = Header(None)):
    """Require Bearer token for write endpoints."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


async def optional_user(authorization: str = Header(None)) -> dict | None:
    """Return user dict if a valid JWT is present, else None (public access)."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    payload = decode_token(parts[1])
    if not payload:
        return None
    return {"email": payload.get("sub"), "role": payload.get("role")}


async def require_user(authorization: str = Header(None)) -> dict:
    """Require a valid JWT (any logged-in user)."""
    user = await optional_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


@router.get("/servers")
async def list_servers():
    """List all registered server names with aliases."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT DISTINCT server_name FROM metrics_raw ORDER BY server_name"
    )
    rows = await cursor.fetchall()
    names = [row["server_name"] for row in rows]

    # Attach aliases
    result = []
    for name in names:
        ac = await db.execute(
            "SELECT alias FROM server_meta WHERE server_name = ?", (name,)
        )
        arow = await ac.fetchone()
        result.append({
            "name": name,
            "alias": arow["alias"] if arow else None,
        })
    return result


@router.get("/servers/{name}/alias")
async def get_alias(name: str):
    """Get the display alias for a server."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT alias FROM server_meta WHERE server_name = ?", (name,)
    )
    row = await cursor.fetchone()
    return {"name": name, "alias": row["alias"] if row else None}


@router.put("/servers/{name}/alias", dependencies=[Depends(require_user)])
async def set_alias(name: str, payload: AliasUpdate):
    """Set the display alias for a server."""
    alias = payload.alias.strip()
    if len(alias) > 30:
        raise HTTPException(status_code=400, detail="Alias too long (max 30 chars)")
    db = await get_db()
    await db.execute(
        """INSERT INTO server_meta (server_name, alias) VALUES (?, ?)
           ON CONFLICT(server_name) DO UPDATE SET alias = excluded.alias""",
        (name, alias),
    )
    await db.commit()
    return {"name": name, "alias": alias}


@router.get("/servers/{name}/latest")
async def server_latest(name: str, user: dict | None = Depends(optional_user)):
    """Get the latest metrics for a server.

    Public: returns the full payload minus sensitive fields (service
    details, process list, hostname) when not logged in.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1",
        (name,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Server not found")
    data = json.loads(row["data"])

    # Strip sensitive details for anonymous visitors
    if not user:
        data = dict(data)
        data.pop("hostname", None)
        if "services" in data:
            data["services"] = {
                "total": data["services"].get("total", 0),
                "failed": data["services"].get("failed", 0),
                "running": data["services"].get("running", 0),
            }
        if "processes" in data:
            data["processes"] = {"top_cpu": [], "top_memory": []}
    return data


@router.get("/servers/{name}/history", dependencies=[Depends(require_user)])
async def server_history(
    name: str,
    interval: str = Query("1min", description="Aggregation interval: realtime, 1min, 5min, 1h, 1d, 1mon"),
    limit: int = Query(100, ge=1, le=10000),
    start: int | None = Query(None, description="Start unix timestamp (inclusive)"),
    end: int | None = Query(None, description="End unix timestamp (inclusive)"),
):
    """Get historical aggregated metrics for a server."""
    db = await get_db()

    # Map 1mon → 1d aggregation (30 days of daily points)
    if interval == "1mon":
        interval = "1d"
        if limit == 100:
            limit = 31

    if interval == "realtime":
        sql = "SELECT timestamp, data FROM metrics_raw WHERE server_name = ?"
        params: list = [name]
        if start is not None:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end is not None:
            sql += " AND timestamp <= ?"
            params.append(end)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(sql, params)
    else:
        sql = "SELECT timestamp, data FROM metrics_agg WHERE server_name = ? AND interval = ?"
        params = [name, interval]
        if start is not None:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end is not None:
            sql += " AND timestamp <= ?"
            params.append(end)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [
        {"timestamp": row["timestamp"], "data": json.loads(row["data"])}
        for row in reversed(rows)
    ]


@router.get("/servers/{name}/overview", dependencies=[Depends(require_user)])
async def server_overview(name: str):
    """Summary stats for the overview card."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1",
        (name,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Server not found")

    latest = json.loads(row["data"])

    # Get 1h of data for min/max/avg calculations
    cursor2 = await db.execute(
        "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1800",
        (name,),
    )
    rows = await cursor2.fetchall()
    cpu_vals, mem_vals = [], []
    for r in rows:
        d = json.loads(r["data"])
        cpu_vals.append(d.get("cpu", {}).get("percent", 0))
        mem_vals.append(d.get("memory", {}).get("percent", 0))

    return {
        "server_name": name,
        "latest": latest,
        "stats": {
            "cpu": {
                "avg": sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0,
                "min": min(cpu_vals) if cpu_vals else 0,
                "max": max(cpu_vals) if cpu_vals else 0,
            },
            "memory": {
                "avg": sum(mem_vals) / len(mem_vals) if mem_vals else 0,
                "min": min(mem_vals) if mem_vals else 0,
                "max": max(mem_vals) if mem_vals else 0,
            },
            "data_points": len(cpu_vals),
        },
    }
