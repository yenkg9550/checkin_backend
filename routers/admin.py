from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from datetime import datetime, date
from typing import Optional
from database import get_db
from models import Attendance, Employee, Override, CheckType
from schemas import AttendanceWithUser, OverrideRequest, EmployeeOut
from utils.jwt_helper import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/report", response_model=list[AttendanceWithUser])
async def daily_report(
    report_date: Optional[date] = None,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """查詢指定日期（預設今天）所有員工打卡紀錄"""
    target = report_date or date.today()
    day_start = datetime.combine(target, datetime.min.time())
    day_end = datetime.combine(target, datetime.max.time())

    result = await db.execute(
        select(Attendance, Employee.display_name, Employee.picture_url)
        .join(Employee, Attendance.employee_id == Employee.id)
        .where(and_(Attendance.checked_at >= day_start, Attendance.checked_at <= day_end))
        .order_by(Attendance.checked_at)
    )
    rows = result.all()

    return [
        AttendanceWithUser(
            **{c.key: getattr(att, c.key) for c in Attendance.__table__.columns},
            display_name=name,
            picture_url=pic,
        )
        for att, name, pic in rows
    ]


@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).order_by(Employee.created_at))
    return result.scalars().all()


@router.patch("/employees/{employee_id}/role")
async def update_role(
    employee_id: int,
    role: str,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """設定員工角色（employee / admin）"""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="員工不存在")
    emp.role = role
    await db.commit()
    return {"success": True}


@router.post("/override")
async def create_override(
    body: OverrideRequest,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """補打卡"""
    override = Override(
        employee_id=body.employee_id,
        check_type=body.check_type,
        override_at=body.override_at,
        reason=body.reason,
        approved_by=int(admin["sub"]),
    )
    db.add(override)

    # 同步寫入一筆 attendance
    att = Attendance(
        employee_id=body.employee_id,
        check_type=body.check_type,
        checked_at=body.override_at,
        is_valid=True,
        note=f"補打卡：{body.reason}",
    )
    db.add(att)
    await db.commit()
    return {"success": True}


@router.delete("/attendance/all")
async def clear_all_attendance(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """清除所有打卡與補打卡記錄"""
    await db.execute(delete(Override))
    await db.execute(delete(Attendance))
    await db.commit()
    return {"success": True, "message": "所有打卡記錄已清除"}
