import os
import pytest


class TestConfig:
    def test_default_values(self):
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("MAX_FRAME_BYTES", None)
        os.environ.pop("MAX_WIDTH", None)
        os.environ.pop("MAX_HEIGHT", None)
        os.environ.pop("MAX_FPS_PER_CLIENT", None)
        os.environ.pop("ENABLE_PROCESSOR", None)
        
        from importlib import reload
        import app.config as config_module
        reload(config_module)
        
        settings = config_module.settings
        assert settings.app_name == "Face Streaming API"
        assert settings.max_frame_bytes == 2 * 1024 * 1024
        assert settings.max_width == 1920
        assert settings.max_height == 1080
        assert settings.max_fps_per_client == 12.0
        assert settings.enable_processor is True

    def test_custom_env_values(self):
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        os.environ["MAX_FRAME_BYTES"] = "1048576"
        os.environ["MAX_WIDTH"] = "1280"
        os.environ["MAX_HEIGHT"] = "720"
        os.environ["MAX_FPS_PER_CLIENT"] = "24.0"
        os.environ["ENABLE_PROCESSOR"] = "false"
        
        from importlib import reload
        import app.config as config_module
        reload(config_module)
        
        settings = config_module.settings
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        assert settings.max_frame_bytes == 1048576
        assert settings.max_width == 1280
        assert settings.max_height == 720
        assert settings.max_fps_per_client == 24.0
        assert settings.enable_processor is False
        
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("MAX_FRAME_BYTES", None)
        os.environ.pop("MAX_WIDTH", None)
        os.environ.pop("MAX_HEIGHT", None)
        os.environ.pop("MAX_FPS_PER_CLIENT", None)
        os.environ.pop("ENABLE_PROCESSOR", None)