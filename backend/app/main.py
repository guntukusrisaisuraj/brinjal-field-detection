"""
FastAPI application entry point.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

# Load configuration before importing modules that read environment variables
# at import time (notably the database engine).
from app.config import load_backend_environment

load_backend_environment()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_analyze,
    routes_classify,
    routes_health,
    routes_ndvi,
    routes_results,
    routes_train,
    routes_training,
    routes_locations,
    routes_landsat,
    routes_satellite,
    routes_score,
    routes_state_discovery,
)
from app.database import init_db
from app.earth_engine.ee_client import EEClient
from app.utils.logger import configure_logging, logger

configure_logging(os.getenv("LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Lifespan: initialise GEE on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AgriSense AI API...")

    # ── Database ──────────────────────────────────────────────────────────
    try:
        await init_db()
        logger.info("Database tables ready (SQLite/PostgreSQL).")
    except Exception as exc:
        logger.error(f"Database init failed: {exc}")

    # ── Google Earth Engine ───────────────────────────────────────────────
    try:
        EEClient.init()
        logger.info("Earth Engine ready.")
    except RuntimeError as exc:
        logger.error(
            f"Earth Engine NOT available: {exc}\n"
            "API will start but GEE endpoints will return errors until credentials are provided."
        )
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI-Based Brinjal Crop Detection API",
    description=(
        "Detects and maps brinjal (eggplant) cultivation in India using "
        "Sentinel-2 satellite imagery, Google Earth Engine, and Random Forest ML."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(routes_health.router,     prefix="/api", tags=["Health"])
app.include_router(routes_analyze.router,    prefix="/api", tags=["Analysis"])
app.include_router(routes_ndvi.router,       prefix="/api", tags=["NDVI"])
app.include_router(routes_training.router,   prefix="/api", tags=["Training Data"])
app.include_router(routes_train.router,      prefix="/api", tags=["Model Training"])
app.include_router(routes_classify.router,   prefix="/api", tags=["Classification"])
app.include_router(routes_results.router,    prefix="/api", tags=["Results"])
app.include_router(routes_locations.router,  prefix="/api", tags=["Locations"])
app.include_router(routes_landsat.router,    prefix="/api", tags=["Landsat"])
app.include_router(routes_satellite.router,  prefix="/api", tags=["Satellite Intelligence"])
app.include_router(routes_score.router,      prefix="/api", tags=["Score"])
app.include_router(routes_state_discovery.router, prefix="/api", tags=["State Discovery"])
