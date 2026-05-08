"""
Munch – Food Ordering System Backend
FastAPI + PostgreSQL + WebSockets + AI Recommendations
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import engine, Base

async def run_seed():
    """Auto-seed on first deployment if DB is empty."""
    from sqlalchemy import select, text
    from app.db.session import AsyncSessionLocal
    from app.models.models import User
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            import subprocess, sys
            subprocess.run([sys.executable, "seed.py"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use Alembic for production migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_seed()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Munch Campus Canteen Food Ordering System. "
        "Two-tap ordering, live kitchen queue, AI recommendations, "
        "real-time WebSocket status updates."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS – allow frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", tags=["health"])
async def root():
    return {"service": settings.APP_NAME, "version": settings.APP_VERSION, "status": "ok"}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}
