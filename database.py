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
    from sqlalchemy import text
    db_url = _get_db_url()
    is_postgres = "postgresql" in db_url
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add is_overtime column to schedules if not yet present
        if is_postgres:
            await conn.execute(text(
                "ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1"
            ))
            await conn.execute(text("ALTER TABLE employee_salary_configs ADD COLUMN IF NOT EXISTS insurance_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
            await conn.execute(text("ALTER TABLE employee_salary_configs ADD COLUMN IF NOT EXISTS insurance_rate FLOAT NOT NULL DEFAULT 6.0"))
            await conn.execute(text("ALTER TABLE employee_salary_configs ADD COLUMN IF NOT EXISTS pension_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
            await conn.execute(text("ALTER TABLE employee_salary_configs ADD COLUMN IF NOT EXISTS pension_rate FLOAT NOT NULL DEFAULT 6.0"))
            await conn.execute(text("ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS insurance_deduction FLOAT NOT NULL DEFAULT 0.0"))
            await conn.execute(text("ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS pension_deduction FLOAT NOT NULL DEFAULT 0.0"))
            await conn.execute(text(
                "ALTER TABLE schedules ADD COLUMN IF NOT EXISTS is_overtime BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            await conn.execute(text(
                "ALTER TABLE employee_salary_configs ADD COLUMN IF NOT EXISTS overtime_min_minutes INTEGER NOT NULL DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE positions ADD COLUMN IF NOT EXISTS overtime_min_minutes INTEGER NOT NULL DEFAULT 0"
            ))
        else:
            for sql in [
                "ALTER TABLE schedules ADD COLUMN is_overtime INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE employee_salary_configs ADD COLUMN overtime_min_minutes INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE positions ADD COLUMN overtime_min_minutes INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    await conn.execute(text(sql))
                except Exception:
                    pass
