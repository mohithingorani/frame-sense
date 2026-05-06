from datetime import datetime

from pydantic import BaseModel, Field


class ROIOut(BaseModel):
    id: int
    timestamp: datetime
    x: int
    y: int
    width: int
    height: int


class FrameOutput(BaseModel):
    image_base64: str
    roi: ROIOut | None = None
    note: str | None = Field(default=None)
