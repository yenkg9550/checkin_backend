from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from datetime import datetime, date as date_type
from typing import Optional
from pydantic import BaseModel

from database import get_db
from models import Position, LeaveType, PositionLeaveType, EmployeeLeaveType, Employee, EmployeeSalaryConfig, LeaveRecord
from utils.jwt_helper import require_admin

router = APIRouter(prefix="/admin", tags=["positions"])


# ─────────────────────────── Schemas ────────────────────────────────────────

class PositionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    pay_type: str = "monthly"
    base_salary: float = 0.0
    overtime_threshold_hours: float = 8.0
    overtime_min_minutes: int = 0
    overtime_rate: float = 1.5
    deduction_type: str = "per_minute"
    deduction_per_minute: float = 0.0
    deduction_fixed: float = 0.0
    holiday_rate: float = 2.0
    monthly_work_hours: float = 174.0
    leave_type_ids: list[int] = []

class PositionUpdate(PositionCreate):
    pass

class LeaveTypeCreate(BaseModel):
    name: str
    is_paid: bool = True
    max_days: Optional[int] = None  # None = 依勞基法年資計算
    color: str = "#10b981"
    note: Optional[str] = None

class LeaveTypeUpdate(LeaveTypeCreate):
    pass

class LeaveRecordCreate(BaseModel):
    leave_type_id: int
    leave_date: date_type
    days: float = 1.0
    note: Optional[str] = None


# ─────────────────────────── Positions ──────────────────────────────────────

@router.get("/positions")
async def list_positions(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Position).order_by(Position.created_at))
    positions = result.scalars().all()
    out = []
    for p in positions:
        lt_res = await db.execute(
            select(PositionLeaveType.leave_type_id).where(PositionLeaveType.position_id == p.id)
        )
        leave_ids = [r[0] for r in lt_res.all()]
        out.append({**_pos_dict(p), "leave_type_ids": leave_ids})
    return out


@router.post("/positions", status_code=201)
async def create_position(
    body: PositionCreate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Position).where(Position.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="職位名稱已存在")
    pos = Position(**{k: v for k, v in body.dict().items() if k != "leave_type_ids"})
    db.add(pos)
    await db.flush()
    for lt_id in body.leave_type_ids:
        db.add(PositionLeaveType(position_id=pos.id, leave_type_id=lt_id))
    await db.commit()
    await db.refresh(pos)
    lt_res = await db.execute(
        select(PositionLeaveType.leave_type_id).where(PositionLeaveType.position_id == pos.id)
    )
    return {**_pos_dict(pos), "leave_type_ids": [r[0] for r in lt_res.all()]}


@router.put("/positions/{position_id}")
async def update_position(
    position_id: int,
    body: PositionUpdate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Position).where(Position.id == position_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="職位不存在")
    for k, v in body.dict().items():
        if k != "leave_type_ids":
            setattr(pos, k, v)
    # 重設假別
    await db.execute(delete(PositionLeaveType).where(PositionLeaveType.position_id == position_id))
    for lt_id in body.leave_type_ids:
        db.add(PositionLeaveType(position_id=position_id, leave_type_id=lt_id))
    await db.commit()
    await db.refresh(pos)
    lt_res = await db.execute(
        select(PositionLeaveType.leave_type_id).where(PositionLeaveType.position_id == pos.id)
    )
    return {**_pos_dict(pos), "leave_type_ids": [r[0] for r in lt_res.all()]}


@router.delete("/positions/{position_id}", status_code=204)
async def delete_position(
    position_id: int,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Position).where(Position.id == position_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="職位不存在")
    # 解除員工的職位綁定
    emp_res = await db.execute(select(Employee).where(Employee.position_id == position_id))
    for emp in emp_res.scalars().all():
        emp.position_id = None
    await db.delete(pos)
    await db.commit()


# ─────────────────────────── Employee position assignment ───────────────────

