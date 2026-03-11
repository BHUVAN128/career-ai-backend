from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


def _get_async_url(url: str) -> str:
    """Convert postgresql:// to postgresql+asyncpg://"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _is_placeholder(url: str) -> bool:
    return not url or "your-project" in url or "password@db" in url


_db_url = (
    "sqlite+aiosqlite:///./career_ai.db"
    if _is_placeholder(settings.DATABASE_URL)
    else _get_async_url(settings.DATABASE_URL)
)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables on startup (dev only — use Alembic for prod)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
