from dataclasses import dataclass

import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


@dataclass
class BBox:
    x: int
    y: int
    width: int
    height: int


class FaceDetectionService:
    def __init__(
        self,
        detector=None,
        min_confidence: float = 0.35,
        model_path: str = "/app/models/blaze_face_short_range.tflite",
    ) -> None:
        if detector is None:
            options = vision.FaceDetectorOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                min_detection_confidence=min_confidence,
            )
            detector = vision.FaceDetector.create_from_options(options)
        self.detector = detector

    def detect_single_face(self, image: Image.Image) -> BBox | None:
        rgb = np.array(image)
        detections = []

        # MediaPipe Tasks API path.
        if hasattr(self.detector, "detect"):
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.detector.detect(mp_image)
            detections = result.detections if result else []
        # Backward-compatible path for tests/mocks.
        elif hasattr(self.detector, "process"):
            result = self.detector.process(rgb)
            detections = result.detections if result else []

        if not detections:
            return None

        detection = detections[0]
        width_px, height_px = image.size

        # Tasks API absolute bbox.
        if hasattr(detection, "bounding_box"):
            box = detection.bounding_box
            x = max(0, int(box.origin_x))
            y = max(0, int(box.origin_y))
            w = max(0, int(box.width))
            h = max(0, int(box.height))
        else:
            # Legacy relative bbox.
            rel = detection.location_data.relative_bounding_box
            x = max(0, int(rel.xmin * width_px))
            y = max(0, int(rel.ymin * height_px))
            w = max(0, int(rel.width * width_px))
            h = max(0, int(rel.height * height_px))

        w = min(w, width_px - x)
        h = min(h, height_px - y)
        if w == 0 or h == 0:
            return None

        return BBox(x=x, y=y, width=w, height=h)

    def draw_bbox(self, image: Image.Image, bbox: BBox) -> Image.Image:
        out = image.copy()
        draw = ImageDraw.Draw(out)
        draw.rectangle(
            [(bbox.x, bbox.y), (bbox.x + bbox.width, bbox.y + bbox.height)],
            outline=(0, 255, 0),
            width=3,
        )
        return out
