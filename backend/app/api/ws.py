"""WebSocket endpoint for real-time metrics push.

鉴权：连接时带 ?token=<JWT>；无效/过期/被禁用账号一律 4401 关闭。
未登录前端收到 4401 后自动降级为轮询公开（脱敏）数据。
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.auth import decode_token
from app.core.database import get_db

router = APIRouter(tags=["websocket"])

_clients: set[WebSocket] = set()


async def broadcast(message: dict) -> None:
    """Broadcast a message to all connected WebSocket clients."""
    dead = set()
    payload = json.dumps(message)
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = ws.query_params.get("token", "")
    payload = decode_token(token) if token else None
    if payload:
        # 与 REST 一致：账号被禁用/删除后 token 立即失效
        db = await get_db()
        cur = await db.execute(
            "SELECT id FROM users WHERE email = ? AND disabled = 0", (payload.get("sub"),)
        )
        row = await cur.fetchone()
    else:
        row = None
    if not row:
        # 先 accept 再 close，保证浏览器 onclose 收到 4401（若在 accept 前
        # 关闭，握手失败，浏览器只会看到 1006，前端降级判断会失效）
        await ws.accept()
        await ws.close(code=4401)
        return

    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            # Keep connection alive; discard client messages
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
