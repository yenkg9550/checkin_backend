from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Employee
from schemas import LineLoginRequest, TokenResponse, UserInfo, AdminLoginRequest, AdminTokenResponse
from utils.line_verify import verify_line_id_token
from utils.jwt_helper import create_token
from config import settings

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


@router.post("/admin-login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLoginRequest):
    """管理後台帳密登入"""
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    token = create_token({"sub": "admin", "role": "admin"})
    return AdminTokenResponse(access_token=token)
