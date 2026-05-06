from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ROI


async def create_roi(session: AsyncSession, x: int, y: int, width: int, height: int) -> ROI:
    row = ROI(timestamp=datetime.now(timezone.utc), x=x, y=y, width=width, height=height)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_roi(session: AsyncSession, limit: int = 50) -> list[ROI]:
    stmt = select(ROI).order_by(desc(ROI.timestamp)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
