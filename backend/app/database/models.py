"""
SQLAlchemy ORM models for AgriSense AI.

Tables:
  locations  — saved farm / AOI coordinates (replaces in-memory LocationService)
  jobs       — persistent analysis/training/classification job records

All columns use standard SQL types so the models work with SQLite,
PostgreSQL, and MySQL without modification.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.engine import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Location model
# ---------------------------------------------------------------------------

class LocationModel(Base):
    """
    Persistent storage for saved farm / AOI locations.

    Replaces the in-memory dict in location_service.py.
    Each row represents one user-submitted coordinate entry.
    """
    __tablename__ = "locations"

    # Primary key
    location_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )

    # Coordinates
    latitude:    Mapped[float] = mapped_column(Float, nullable=False)
    longitude:   Mapped[float] = mapped_column(Float, nullable=False)
    name:        Mapped[str]   = mapped_column(String(200), nullable=False, default="")
    radius_km:   Mapped[float] = mapped_column(Float, default=10.0)

    # Analysis window
    date_from:        Mapped[str]   = mapped_column(String(20), default="")
    date_to:          Mapped[str]   = mapped_column(String(20), default="")
    cloud_threshold:  Mapped[float] = mapped_column(Float, default=20.0)
    ndvi_threshold:   Mapped[float] = mapped_column(Float, default=0.25)

    # User
    user_id: Mapped[str] = mapped_column(String(100), default="default", index=True)

    # Pipeline references
    status:          Mapped[str]           = mapped_column(String(20), default="saved")
    analyze_job_id:  Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    classify_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # JSON summary of analysis results (stored as TEXT / JSON column)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (matches the existing API schema)."""
        return {
            "location_id":    self.location_id,
            "latitude":       self.latitude,
            "longitude":      self.longitude,
            "name":           self.name,
            "radius_km":      self.radius_km,
            "date_from":      self.date_from,
            "date_to":        self.date_to,
            "cloud_threshold": self.cloud_threshold,
            "ndvi_threshold": self.ndvi_threshold,
            "user_id":        self.user_id,
            "status":         self.status,
            "analyze_job_id":  self.analyze_job_id,
            "classify_job_id": self.classify_job_id,
            "result_summary":  self.result_summary,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "updated_at":     self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

class JobModel(Base):
    """
    Persistent job records for analysis / training / classification tasks.

    The existing in-memory job_service loses all jobs on server restart.
    This table survives restarts, enabling job status recovery.
    """
    __tablename__ = "jobs"

    job_id:   Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Status: pending | running | completed | failed
    status:   Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message:  Mapped[str] = mapped_column(Text, default="")

    # JSON payload for results and errors
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error:  Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id":     self.job_id,
            "job_type":   self.job_type,
            "status":     self.status,
            "progress":   self.progress,
            "message":    self.message,
            "result":     self.result,
            "error":      self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
