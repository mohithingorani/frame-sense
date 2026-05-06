import pytest

from app.db.repository import create_roi


@pytest.mark.asyncio
async def test_get_roi_returns_latest(client, test_db_session):
    async with test_db_session() as session:
        await create_roi(session, 1, 2, 100, 120)
        await create_roi(session, 10, 20, 80, 90)

    response = client.get("/roi?limit=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["x"] == 10
    assert body[0]["y"] == 20
