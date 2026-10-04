"""
Location service – database-backed farm / AOI location store.

Replaces the previous in-memory dict with SQLAlchemy async operations.
The public interface is unchanged so all existing routes and tests continue
to work without modification.

Database: configured via DATABASE_URL in backend/.env
  Default: SQLite  → data/agrisense.db  (zero config)
  Prod:    PostgreSQL / MySQL via DATABASE_URL env var
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import AsyncSession as SessionFactory
from app.database.models import LocationModel
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Thin wrapper used by existing routes (preserves the old .to_dict() interface)
# ---------------------------------------------------------------------------

class SavedLocation:
    """
    Lightweight in-memory view of a LocationModel row.
    Used so route handlers don't need to change — they still call .to_dict().
    """
    def __init__(self, row: LocationModel):
        self._row = row

    # Expose all attributes transparently
    def __getattr__(self, name: str):
        return getattr(self._row, name)

    def to_dict(self) -> Dict[str, Any]:
        return self._row.to_dict()


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class LocationService:
    """
    Async database-backed location service.

    All methods open their own session so they can be called from both
    FastAPI route handlers (which use Depends(get_db)) and background tasks.
    """

    async def create(
        self,
        latitude: float,
        longitude: float,
        name: str = "",
        radius_km: float = 10.0,
        date_from: str = "",
        date_to: str = "",
        cloud_threshold: float = 20.0,
        ndvi_threshold: float = 0.25,
        user_id: str = "default",
    ) -> SavedLocation:
        """Insert a new location row and return a SavedLocation wrapper."""
        row = LocationModel(
            location_id=str(uuid.uuid4()),
            latitude=latitude,
            longitude=longitude,
            name=name or f"Farm @ {latitude:.4f}, {longitude:.4f}",
            radius_km=radius_km,
            date_from=date_from,
            date_to=date_to,
            cloud_threshold=cloud_threshold,
            ndvi_threshold=ndvi_threshold,
            user_id=user_id,
            status="saved",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        async with SessionFactory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)

        logger.info(f"[LocationService] Created location {row.location_id}: {row.name}")
        return SavedLocation(row)

    async def get(self, location_id: str) -> Optional[SavedLocation]:
        """Fetch a single location by ID. Returns None if not found."""
        async with SessionFactory() as session:
            row = await session.get(LocationModel, location_id)
        return SavedLocation(row) if row else None

    async def list_all(self, user_id: Optional[str] = None) -> List[SavedLocation]:
        """List all locations, newest first. Optionally filter by user_id."""
        async with SessionFactory() as session:
            stmt = select(LocationModel).order_by(LocationModel.created_at.desc())
            if user_id:
                stmt = stmt.where(LocationModel.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [SavedLocation(r) for r in rows]

    async def update_status(
        self,
        location_id: str,
        status: str = "",
        analyze_job_id: Optional[str] = None,
        classify_job_id: Optional[str] = None,
        result_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[SavedLocation]:
        """Update status, job IDs, or result summary for a location."""
        async with SessionFactory() as session:
            row = await session.get(LocationModel, location_id)
            if row is None:
                return None
            if status:
                row.status = status
            if analyze_job_id:
                row.analyze_job_id = analyze_job_id
            if classify_job_id:
                row.classify_job_id = classify_job_id
            if result_summary:
                row.result_summary = result_summary
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
        return SavedLocation(row)

    async def delete(self, location_id: str) -> bool:
        """Delete a location. Returns True if deleted, False if not found."""
        async with SessionFactory() as session:
            row = await session.get(LocationModel, location_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
        logger.info(f"[LocationService] Deleted location {location_id}")
        return True

    async def count(self) -> int:
        """Return total number of stored locations."""
        async with SessionFactory() as session:
            result = await session.execute(select(LocationModel))
            return len(result.scalars().all())


# Singleton
location_service = LocationService()
