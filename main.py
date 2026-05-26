from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from routers import auth, attendance, admin, webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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


@app.get("/health")
async def health():
    return {"status": "ok"}
