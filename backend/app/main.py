import asyncio
import logging
from contextlib import asynccontextmanager
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI
from PIL import UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.config import settings
from app.db.base import Base
from app.db.repository import create_roi, create_roi_batch
from app.db.session import AsyncSessionLocal, engine
from app.schemas import FrameOutput, ROIOut
from app.services.face_detection import FaceDetectionService
from app.services.frame_codec import decode_frame, encode_frame
from app.services.stream_hub import hub


processor_task: asyncio.Task | None = None
batch_task: asyncio.Task | None = None
roi_batch: deque = deque()
BATCH_SIZE = 10
BATCH_INTERVAL = 1.0
logger = logging.getLogger(__name__)


def _validate_image_size(width: int, height: int) -> bool:
    return width <= settings.max_width and height <= settings.max_height


async def batch_writer() -> None:
    while True:
        await asyncio.sleep(BATCH_INTERVAL)
        if not roi_batch:
            continue
        batch = []
        while roi_batch and len(batch) < BATCH_SIZE:
            batch.append(roi_batch.popleft())
        if batch:
            try:
                async with AsyncSessionLocal() as session:
                    await create_roi_batch(session, batch)
            except Exception:
                logger.exception("Batch DB write failed")


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

            roi_batch.append({"x": bbox.x, "y": bbox.y, "width": bbox.width, "height": bbox.height})

            roi = ROIOut(
                id=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                x=bbox.x,
                y=bbox.y,
                width=bbox.width,
                height=bbox.height,
            )

            payload_out = FrameOutput(image_base64=encoded, roi=roi).model_dump(mode="json")
            await hub.broadcast_json(payload_out)
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError:
            logger.exception("Database error during frame processing")
            await hub.broadcast_json(FrameOutput(image_base64="", note="processing_error").model_dump())
        except Exception:
            logger.exception("Frame processing failed")
            await hub.broadcast_json(FrameOutput(image_base64="", note="processing_error").model_dump())


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
    global processor_task, batch_task
    await init_db_with_retry()

    if settings.enable_processor:
        batch_task = asyncio.create_task(batch_writer())
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
        if batch_task:
            batch_task.cancel()
            try:
                await batch_task
            except asyncio.CancelledError:
                pass
        if roi_batch:
            final_batch = list(roi_batch)
            roi_batch.clear()
            if final_batch:
                try:
                    async with AsyncSessionLocal() as session:
                        await create_roi_batch(session, final_batch)
                except Exception:
                    logger.exception("Final batch DB write failed")
        await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
