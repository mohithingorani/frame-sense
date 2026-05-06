import base64
import io

from PIL import Image


def decode_frame(payload: bytes | str) -> Image.Image:
    if isinstance(payload, str):
        payload = payload.strip()
        if payload.startswith("data:image"):
            payload = payload.split(",", 1)[1]
        raw = base64.b64decode(payload)
    else:
        raw = payload

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    return image


def encode_frame(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
