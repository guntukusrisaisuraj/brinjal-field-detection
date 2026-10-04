"""
Google Earth Engine client initialiser.

Authentication priority:
  1. Service account (GEE_SERVICE_ACCOUNT_EMAIL + GEE_PRIVATE_KEY_FILE)
  2. Application-default / persisted credentials (~/.config/earthengine/credentials)

Call `init_ee()` once at application startup.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import ee
from app.utils.logger import logger


class EEClient:
    """Singleton Earth Engine client."""

    _initialized: bool = False
    _project: Optional[str] = None

    @classmethod
    def init(cls) -> None:
        """Initialise GEE. Idempotent – safe to call multiple times."""
        if cls._initialized:
            return

        project = os.getenv("GEE_PROJECT_ID", "")
        service_account = os.getenv("GEE_SERVICE_ACCOUNT_EMAIL", "")
        key_file = os.getenv("GEE_PRIVATE_KEY_FILE", "")

        try:
            if service_account and key_file and os.path.exists(key_file):
                logger.info(
                    f"[GEE] Authenticating with service account: {service_account}"
                )
                credentials = ee.ServiceAccountCredentials(service_account, key_file)
                ee.Initialize(credentials, project=project or None)
            else:
                logger.info("[GEE] Authenticating with application-default credentials")
                ee.Initialize(project=project or None)

            # Quick connectivity test
            _ = ee.Number(1).getInfo()
            cls._initialized = True
            cls._project = project
            logger.info("[GEE] Earth Engine initialised successfully")

        except ee.EEException as exc:
            logger.error(f"[GEE] Initialisation failed: {exc}")
            raise RuntimeError(
                "Google Earth Engine authentication failed. "
                "Run `earthengine authenticate` or configure a service account. "
                f"Details: {exc}"
            ) from exc

    @classmethod
    def is_ready(cls) -> bool:
        return cls._initialized

    @classmethod
    def project(cls) -> Optional[str]:
        return cls._project


def init_ee() -> None:
    """Module-level convenience wrapper."""
    EEClient.init()
