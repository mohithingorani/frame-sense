import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["ENABLE_PROCESSOR"] = "false"

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    yield Session
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
def client(test_db_session):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mock_roi_data():
    return [
        {"x": 100, "y": 50, "width": 200, "height": 200},
        {"x": 120, "y": 80, "width": 180, "height": 180},
    ]