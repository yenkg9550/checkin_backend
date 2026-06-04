from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from database import get_db
from models import Employee, AdminUser
from schemas import LineLoginRequest, TokenResponse, UserInfo, AdminLoginRequest, AdminTokenResponse, AdminUserInfo
from utils.line_verify import verify_line_id_token
from utils.jwt_helper import create_token
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/line", response_model=TokenResponse)
async def login_with_line(body: LineLoginRequest, db: AsyncSession = Depends(get_db)):
    """用 LIFF ID Token 登入，自動建立新員工帳號"""
    payload = await verify_line_id_token(body.id_token)

    line_user_id = payload["sub"]
    display_name = payload.get("name", "未知使用者")
    picture_url = payload.get("picture")

    result = await db.execute(select(Employee).where(Employee.line_user_id == line_user_id))
    employee = result.scalar_one_or_none()

    if not employee:
        # 員工人數上限
        MAX_EMPLOYEES = 20
        count_result = await db.execute(select(Employee))
        employee_count = len(count_result.scalars().all())
        if employee_count >= MAX_EMPLOYEES:
            raise HTTPException(
                status_code=403,
                detail=f"員工人數已達上限（{MAX_EMPLOYEES} 人），請聯絡管理員",
            )

        employee = Employee(
            line_user_id=line_user_id,
            display_name=display_name,
            picture_url=picture_url,
        )
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
    else:
        employee.display_name = display_name
        employee.picture_url = picture_url
        await db.commit()
        await db.refresh(employee)

    token = create_token({"sub": str(employee.id), "role": employee.role.value})

    return TokenResponse(
        access_token=token,
        user=UserInfo(
            id=employee.id,
            line_user_id=employee.line_user_id,
            display_name=employee.display_name,
            picture_url=employee.picture_url,
            role=employee.role,
        ),
    )


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(line_user_id: str, db: AsyncSession = Depends(get_db)):
    """本地開發用登入（僅在 ENABLE_DOCS=true 環境下可用）"""
    if not settings.enable_docs:
        raise HTTPException(status_code=404, detail="Not Found")
    result = await db.execute(select(Employee).where(Employee.line_user_id == line_user_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="員工不存在，請先執行 seed_local.py")
    token = create_token({"sub": str(employee.id), "role": employee.role.value})
    return TokenResponse(
        access_token=token,
        user=UserInfo(
            id=employee.id,
            line_user_id=employee.line_user_id,
            display_name=employee.display_name,
            picture_url=employee.picture_url,
            role=employee.role,
        ),
    )


@router.post("/admin-login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    """管理後台帳密登入（查詢 admin_users 資料表）"""
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == body.username)
    )
    admin = result.scalar_one_or_none()

    if not admin or not pwd_context.verify(body.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    # 遞增 token_version，讓舊 token 全部失效（踢出同帳號其他登入）
    admin.token_version = (admin.token_version or 0) + 1
    await db.commit()
    await db.refresh(admin)

    perms = [p for p in (admin.permissions or "").split(",") if p]
    token = create_token({"sub": str(admin.id), "role": admin.role.value, "tv": admin.token_version})
    return AdminTokenResponse(
        access_token=token,
        user=AdminUserInfo(
            id=admin.id,
            username=admin.username,
            display_name=admin.display_name,
            role=admin.role,
            permissions=perms,
        ),
    )