@router.patch("/employees/{employee_id}/position")
async def set_employee_position(
    employee_id: int,
    position_id: Optional[int] = None,
    apply_salary: bool = False,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """指派員工職位；apply_salary=true 時同步套用職位的薪資預設"""
    emp_res = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = emp_res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="員工不存在")
    emp.position_id = position_id
    if apply_salary and position_id:
        pos_res = await db.execute(select(Position).where(Position.id == position_id))
        pos = pos_res.scalar_one_or_none()
        if pos:
            cfg_res = await db.execute(
                select(EmployeeSalaryConfig).where(EmployeeSalaryConfig.employee_id == employee_id)
            )
            cfg = cfg_res.scalar_one_or_none()
            if not cfg:
                cfg = EmployeeSalaryConfig(employee_id=employee_id)
                db.add(cfg)
            cfg.pay_type = pos.pay_type
            cfg.base_salary = pos.base_salary
            cfg.overtime_threshold_hours = pos.overtime_threshold_hours
            cfg.overtime_min_minutes = pos.overtime_min_minutes
            cfg.overtime_rate = pos.overtime_rate
            cfg.deduction_type = pos.deduction_type
            cfg.deduction_per_minute = pos.deduction_per_minute
            cfg.deduction_fixed = pos.deduction_fixed
            cfg.holiday_rate = pos.holiday_rate
            cfg.monthly_work_hours = pos.monthly_work_hours
    await db.commit()
    return {"success": True}


# ─────────────────────────── Employee leave types ───────────────────────────

@router.get("/employees/{employee_id}/leave-types")
async def get_employee_leave_types(
    employee_id: int,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EmployeeLeaveType.leave_type_id).where(EmployeeLeaveType.employee_id == employee_id)
    )
    return [r[0] for r in result.all()]


@router.put("/employees/{employee_id}/leave-types")
async def set_employee_leave_types(
    employee_id: int,
    leave_type_ids: list[int],
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(EmployeeLeaveType).where(EmployeeLeaveType.employee_id == employee_id))
    for lt_id in leave_type_ids:
        db.add(EmployeeLeaveType(employee_id=employee_id, leave_type_id=lt_id))
    await db.commit()
    return {"success": True}


# ─────────────────────────── Leave Types ────────────────────────────────────

@router.get("/leave-types")
async def list_leave_types(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LeaveType).order_by(LeaveType.created_at))
    return [_lt_dict(lt) for lt in result.scalars().all()]


@router.post("/leave-types", status_code=201)
async def create_leave_type(
    body: LeaveTypeCreate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(LeaveType).where(LeaveType.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="假別名稱已存在")
    lt = LeaveType(**body.dict())
    db.add(lt)
    await db.commit()
    await db.refresh(lt)
    return _lt_dict(lt)


@router.put("/leave-types/{lt_id}")
async def update_leave_type(
    lt_id: int,
    body: LeaveTypeUpdate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LeaveType).where(LeaveType.id == lt_id))
    lt = result.scalar_one_or_none()
    if not lt:
        raise HTTPException(status_code=404, detail="假別不存在")
    for k, v in body.dict().items():
        setattr(lt, k, v)
    await db.commit()
    await db.refresh(lt)
    return _lt_dict(lt)


@router.delete("/leave-types/{lt_id}", status_code=204)
async def delete_leave_type(
    lt_id: int,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LeaveType).where(LeaveType.id == lt_id))
    lt = result.scalar_one_or_none()
    if not lt:
        raise HTTPException(status_code=404, detail="假別不存在")
    await db.delete(lt)
    await db.commit()


# ─────────────────────────── Leave Records ──────────────────────────────────

