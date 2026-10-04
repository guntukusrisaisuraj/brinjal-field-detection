"""
Database package for AgriSense AI.

Provides:
  - engine      : SQLAlchemy async engine
  - AsyncSession : session factory for dependency injection
  - Base        : declarative base for ORM models
  - get_db      : FastAPI dependency that yields a session
  - init_db()   : creates all tables on startup

DATABASE_URL env var (default: SQLite file in backend/data/agrisense.db):
  SQLite  : sqlite+aiosqlite:///./data/agrisense.db          ← default (zero config)
  Postgres: postgresql+asyncpg://user:pass@host:5432/dbname   ← production
  MySQL   : mysql+aiomysql://user:pass@host:3306/dbname

To switch databases: just change DATABASE_URL in backend/.env.
No code changes required — SQLAlchemy handles the dialect.
"""
from app.database.engine import engine, AsyncSession, get_db, init_db

__all__ = ["engine", "AsyncSession", "get_db", "init_db"]
