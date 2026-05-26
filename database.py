from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings


def _get_db_url() -> str:
    """
    優先使用 Render 注入的 DATABASE_URL（格式 postgresql://...），
    自動轉換成 asyncpg 所需的 postgresql+asyncpg://...
    若沒有則退回 settings.database_url（SQLite 本地開發）。
    """
    url = settings.DATABASE_URL or settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_get_db_url(), echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
