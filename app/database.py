from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


engine = create_async_engine(settings.database_url, echo=False)
readonly_engine = create_async_engine(settings.database_url_readonly, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
ReadonlySessionLocal = async_sessionmaker(readonly_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with ReadonlySessionLocal() as session:
        yield session
