"""Dashboard query endpoints."""
import json
import time
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from app.core.database import get_db
from app.core.config import API_KEY
from app.core.auth import decode_token
from app.api.auth import require_admin

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


@router.get("/servers/{name}/traffic/daily", dependencies=[Depends(require_user)])
async def server_traffic_daily(name: str, days: int = Query(30, ge=1, le=90)):
    """每日流量合计（北京时间日界），由 1h 聚合桶的 lifetime 最大值差分得出。"""
    db = await get_db()

    TZ8 = datetime.timezone(datetime.timedelta(hours=8))
    now = int(time.time())
    # 多取一天做差分基准
    cur = await db.execute(
        """SELECT ((timestamp + 28800) / 86400) AS day,
                  MAX(CAST(json_extract(data, '$.network.lifetime_bytes_recv') AS INTEGER)) AS r,
                  MAX(CAST(json_extract(data, '$.network.lifetime_bytes_sent') AS INTEGER)) AS s
           FROM metrics_agg
           WHERE server_name = ? AND interval = '1h' AND timestamp >= ?
           GROUP BY day ORDER BY day""",
        (name, now - (days + 1) * 86400),
    )
    rows = await cur.fetchall()
    if not rows:
        return []

    # 基准: 今天北京零点前最近一条 raw 记录的 lifetime(raw 保留1天, 足够当天差分)
    def day_start_bj(ts: int) -> int:
        return int(datetime.datetime.fromtimestamp(ts, TZ8).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    today_start = day_start_bj(now)
    base_raw: tuple | None = None
    cur = await db.execute(
        "SELECT data FROM metrics_raw WHERE server_name = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1",
        (name, today_start),
    )
    brow = await cur.fetchone()
    if brow:
        net = json.loads(brow["data"]).get("network", {})
        rv = net.get("lifetime_bytes_recv")
        sv = net.get("lifetime_bytes_sent")
        if rv is not None and sv is not None:
            base_raw = (int(rv), int(sv))

    out = []
    prev: tuple | None = None
    for row in rows:
        if row["r"] is None or row["s"] is None:
            continue  # 该日聚合桶尚无 lifetime 字段(升级前历史数据)
        day_utc0 = row["day"] * 86400 - 28800  # 该北京日的 UTC 零点
        if day_utc0 > now:
            break
        if prev is None:
            # 首日: 若正是今天且 raw 基准可用, 当天显示真实用量; 否则作基准(记 0)
            if day_utc0 == today_start and base_raw is not None:
                recv = max(0, row["r"] - base_raw[0])
                sent = max(0, row["s"] - base_raw[1])
            else:
                recv = sent = 0
            prev = (row["r"], row["s"])
        else:
            recv = max(0, row["r"] - prev[0])
            sent = max(0, row["s"] - prev[1])
            prev = (row["r"], row["s"])
        date_str = datetime.datetime.fromtimestamp(day_utc0, TZ8).strftime("%m-%d")
        out.append({
            "date": date_str,
            "recv_bytes": recv,
            "sent_bytes": sent,
            "total_bytes": recv + sent,
        })
    return out


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


@router.get("/servers/{name}/custom-history", dependencies=[Depends(require_user)])
async def custom_history(name: str, item: str, hours: int = 24):
    """自定义监控项历史值（从 metrics_raw 采样；raw 保留 1 天，故上限 24h）。"""
    db = await get_db()
    now = int(time.time())
    start = now - min(max(hours, 1), 24) * 3600
    cur = await db.execute(
        "SELECT timestamp, data FROM metrics_raw WHERE server_name = ? AND timestamp >= ? "
        "ORDER BY timestamp ASC",
        (name, start),
    )
    rows = await cur.fetchall()
    points = []
    last = 0
    for r in rows:
        c = (json.loads(r["data"]).get("custom") or {}).get(item)
        if not c or c.get("value") is None:
            continue
        if r["timestamp"] - last < 60:  # 采样：每 60s 一个点
            continue
        last = r["timestamp"]
        points.append({"timestamp": r["timestamp"], "value": c["value"]})
    if len(points) > 500:  # 限制点数
        step = len(points) // 500 + 1
        points = points[::step]
    return points


@router.get("/badge/{name}.svg")
async def status_badge(name: str):
    """公开状态徽章（SVG, shields.io 风格, 无需登录, 可嵌入教程/论坛/README）。

    左侧标签 = 服务器名(别名优先), 右侧 = 24h 可用率(在线绿色/离线红色)。
    """
    from fastapi.responses import Response
    db = await get_db()
    now = int(time.time())

    ac = await db.execute("SELECT alias FROM server_meta WHERE server_name = ?", (name,))
    arow = await ac.fetchone()
    label = (arow["alias"] if arow and arow["alias"] else name) or name

    # 24h 可用率: 每 5 分钟窗口内有上报即算在线
    cur = await db.execute(
        "SELECT COUNT(DISTINCT timestamp/300) as n FROM metrics_raw "
        "WHERE server_name = ? AND timestamp > ?",
        (name, now - 86400),
    )
    row = await cur.fetchone()
    windows = row["n"] if row else 0
    total_windows = 86400 // 300
    uptime = round(windows / total_windows * 100, 1) if windows else 0.0
    uptime = min(uptime, 100.0)  # 边界统计可能略超 100%

    # 当前在线状态: 最新数据 < 120s
    cur = await db.execute(
        "SELECT MAX(timestamp) as ts FROM metrics_raw WHERE server_name = ?", (name,)
    )
    row = await cur.fetchone()
    online = bool(row and row["ts"] and now - row["ts"] <= 120)

    color = "#34c759" if online else "#ff3b30"
    value = f"{uptime}% 可用" if online else "离线"

    lw = max(48, len(label) * 8 + 22)      # 左标签宽
    rw = max(72, len(value) * 8 + 22)      # 右值宽
    total_w = lw + rw
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{total_w}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <g shape-rendering="crispEdges">
    <rect width="{lw}" height="20" fill="#4c566a"/>
    <rect x="{lw}" width="{rw}" height="20" fill="{color}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{lw/2}" y="14" font-weight="bold">{label}</text>
    <text x="{lw + rw/2}" y="14" font-weight="bold">{value}</text>
  </g>
</svg>'''
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "no-cache, no-store"})


@router.get("/servers/{name}/events", dependencies=[Depends(require_user)])
async def server_events(name: str, hours: int = 24):
    """服务器相关事件(告警/离线/恢复) + 维护窗口，供详情页图表标注（Grafana Annotations 风格）。"""
    db = await get_db()
    now = int(time.time())
    start = now - min(max(hours, 1), 720) * 3600
    cur = await db.execute(
        "SELECT kind, message, created_at FROM alert_events "
        "WHERE server_name = ? AND kind NOT LIKE 'probe%' AND created_at >= ? "
        "ORDER BY created_at ASC LIMIT 300",
        (name, start),
    )
    events = [{"ts": r["created_at"], "kind": r["kind"], "message": r["message"]} for r in await cur.fetchall()]
    cur = await db.execute(
        "SELECT server_name, start_at, end_at, note FROM maintenance_windows "
        "WHERE (server_name = ? OR server_name = '*') AND end_at >= ?",
        (name, start),
    )
    windows = [{"start": r["start_at"], "end": r["end_at"], "note": r["note"]} for r in await cur.fetchall()]
    return {"events": events, "maintenance": windows}


@router.get("/agents-health", dependencies=[Depends(require_admin)])
async def agents_health():
    """每台 agent 的上报健康：最后上报时间 / 版本 / 推送频率。"""
    db = await get_db()
    now = int(time.time())
    cur = await db.execute("SELECT DISTINCT server_name FROM metrics_raw ORDER BY server_name")
    servers = [r["server_name"] for r in await cur.fetchall()]
    out = []
    for name in servers:
        cur = await db.execute(
            "SELECT data FROM metrics_raw WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1",
            (name,),
        )
        row = await cur.fetchone()
        latest = json.loads(row["data"]) if row else {}
        cur = await db.execute(
            "SELECT MAX(timestamp) as last_ts, COUNT(*) as n FROM metrics_raw "
            "WHERE server_name = ? AND timestamp > ?",
            (name, now - 600),
        )
        st = await cur.fetchone()
        last_ts = st["last_ts"] or 0
        out.append({
            "server_name": name,
            "version": latest.get("agent_version"),
            "hostname": latest.get("hostname"),
            "last_ts": last_ts,
            "last_age": now - last_ts,
            "pushes_10min": st["n"],
            "online": (now - last_ts) <= 120,
        })
    return out