@router.get("/employees/{employee_id}/leave-records")
async def get_leave_records(
    employee_id: int,
    year: Optional[int] = None,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(LeaveRecord).where(LeaveRecord.employee_id == employee_id)
    if year:
        from sqlalchemy import extract
        q = q.where(extract('year', LeaveRecord.leave_date) == year)
    q = q.order_by(LeaveRecord.leave_date.desc())
    result = await db.execute(q)
    return [_lr_dict(r) for r in result.scalars().all()]


@router.post("/employees/{employee_id}/leave-records", status_code=201)
async def create_leave_record(
    employee_id: int,
    body: LeaveRecordCreate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    record = LeaveRecord(employee_id=employee_id, **body.dict())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _lr_dict(record)


@router.delete("/leave-records/{record_id}", status_code=204)
async def delete_leave_record(
    record_id: int,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LeaveRecord).where(LeaveRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="紀錄不存在")
    await db.delete(record)
    await db.commit()


@router.get("/employees/{employee_id}/leave-balance")
async def get_leave_balance(
    employee_id: int,
    year: int,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """回傳員工在指定年度每個假別的 {max_days, used_days, remaining}"""
    from sqlalchemy import extract
    # 取得員工已分配的假別
    lt_res = await db.execute(
        select(EmployeeLeaveType.leave_type_id).where(EmployeeLeaveType.employee_id == employee_id)
    )
    lt_ids = [r[0] for r in lt_res.all()]
    if not lt_ids:
        return []

    # 取假別資訊
    lts_res = await db.execute(select(LeaveType).where(LeaveType.id.in_(lt_ids)))
    lts = {lt.id: lt for lt in lts_res.scalars().all()}

    # 取年度使用量
    used_res = await db.execute(
        select(LeaveRecord.leave_type_id, func.sum(LeaveRecord.days))
        .where(
            LeaveRecord.employee_id == employee_id,
            extract('year', LeaveRecord.leave_date) == year,
        )
        .group_by(LeaveRecord.leave_type_id)
    )
    used_map = {r[0]: float(r[1]) for r in used_res.all()}

    # 取員工到職日（計算特休年資用）
    emp = await db.get(Employee, employee_id)
    hire_date = emp.hire_date if emp else None

    out = []
    for lt_id in lt_ids:
        lt = lts.get(lt_id)
        if not lt:
            continue
        used = used_map.get(lt_id, 0.0)
        max_d = lt.max_days  # 0 = 無上限

        # 特休：依年資自動計算上限
        if lt.name == "特休" and hire_date:
            max_d = _calc_annual_leave_days(hire_date)

        out.append({
            "leave_type_id": lt_id,
            "name": lt.name,
            "color": lt.color,
            "is_paid": lt.is_paid,
            "max_days": max_d,
            "used_days": used,
            "remaining": (max_d - used) if max_d > 0 else None,
        })
    return out


def _calc_annual_leave_days(hire_date) -> int:
    """依勞基法年資計算特休天數"""
    from datetime import date
    today = date.today()
    delta = today - hire_date
    years = delta.days / 365.25
    if years < 0.5:  return 0
    if years < 1:    return 3
    if years < 2:    return 7
    if years < 3:    return 10
    if years < 5:    return 14
    if years < 10:   return 15
    return min(15 + int(years - 10) + 1, 30)


# ─────────────────────────── Helpers ────────────────────────────────────────

def _pos_dict(p: Position) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "pay_type": p.pay_type, "base_salary": p.base_salary,
        "overtime_threshold_hours": p.overtime_threshold_hours,
        "overtime_min_minutes": p.overtime_min_minutes,
        "overtime_rate": p.overtime_rate, "deduction_type": p.deduction_type,
        "deduction_per_minute": p.deduction_per_minute, "deduction_fixed": p.deduction_fixed,
        "holiday_rate": p.holiday_rate, "monthly_work_hours": p.monthly_work_hours,
        "created_at": p.created_at.isoformat(),
    }

def _lt_dict(lt: LeaveType) -> dict:
    return {
        "id": lt.id, "name": lt.name, "is_paid": lt.is_paid,
        "max_days": lt.max_days, "color": lt.color, "note": lt.note,
        "created_at": lt.created_at.isoformat(),
    }

def _lr_dict(r: LeaveRecord) -> dict:
    return {
        "id": r.id, "employee_id": r.employee_id,
        "leave_type_id": r.leave_type_id,
        "leave_date": r.leave_date.isoformat(),
        "days": r.days, "note": r.note,
        "created_at": r.created_at.isoformat(),
    }
