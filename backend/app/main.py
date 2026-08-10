"""FastAPI application entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import init_db, close_db, get_db
from app.core.auth import hash_password
from app.api.agent import router as agent_router
from app.api.dashboard import router as dashboard_router
from app.api.auth import router as auth_router
from app.api.ws import router as ws_router
from app.services.aggregator import aggregator_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path("/home/ubuntu/server-monitor/frontend/dist")

# First-run admin bootstrap: create admin@dfshmily.icu with a random password.
ADMIN_EMAIL = "admin@dfshmily.icu"


async def ensure_admin_account() -> str | None:
    """Create the admin account on first run; return the initial password (shown once)."""
    db = await get_db()
    cur = await db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
    if await cur.fetchone():
        return None
    import secrets
    password = secrets.token_urlsafe(10)  # e.g. x7Kp2qR9vL
    now = int(__import__("time").time())
    await db.execute(
        "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
        (ADMIN_EMAIL, hash_password(password), now),
    )
    await db.commit()
    return password


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    initial_password = await ensure_admin_account()
    if initial_password:
        logger.warning(
            "👑 Admin account created: %s  initial password: %s  (change it after first login)",
            ADMIN_EMAIL, initial_password,
        )
    task = asyncio.create_task(aggregator_loop())
    logger.info("Aggregator started")
    yield
    task.cancel()
    await close_db()


app = FastAPI(title="Server Monitor", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(agent_router)
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(ws_router)

# Serve frontend static files if built
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
