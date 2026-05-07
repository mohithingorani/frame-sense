from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ROIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    timestamp: datetime
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1, le=10000)
    height: int = Field(ge=1, le=10000)

    @field_validator("x", "y", "width", "height", mode="before")
    @classmethod
    def validate_positive(cls, v):
        if v is None:
            return v
        if not isinstance(v, int) or v < 0:
            raise ValueError("Coordinate must be a non-negative integer")
        return v


class FrameOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    image_base64: str
    roi: ROIOut | None = None
    note: str | None = Field(default=None)