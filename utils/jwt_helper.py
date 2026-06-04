from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from database import get_db

bearer = HTTPBearer()


def create_token(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 無效或已過期")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = decode_token(credentials.credentials)

    # 若是管理員 token，驗證 token_version 防止舊 token 繼續使用
    role = payload.get("role", "")
    if role in ("admin", "super_admin"):
        tv = payload.get("tv")
        if tv is not None:
            from models import AdminUser
            admin = await db.get(AdminUser, int(payload["sub"]))
            if not admin or admin.token_version != tv:
                raise HTTPException(status_code=401, detail="帳號已在其他裝置登入，請重新登入")

    return payload


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="此操作需要超級管理員權限")
    return user
