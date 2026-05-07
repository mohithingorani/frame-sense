import pytest

from app.db.repository import create_roi, create_roi_batch, list_roi


@pytest.mark.asyncio
async def test_create_roi(test_db_session):
    async with test_db_session() as session:
        roi = await create_roi(session, x=100, y=50, width=200, height=200)
        assert roi.id is not None
        assert roi.x == 100
        assert roi.y == 50
        assert roi.width == 200
        assert roi.height == 200
        assert roi.timestamp is not None


@pytest.mark.asyncio
async def test_create_roi_batch(test_db_session):
    batch = [
        {"x": 100, "y": 50, "width": 200, "height": 200},
        {"x": 120, "y": 80, "width": 180, "height": 180},
    ]
    async with test_db_session() as session:
        rois = await create_roi_batch(session, batch)
        assert len(rois) == 2
        assert rois[0].x == 100
        assert rois[1].x == 120


@pytest.mark.asyncio
async def test_create_roi_batch_empty(test_db_session):
    async with test_db_session() as session:
        rois = await create_roi_batch(session, [])
        assert rois == []


@pytest.mark.asyncio
async def test_list_roi_returns_latest_first(test_db_session):
    async with test_db_session() as session:
        await create_roi(session, x=10, y=20, width=100, height=120)
        await create_roi(session, x=100, y=200, width=80, height=90)
        
    async with test_db_session() as session:
        rois = await list_roi(session, limit=1)
        assert len(rois) == 1
        assert rois[0].x == 100


@pytest.mark.asyncio
async def test_list_roi_respects_limit(test_db_session):
    async with test_db_session() as session:
        for i in range(5):
            await create_roi(session, i * 10, i * 10, 50, 50)
            
    async with test_db_session() as session:
        rois = await list_roi(session, limit=3)
        assert len(rois) == 3


@pytest.mark.asyncio
async def test_list_roi_empty_table(test_db_session):
    async with test_db_session() as session:
        rois = await list_roi(session, limit=10)
        assert rois == []