from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Face Streaming API"
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@db:5432/facestream", alias="DATABASE_URL")
    max_frame_bytes: int = Field(default=2 * 1024 * 1024, alias="MAX_FRAME_BYTES")
    max_width: int = Field(default=1920, alias="MAX_WIDTH")
    max_height: int = Field(default=1080, alias="MAX_HEIGHT")
    max_fps_per_client: float = Field(default=12.0, alias="MAX_FPS_PER_CLIENT")
    enable_processor: bool = Field(default=True, alias="ENABLE_PROCESSOR")


settings = Settings()
