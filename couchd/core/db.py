# couchd/core/db.py

import logging
from contextlib import asynccontextmanager
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from couchd.core.config import settings

log = logging.getLogger(__name__)

# 1. Construct the URL securely from our validated Pydantic settings
# Notice we use 'postgresql+asyncpg' to ensure it's non-blocking!
db_url = URL.create(
    drivername="postgresql+asyncpg",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

# 2. Initialize the Engine and Session Factory
try:
    engine = create_async_engine(db_url, echo=False)
    # expire_on_commit=False is crucial for async discord bots so we can
    # access object attributes after the transaction closes.
    SessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    log.info("Async SQLAlchemy engine initialized successfully.")
except Exception as e:
    log.critical(f"Failed to initialize database engine: {e}")
    raise


class Base(DeclarativeBase):
    pass


# 3. The Async Context Manager (Adapted from your design)
@asynccontextmanager
async def get_session():
    """
    Provides a transactional scope around a series of database operations.
    Automatically commits on success and rolls back on failure.

    Usage:
        async with get_session() as db:
            db.add(new_user)
    """
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        log.error(f"Database transaction failed, rolled back. Error: {e}")
        raise
    finally:
        await session.close()
