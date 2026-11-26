import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from core import release

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("zetatech.update.router")


@router.get("/update")
async def get_update_status(force: bool = False):
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
    try:
        payload = await asyncio.to_thread(release.manager.get_manual_update_payload)
        return payload
    except Exception as exc:
        logger.exception("Update helper request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to prepare manual update instructions right now.",
        ) from exc
