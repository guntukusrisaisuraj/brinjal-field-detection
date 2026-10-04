"""
SQLAlchemy async engine, session factory, and FastAPI dependency.

Reads DATABASE_URL from environment (set in backend/.env).
Defaults to SQLite at data/agrisense.db (auto-created, zero config).

Switching to PostgreSQL/MySQL:
  Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
  Install: pip install asyncpg
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

# Default: SQLite file inside backend/data/
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "agrisense.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}",
)

# Connection args — only needed for SQLite (check_same_thread)
_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    connect_args=_connect_args,
    # For PostgreSQL, increase pool size for production:
    # pool_size=10, max_overflow=20,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSession = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Declarative base for all database models."""
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session.

    Usage in route:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Table creation (called from lifespan)
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call on every startup."""
    from app.database import models as _models  # noqa: F401 — imports register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
