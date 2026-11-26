"""
System router exposes dashboard metadata and update controls.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from core import release

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("zetatech.update.router")


@router.get("/update")
async def get_update_status(force: bool = False):
    """Return the current version, latest release, and manual update helper state."""
    try:
        status_payload = await asyncio.to_thread(release.manager.get_status, force)
        return status_payload
    except Exception as exc:
        logger.exception("Failed to fetch update info")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to check for releases right now.",
        ) from exc


@router.post("/update")
async def trigger_update():
    """Return deprecated manual-only update guidance instead of triggering host mutation."""
    try:
        payload = await asyncio.to_thread(release.manager.get_manual_update_payload)
        return payload
    except Exception as exc:
        logger.exception("Update helper request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to prepare manual update instructions right now.",
        ) from exc
