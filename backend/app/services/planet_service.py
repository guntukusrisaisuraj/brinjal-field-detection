"""
Planet Labs service – validates credentials and reports integration status.

IMPORTANT:
  - Planet integration is REAL. We do NOT mock or fake imagery.
  - If PLANET_API_KEY is not set, all Planet features are clearly disabled in the UI.
  - Planet imagery is only accessed when valid credentials exist and the API responds.

Planet APIs used (when credentials available):
  - Planet Data API v1  (https://api.planet.com/data/v1/)
  - Authentication: Basic Auth with API key as username

To enable:
  1. Set PLANET_API_KEY in backend/.env
  2. Ensure your Planet subscription includes the required item types
     (PSScene / SkySatCollect for high-resolution imagery)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from app.utils.logger import logger

PLANET_API_BASE = "https://api.planet.com/data/v1"


def _get_api_key() -> Optional[str]:
    key = os.getenv("PLANET_API_KEY", "").strip()
    return key if key else None


async def check_planet_access() -> Dict[str, Any]:
    """
    Check whether the configured Planet API key is valid and what
    item types are accessible.

    Returns
    -------
    dict with:
      - configured    : bool (key is set in env)
      - valid         : bool (key accepted by Planet API)
      - item_types    : list of str (available item types, if any)
      - quota_used    : str or None
      - error         : str or None
    """
    key = _get_api_key()
    if not key:
        return {
            "configured": False,
            "valid": False,
            "item_types": [],
            "quota_used": None,
            "error": (
                "PLANET_API_KEY is not set. Add it to backend/.env to enable "
                "Planet integration. Visit https://www.planet.com/account/#/user-settings "
                "to obtain your API key."
            ),
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{PLANET_API_BASE}/item-types",
                auth=(key, ""),
                headers={"Accept": "application/json"},
            )

        if resp.status_code == 401:
            return {
                "configured": True,
                "valid": False,
                "item_types": [],
                "quota_used": None,
                "error": "Planet API key is invalid or expired.",
            }

        if resp.status_code != 200:
            return {
                "configured": True,
                "valid": False,
                "item_types": [],
                "quota_used": None,
                "error": f"Planet API returned HTTP {resp.status_code}.",
            }

        data = resp.json()
        item_types = [
            it.get("display_name", it.get("id", ""))
            for it in data.get("item_types", [])[:10]  # limit to first 10
        ]

        logger.info(f"[Planet] API key valid. {len(item_types)} item types available.")
        return {
            "configured": True,
            "valid": True,
            "item_types": item_types,
            "quota_used": None,  # Planet v1 API does not expose quota here
            "error": None,
        }

    except httpx.TimeoutException:
        return {
            "configured": True,
            "valid": False,
            "item_types": [],
            "quota_used": None,
            "error": "Planet API request timed out (10 s). Check network connectivity.",
        }
    except Exception as exc:
        logger.error(f"[Planet] Unexpected error: {exc}")
        return {
            "configured": True,
            "valid": False,
            "item_types": [],
            "quota_used": None,
            "error": f"Unexpected error contacting Planet API: {exc}",
        }
