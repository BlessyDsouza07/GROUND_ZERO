
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """Create and reuse the asynchronous SQLAlchemy engine."""
    global _engine

    if _engine is None:
        database_url = get_settings().database_url

        # Normalize PostgreSQL URLs for Layer 0's async SQLAlchemy engine.
        if database_url.startswith("postgres://"):
            database_url = (
                "postgresql+asyncpg://"
                + database_url[len("postgres://"):]
            )
        elif database_url.startswith("postgresql://"):
            database_url = (
                "postgresql+asyncpg://"
                + database_url[len("postgresql://"):]
            )
        elif database_url.startswith("postgresql+psycopg2://"):
            database_url = (
                "postgresql+asyncpg://"
                + database_url[len("postgresql+psycopg2://"):]
            )

        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the reusable asynchronous session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session and roll back on errors."""
    factory = get_session_factory()

    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose of pooled connections during application shutdown."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
