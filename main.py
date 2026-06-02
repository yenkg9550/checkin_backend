from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select
from passlib.context import CryptContext
from database import init_db, AsyncSessionLocal
from models import AdminUser
from config import settings
from routers import auth, attendance, admin, webhook, schedule, payroll, positions

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def init_super_admin() -> None:
    """啟動時若無 super_admin 則自動建立一個"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AdminUser).where(AdminUser.role == "super_admin")
        )
        if result.scalar_one_or_none():
            return  # 已存在，跳過

        username = settings.super_admin_username
        password = settings.super_admin_password
        super_admin = AdminUser(
            username=username,
            hashed_password=pwd_context.hash(password),
            display_name="超級管理員",
            role="super_admin",
        )
        db.add(super_admin)
        await db.commit()
        print(f"[init] 超級管理員已建立：帳號={username}，請儘速登入後修改密碼！")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_super_admin()
    yield


app = FastAPI(
    title="Line 打卡系統 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(admin.router,      prefix="/api/v1")
app.include_router(webhook.router,    prefix="/api/v1")
app.include_router(schedule.router,   prefix="/api/v1")
app.include_router(payroll.router,    prefix="/api/v1")
app.include_router(positions.router,  prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
