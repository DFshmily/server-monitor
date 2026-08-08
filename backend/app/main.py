"""FastAPI application entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import init_db, close_db
from app.api.agent import router as agent_router
from app.api.dashboard import router as dashboard_router
from app.api.ws import router as ws_router
from app.services.aggregator import aggregator_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path("/home/ubuntu/server-monitor/frontend/dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
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
app.include_router(ws_router)

# Serve frontend static files if built
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
