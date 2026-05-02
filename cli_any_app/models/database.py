from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Overridable for tests; production uses settings.db_url via init_db()
DATABASE_URL = "sqlite+aiosqlite:///data/cli_any_app.db"

engine = None
async_session_factory = None


class Base(DeclarativeBase):
    pass


async def init_db(url: str | None = None, *, create_schema: bool = True):
    global engine, async_session_factory
    db_url = url or DATABASE_URL
    engine = create_async_engine(db_url, echo=False)
    if db_url.startswith("sqlite"):
        event.listen(
            engine.sync_engine,
            "connect",
            lambda dbapi_connection, _connection_record: dbapi_connection.execute(
                "PRAGMA foreign_keys=ON"
            ),
        )
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    import cli_any_app.models  # noqa: F401

    if create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
