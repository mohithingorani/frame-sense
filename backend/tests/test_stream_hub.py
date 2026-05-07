import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.stream_hub import RateLimiter, StreamHub


class TestRateLimiter:
    def test_rate_limiter_allows_within_limit(self):
        limiter = RateLimiter(max_fps=10)
        for _ in range(10):
            assert limiter.allow() is True

    def test_rate_limiter_blocks_over_limit(self):
        limiter = RateLimiter(max_fps=3)
        for _ in range(3):
            limiter.allow()
        assert limiter.allow() is False

    def test_rate_limiter_resets_after_window(self):
        import time
        limiter = RateLimiter(max_fps=1)
        assert limiter.allow() is True
        time.sleep(1.1)
        assert limiter.allow() is True


class TestStreamHub:
    @pytest.mark.asyncio
    async def test_add_remove_output_client(self):
        hub = StreamHub()
        ws = AsyncMock()
        await hub.add_output_client(ws)
        assert ws in hub.output_clients
        
        await hub.remove_output_client(ws)
        assert ws not in hub.output_clients

    @pytest.mark.asyncio
    async def test_register_unregister_input(self):
        hub = StreamHub()
        ws = AsyncMock()
        hub.register_input(ws)
        assert ws in hub.input_limiters
        
        hub.unregister_input(ws)
        assert ws not in hub.input_limiters

    @pytest.mark.asyncio
    async def test_push_frame_rejects_when_limiter_blocks(self):
        hub = StreamHub()
        ws = AsyncMock()
        hub.register_input(ws)
        limiter = hub.input_limiters[ws]
        for _ in range(100):
            limiter.allow()
        
        result = await hub.push_frame(ws, b"test_frame")
        assert result is False

    @pytest.mark.asyncio
    async def test_push_frame_accepts_when_allowed(self):
        hub = StreamHub()
        ws = AsyncMock()
        hub.register_input(ws)
        
        result = await hub.push_frame(ws, b"test_frame")
        assert result is True

    @pytest.mark.asyncio
    async def test_broadcast_json_handles_disconnect(self):
        hub = StreamHub()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("Client disconnected")
        await hub.add_output_client(ws)
        
        await hub.broadcast_json({"test": "data"})
        
        assert ws not in hub.output_clients