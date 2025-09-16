# backend/app/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from .config import DATABASE_URL

# Async engine for normal FastAPI operations
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    pool_recycle=3600,
    max_overflow=10,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Create proper sync database URL by replacing asyncpg with psycopg2
def create_sync_db_url(async_url: str) -> str:
    """Convert async database URL to sync URL"""
    # Handle different possible async URL formats
    if "postgresql+asyncpg://" in async_url:
        return async_url.replace("postgresql+asyncpg://", "postgresql://")
    elif "postgresql://" in async_url and "+asyncpg" not in async_url:
        # Already sync format, but make sure we use psycopg2
        return async_url
    elif "+asyncpg" in async_url:
        return async_url.replace("+asyncpg", "")
    else:
        # Fallback - assume it's already sync
        return async_url

sync_db_url = create_sync_db_url(DATABASE_URL)
sync_engine = create_engine(
    sync_db_url,
    pool_pre_ping=True,
    echo=False,
    pool_size=5,
    max_overflow=10,
    # Additional parameters for better Celery compatibility
    pool_timeout=30,
    pool_recycle=3600
)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def get_infra_sync(request_identifier: str):
    """
    Synchronous database lookup for Celery tasks.
    Returns InfrastructureRequest object or None.
    """
    from .models import InfrastructureRequest
    try:
        with SyncSessionLocal() as session:
            q = session.query(InfrastructureRequest).filter(
                InfrastructureRequest.request_identifier == request_identifier
            )
            return q.one_or_none()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error in get_infra_sync for %s: %s", request_identifier, e)
        return None