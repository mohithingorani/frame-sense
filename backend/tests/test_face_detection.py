from types import SimpleNamespace

from PIL import Image

from app.services.face_detection import FaceDetectionService


class MockDetector:
    def process(self, _):
        rel_box = SimpleNamespace(xmin=0.1, ymin=0.2, width=0.4, height=0.5)
        loc = SimpleNamespace(relative_bounding_box=rel_box)
        detection = SimpleNamespace(location_data=loc)
        return SimpleNamespace(detections=[detection])


def test_face_detection_bbox_scaling():
    image = Image.new("RGB", (100, 200), "black")
    service = FaceDetectionService(detector=MockDetector())
    bbox = service.detect_single_face(image)
    assert bbox is not None
    assert bbox.x == 10
    assert bbox.y == 40
    assert bbox.width == 40
    assert bbox.height == 100
