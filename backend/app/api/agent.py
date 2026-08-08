"""Agent metrics ingestion endpoint."""
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from app.core.config import API_KEY
from app.core.database import get_db
from app.models.metrics import AgentPayload
from app.api.ws import broadcast

router = APIRouter(prefix="/api/agent", tags=["agent"])


async def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("/metrics", dependencies=[Depends(verify_token)])
async def receive_metrics(payload: AgentPayload):
    """Receive metrics from a monitoring agent."""
    db = await get_db()
    timestamp = payload.metrics.get("timestamp", int(time.time()))
    data_json = json.dumps(payload.metrics)
    await db.execute(
        "INSERT INTO metrics_raw (server_name, timestamp, data) VALUES (?, ?, ?)",
        (payload.server_name, timestamp, data_json),
    )
    await db.commit()
    # Broadcast to connected WebSocket clients
    await broadcast({
        "type": "metrics",
        "server_name": payload.server_name,
        "data": payload.metrics,
    })
    return {"status": "ok"}
