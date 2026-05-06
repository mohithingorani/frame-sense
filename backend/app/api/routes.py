from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repository import list_roi
from app.db.session import get_db
from app.schemas import ROIOut
from app.services.stream_hub import hub

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"] is not None:
                payload = message["bytes"]
            elif "text" in message and message["text"] is not None:
                payload = message["text"]
            else:
                continue

            raw_size = len(payload) if isinstance(payload, bytes) else len(payload.encode("utf-8"))
            if raw_size > settings.max_frame_bytes:
                await websocket.send_json({"error": "frame_too_large"})
                continue

            accepted = await hub.push_frame(websocket, payload)
            if not accepted:
                await websocket.send_json({"error": "rate_limited"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unregister_input(websocket)


@router.websocket("/stream/output")
async def stream_output(websocket: WebSocket) -> None:
    await websocket.accept()
    await hub.add_output_client(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await hub.remove_output_client(websocket)
