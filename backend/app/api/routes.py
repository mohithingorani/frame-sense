from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import logging

from app.config import settings
from app.db.repository import list_roi
from app.db.session import get_db
from app.schemas import ROIOut
from app.services.stream_hub import hub

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health() -> dict:
    from app.main import start_time, _db_healthy, _processor_enabled
    
    uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
    return {
        "status": "ok" if _db_healthy else "degraded",
        "database": "healthy" if _db_healthy else "unhealthy",
        "processor": "enabled" if _processor_enabled else "disabled",
        "uptime_seconds": round(uptime, 2),
    }


@router.get("/roi", response_model=list[ROIOut])
async def get_roi(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ROIOut]:
    rows = await list_roi(db, limit=limit)
    return [ROIOut.model_validate(row, from_attributes=True) for row in rows]


@router.websocket("/stream/input")
async def stream_input(websocket: WebSocket) -> None:
    await websocket.accept()
    hub.register_input(websocket)
    client_id = id(websocket)
    logger.info(f"Input client connected: {client_id}")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                logger.info(f"Input client disconnected: {client_id}, code: {message.get('code')}")
                break
            if "bytes" in message and message["bytes"] is not None:
                payload = message["bytes"]
            elif "text" in message and message["text"] is not None:
                payload = message["text"]
            else:
                continue

            raw_size = len(payload) if isinstance(payload, bytes) else len(payload.encode("utf-8"))
            if raw_size > settings.max_frame_bytes:
                logger.warning(f"Client {client_id} sent oversized frame: {raw_size} bytes")
                await websocket.send_json({"error": "frame_too_large"})
                continue

            accepted = await hub.push_frame(websocket, payload)
            if not accepted:
                await websocket.send_json({"error": "rate_limited"})
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.info(f"Input client error: {client_id}, error: {e}")
    finally:
        hub.unregister_input(websocket)
        logger.info(f"Input client cleaned up: {client_id}")


@router.websocket("/stream/output")
async def stream_output(websocket: WebSocket) -> None:
    await websocket.accept()
    await hub.add_output_client(websocket)
    client_id = id(websocket)
    logger.info(f"Output client connected: {client_id}")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                logger.info(f"Output client disconnected: {client_id}, code: {message.get('code')}")
                break
    except (WebSocketDisconnect, RuntimeError) as e:
        logger.info(f"Output client error: {client_id}, error: {e}")
    finally:
        await hub.remove_output_client(websocket)
        logger.info(f"Output client cleaned up: {client_id}")
