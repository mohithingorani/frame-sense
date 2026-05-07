import asyncio
import logging
import sys
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


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
    )


setup_logging()
logger = logging.getLogger(__name__)

start_time = datetime.now(timezone.utc)
_db_healthy = False
_processor_enabled = settings.enable_processor

processor_task: asyncio.Task | None = None
batch_task: asyncio.Task | None = None
roi_batch: deque = deque()
BATCH_SIZE = 10
BATCH_INTERVAL = 1.0


def _validate_image_size(width: int, height: int) -> bool:
    return width <= settings.max_width and height <= settings.max_height


async def batch_writer() -> None:
    logger.info("Batch writer started")
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
                logger.debug(f"Batch wrote {len(batch)} ROIs to database")
            except Exception as e:
                logger.error(f"Batch DB write failed: {e}", exc_info=True)
                for item in batch:
                    roi_batch.append(item)
    logger.warning("Batch writer stopped")


async def process_frames_loop() -> None:
    logger.info("Frame processor started")
    detector = FaceDetectionService()
    frame_count = 0
    error_count = 0
    while True:
        payload = await hub.pop_frame()
        frame_count += 1
        try:
            try:
                image = decode_frame(payload)
            except (UnidentifiedImageError, ValueError, OSError) as e:
                logger.warning(f"Invalid frame: {e}")
                await hub.broadcast_json(FrameOutput(image_base64="", note="invalid_frame").model_dump())
                continue

            if not _validate_image_size(*image.size):
                logger.warning(f"Frame dimensions exceeded: {image.size}")
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
        except SQLAlchemyError as e:
            error_count += 1
            logger.error(f"Database error during frame processing: {e}", exc_info=True)
            await hub.broadcast_json(FrameOutput(image_base64="", note="processing_error").model_dump())
        except Exception as e:
            error_count += 1
            logger.error(f"Frame processing failed: {e}", exc_info=True)
            await hub.broadcast_json(FrameOutput(image_base64="", note="processing_error").model_dump())
    logger.warning(f"Frame processor stopped (processed: {frame_count}, errors: {error_count})")


async def init_db_with_retry(max_attempts: int = 15, delay_seconds: float = 1.0) -> None:
    global _db_healthy
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _db_healthy = True
            logger.info(f"Database initialized successfully (attempt {attempt})")
            return
        except (OSError, SQLAlchemyError) as exc:
            last_error = exc
            logger.warning(f"Database init attempt {attempt}/{max_attempts} failed: {exc}")
            if attempt == max_attempts:
                break
            await asyncio.sleep(delay_seconds)
    _db_healthy = False
    assert last_error is not None
    raise last_error


@asynccontextmanager
async def lifespan(_: FastAPI):
    global processor_task, batch_task, _db_healthy, _processor_enabled
    
    logger.info("Application starting...")
    await init_db_with_retry()

    if _processor_enabled:
        batch_task = asyncio.create_task(batch_writer())
        processor_task = asyncio.create_task(process_frames_loop())
        logger.info("Frame processor tasks started")
    else:
        logger.info("Frame processor disabled via config")
    
    try:
        yield
    finally:
        logger.info("Application shutting down...")
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
                    logger.info(f"Final batch wrote {len(final_batch)} ROIs")
                except Exception as e:
                    logger.error(f"Final batch DB write failed: {e}", exc_info=True)
        await engine.dispose()
        logger.info("Application shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
