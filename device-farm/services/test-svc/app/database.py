# Database Connection Management
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect, text
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

from app.config import settings
from app.models.database import Base

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_task_log_debug_columns)
        logger.info("Database tables created")


def _sync_task_log_debug_columns(sync_conn):
    """Add nullable debug metadata columns for existing task_logs tables."""
    inspector = inspect(sync_conn)
    columns = {column["name"] for column in inspector.get_columns("task_logs")}
    if "event_type" not in columns:
        sync_conn.execute(text("ALTER TABLE task_logs ADD COLUMN event_type VARCHAR(50)"))
    if "line_number" not in columns:
        sync_conn.execute(text("ALTER TABLE task_logs ADD COLUMN line_number INTEGER"))


async def close_db():
    """Close database connection"""
    await engine.dispose()
    logger.info("Database connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Check if database connection is working"""
    try:
        async with engine.connect() as conn:
            # Use text() for safe raw SQL execution
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
