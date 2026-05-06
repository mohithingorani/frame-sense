import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from PIL import UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.config import settings
from app.db.base import Base
from app.db.repository import create_roi
from app.db.session import AsyncSessionLocal, engine
from app.schemas import FrameOutput, ROIOut
from app.services.face_detection import FaceDetectionService
from app.services.frame_codec import decode_frame, encode_frame
from app.services.stream_hub import hub


processor_task: asyncio.Task | None = None
logger = logging.getLogger(__name__)


def _validate_image_size(width: int, height: int) -> bool:
    return width <= settings.max_width and height <= settings.max_height


async def process_frames_loop() -> None:
    detector = FaceDetectionService()
    while True:
        payload = await hub.pop_frame()
        try:
            try:
                image = decode_frame(payload)
            except (UnidentifiedImageError, ValueError, OSError):
                await hub.broadcast_json(FrameOutput(image_base64="", note="invalid_frame").model_dump())
                continue

            if not _validate_image_size(*image.size):
                await hub.broadcast_json(FrameOutput(image_base64="", note="frame_dimensions_exceeded").model_dump())
                continue

            bbox = detector.detect_single_face(image)
            if not bbox:
                encoded = encode_frame(image)
                await hub.broadcast_json(FrameOutput(image_base64=encoded, note="no_face").model_dump())
                continue

            processed = detector.draw_bbox(image, bbox)
            encoded = encode_frame(processed)

            async with AsyncSessionLocal() as session:
                row = await create_roi(session, bbox.x, bbox.y, bbox.width, bbox.height)
                roi = ROIOut.model_validate(row, from_attributes=True)

            payload_out = FrameOutput(image_base64=encoded, roi=roi).model_dump(mode="json")
            await hub.broadcast_json(payload_out)
        except Exception:
            logger.exception("Frame processing failed")


async def init_db_with_retry(max_attempts: int = 15, delay_seconds: float = 1.0) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except (OSError, SQLAlchemyError) as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            await asyncio.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


@asynccontextmanager
async def lifespan(_: FastAPI):
    global processor_task
    await init_db_with_retry()

    if settings.enable_processor:
        processor_task = asyncio.create_task(process_frames_loop())
    try:
        yield
    finally:
        if processor_task:
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
        await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
