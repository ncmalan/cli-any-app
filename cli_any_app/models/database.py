from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Overridable for tests; production uses settings.db_url via init_db()
DATABASE_URL = "sqlite+aiosqlite:///data/cli_any_app.db"

engine = None
async_session_factory = None


class Base(DeclarativeBase):
    pass


async def init_db(url: str | None = None):
    global engine, async_session_factory
    db_url = url or DATABASE_URL
    engine = create_async_engine(db_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
