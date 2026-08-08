"""Dashboard query endpoints."""
import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.core.database import get_db

router = APIRouter(prefix="/api", tags=["dashboard"])


class AliasUpdate(BaseModel):
    alias: str


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


@router.put("/servers/{name}/alias")
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
async def server_latest(name: str):
    """Get the latest metrics for a server."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1",
        (name,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Server not found")
    return json.loads(row["data"])


@router.get("/servers/{name}/history")
async def server_history(
    name: str,
    interval: str = Query("1min", description="Aggregation interval: realtime, 1min, 5min, 1h, 1d"),
    limit: int = Query(100, ge=1, le=10000),
):
    """Get historical aggregated metrics for a server."""
    db = await get_db()
    if interval == "realtime":
        cursor = await db.execute(
            "SELECT timestamp, data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT ?",
            (name, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT timestamp, data FROM metrics_agg WHERE server_name = ? AND interval = ? ORDER BY timestamp DESC LIMIT ?",
            (name, interval, limit),
        )
    rows = await cursor.fetchall()
    return [
        {"timestamp": row["timestamp"], "data": json.loads(row["data"])}
        for row in reversed(rows)
    ]


@router.get("/servers/{name}/overview")
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
