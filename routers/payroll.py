"""
薪資模組 Router
  GET/PUT  /admin/salary/config/{employee_id}   - 員工薪資設定
  GET/PUT  /admin/salary/shift/{shift_id}        - 班別時薪設定
  GET/POST/DELETE /admin/salary/holidays         - 假日管理
  GET/POST /admin/salary/payroll                 - 薪資單列表 & 計算
  GET      /admin/salary/payroll/{record_id}/detail - 每日明細
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import (
    Employee, EmployeeSalaryConfig, ShiftSalaryConfig,
    Holiday, PayrollRecord, Schedule, Shift, Attendance,
    CheckType, PayType, DeductionType, PayrollDayOverride,
)
from schemas import (
    SalaryConfigUpdate, SalaryConfigOut,
    ShiftSalaryConfigUpdate, ShiftSalaryConfigOut,
    HolidayCreate, HolidayOut,
    PayrollRecordOut, PayrollDailyDetail, PayrollDayOverrideIn,
    AnomalyDayItem, EmployeeAnomalyReport,
)
from utils.jwt_helper import require_admin, require_super_admin

router = APIRouter(prefix="/admin/salary", tags=["salary"])

TW_OFFSET = 8  # UTC+8


def utc_to_tw(dt: datetime) -> datetime:
    return dt + timedelta(hours=TW_OFFSET)


def tw_midnight_utc(d: date) -> datetime:
    """Taiwan midnight (00:00 TWN) as UTC datetime"""
    return datetime(d.year, d.month, d.day, 0, 0, 0) - timedelta(hours=TW_OFFSET)


# ── 員工薪資設定 ──────────────────────────────────────────────────────────────

@router.get("/config/{employee_id}", response_model=SalaryConfigOut)
async def get_salary_config(
    employee_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(EmployeeSalaryConfig).where(EmployeeSalaryConfig.employee_id == employee_id)
    )
    if not row:
        # Return defaults without persisting
        raise HTTPException(status_code=404, detail="尚未設定薪資，請先儲存")
    return row


@router.put("/config/{employee_id}", response_model=SalaryConfigOut)
async def upsert_salary_config(
    employee_id: int,
    body: SalaryConfigUpdate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="員工不存在")

    row = await db.scalar(
        select(EmployeeSalaryConfig).where(EmployeeSalaryConfig.employee_id == employee_id)
    )
    if not row:
        row = EmployeeSalaryConfig(employee_id=employee_id)
        db.add(row)

    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(row)
    return row


# ── 班別時薪設定 ──────────────────────────────────────────────────────────────

@router.get("/shift/{shift_id}", response_model=ShiftSalaryConfigOut)
async def get_shift_salary(
    shift_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(ShiftSalaryConfig).where(ShiftSalaryConfig.shift_id == shift_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="尚未設定班別時薪")
    return row


@router.put("/shift/{shift_id}", response_model=ShiftSalaryConfigOut)
async def upsert_shift_salary(
    shift_id: int,
    body: ShiftSalaryConfigUpdate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(ShiftSalaryConfig).where(ShiftSalaryConfig.shift_id == shift_id)
    )
    if not row:
        row = ShiftSalaryConfig(shift_id=shift_id, hourly_rate=body.hourly_rate)
        db.add(row)
    else:
        row.hourly_rate = body.hourly_rate

    await db.commit()
    await db.refresh(row)
    return row


# ── 國定假日資料（固定＋農曆，2024–2027）─────────────────────────────────────

TW_NATIONAL_HOLIDAYS: dict[int, list[tuple[str, str]]] = {
    2024: [
        ("2024-01-01", "開國紀念日"),
        ("2024-02-08", "農曆除夕"),
        ("2024-02-09", "春節"),
        ("2024-02-10", "春節"),
        ("2024-02-11", "春節"),
        ("2024-02-12", "春節（補假）"),
        ("2024-02-13", "春節（補假）"),
        ("2024-02-14", "春節（補假）"),
        ("2024-02-28", "和平紀念日"),
        ("2024-04-04", "兒童節"),
        ("2024-04-05", "清明節"),
        ("2024-05-01", "勞動節"),
        ("2024-06-10", "端午節"),
        ("2024-09-17", "中秋節"),
        ("2024-10-10", "國慶日"),
    ],
    2025: [
        ("2025-01-01", "開國紀念日"),
        ("2025-01-27", "農曆除夕"),
        ("2025-01-28", "春節"),
        ("2025-01-29", "春節"),
        ("2025-01-30", "春節"),
        ("2025-01-31", "春節（補假）"),
        ("2025-02-01", "春節（補假）"),
        ("2025-02-02", "春節（補假）"),
        ("2025-02-28", "和平紀念日"),
        ("2025-04-03", "兒童節（補假）"),
        ("2025-04-04", "兒童節 / 清明節"),
        ("2025-05-01", "勞動節"),
        ("2025-05-31", "端午節"),
        ("2025-10-06", "中秋節"),
        ("2025-10-10", "國慶日"),
    ],
    2026: [
        ("2026-01-01", "開國紀念日"),
        ("2026-02-16", "農曆除夕"),
        ("2026-02-17", "春節"),
        ("2026-02-18", "春節"),
        ("2026-02-19", "春節"),
        ("2026-02-20", "春節（補假）"),
        ("2026-02-21", "春節（補假）"),
        ("2026-02-28", "和平紀念日"),
        ("2026-04-04", "兒童節 / 清明節"),
        ("2026-05-01", "勞動節"),
        ("2026-06-19", "端午節"),
        ("2026-09-25", "中秋節"),
        ("2026-10-10", "國慶日"),
    ],
    2027: [
        ("2027-01-01", "開國紀念日"),
        ("2027-02-05", "農曆除夕"),
        ("2027-02-06", "春節"),
        ("2027-02-07", "春節"),
        ("2027-02-08", "春節"),
        ("2027-02-09", "春節（補假）"),
        ("2027-02-10", "春節（補假）"),
        ("2027-02-28", "和平紀念日"),
        ("2027-04-04", "兒童節"),
        ("2027-04-05", "清明節"),
        ("2027-05-01", "勞動節"),
        ("2027-06-09", "端午節"),
        ("2027-09-15", "中秋節"),
        ("2027-10-10", "國慶日"),
    ],
}


@router.post("/holidays/import-national")
async def import_national_holidays(
    year: int,
    month: Optional[int] = None,   # 指定月份則只匯入該月；省略則全年
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """匯入台灣國定特別假日（已存在的日期跳過）"""
    holidays_data = TW_NATIONAL_HOLIDAYS.get(year)
    if not holidays_data:
        raise HTTPException(400, f"目前僅支援 2024–2027 年，{year} 年資料不存在")

    from datetime import date as date_type
    added = skipped = 0
    for date_str, name in holidays_data:
        d = date_type.fromisoformat(date_str)
        if month and d.month != month:
            continue
        existing = await db.scalar(select(Holiday).where(Holiday.date == d))
        if existing:
            skipped += 1
            continue
        db.add(Holiday(date=d, name=name, type="national"))
        added += 1

    await db.commit()
    return {"added": added, "skipped": skipped}


# ── 假日管理 ──────────────────────────────────────────────────────────────────

@router.get("/holidays", response_model=list[HolidayOut])
async def list_holidays(
    year: int,
    month: Optional[int] = None,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import extract
    q = select(Holiday).where(extract("year", Holiday.date) == year)
    if month:
        q = q.where(extract("month", Holiday.date) == month)
    rows = (await db.execute(q.order_by(Holiday.date))).scalars().all()
    return rows


@router.post("/holidays", response_model=HolidayOut)
async def create_holiday(
    body: HolidayCreate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(Holiday).where(Holiday.date == body.date))
    if existing:
        raise HTTPException(status_code=409, detail="該日期已設為假日")
    h = Holiday(date=body.date, name=body.name, type=body.type)
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    h = await db.get(Holiday, holiday_id)
    if not h:
        raise HTTPException(status_code=404, detail="假日不存在")
    await db.delete(h)
    await db.commit()
    return {"ok": True}


# ── 薪資計算 ──────────────────────────────────────────────────────────────────

def _parse_time(hhmm: str) -> tuple[int, int]:
    h, m = hhmm.split(":")
    return int(h), int(m)


async def _calculate_payroll(
    employee_id: int,
    year: int,
    month: int,
    db: AsyncSession,
) -> PayrollRecord:
    """Core payroll calculation — creates/updates a PayrollRecord."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, "員工不存在")

    cfg = await db.scalar(
        select(EmployeeSalaryConfig).where(EmployeeSalaryConfig.employee_id == employee_id)
    )
    if not cfg:
        raise HTTPException(400, f"員工 {emp.display_name} 尚未設定薪資")

    # Date range (Taiwan dates, but attendance stored as UTC)
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Fetch schedules for the month
    scheds = (await db.execute(
        select(Schedule, Shift)
        .join(Shift, Schedule.shift_id == Shift.id)
        .where(Schedule.employee_id == employee_id)
        .where(Schedule.work_date >= first_day)
        .where(Schedule.work_date <= last_day)
        .order_by(Schedule.work_date)
    )).all()

    # Fetch holidays
    from sqlalchemy import extract
    holiday_dates: set[date] = set(
        (await db.execute(
            select(Holiday.date)
            .where(extract("year", Holiday.date) == year)
            .where(extract("month", Holiday.date) == month)
        )).scalars().all()
    )

    # Fetch attendance in window (UTC range covers the whole month in TW time)
    win_start = tw_midnight_utc(first_day)
    win_end   = tw_midnight_utc(last_day) + timedelta(days=1)
    att_rows  = (await db.execute(
        select(Attendance)
        .where(Attendance.employee_id == employee_id)
        .where(Attendance.checked_at >= win_start)
        .where(Attendance.checked_at < win_end)
        .order_by(Attendance.checked_at)
    )).scalars().all()

    # Index attendance by TW date
    # 同日多筆：clock_in 取最早、clock_out 取最晚，避免重複打卡覆蓋正確紀錄
    att_by_date: dict[date, dict] = {}
    for a in att_rows:
        tw_dt = utc_to_tw(a.checked_at)
        d = tw_dt.date()
        if d not in att_by_date:
            att_by_date[d] = {}
        existing = att_by_date[d].get(a.check_type)
        if existing is None:
            att_by_date[d][a.check_type] = tw_dt
        elif a.check_type == CheckType.clock_in and tw_dt < existing:
            att_by_date[d][a.check_type] = tw_dt   # 最早上班
        elif a.check_type == CheckType.clock_out and tw_dt > existing:
            att_by_date[d][a.check_type] = tw_dt   # 最晚下班

    # 載入此薪資單的覆寫（用於異常判斷）
    rec_existing = await db.scalar(
        select(PayrollRecord).where(
            and_(PayrollRecord.employee_id == employee_id,
                 PayrollRecord.year == year,
                 PayrollRecord.month == month)
        )
    )
    ov_map_calc: dict[date, PayrollDayOverride] = {}
    if rec_existing:
        ov_rows_calc = (await db.execute(
            select(PayrollDayOverride).where(PayrollDayOverride.payroll_record_id == rec_existing.id)
        )).scalars().all()
        ov_map_calc = {ov.work_date: ov for ov in ov_rows_calc}

    # Per-day calculation
    total_worked = total_overtime = total_late = total_early = total_holiday = 0
    total_base = total_ot_pay = total_hol_pay = total_deductions = 0.0
    total_anomaly = 0
    total_unscheduled = 0
    sched_dates = {sched.work_date for sched, _ in scheds}

    threshold_min = int(cfg.overtime_threshold_hours * 60)

    for sched, shift in scheds:
        d = sched.work_date
        is_holiday = d in holiday_dates  # 僅手動設定的假日才計假日薪

        sh, sm = _parse_time(shift.start_time)
        eh, em = _parse_time(shift.end_time)
        shift_start = datetime(d.year, d.month, d.day, sh, sm)
        # Handle overnight shift
        if eh < sh or (eh == sh and em < sm):
            shift_end = datetime(d.year, d.month, d.day, eh, em) + timedelta(days=1)
        else:
            shift_end = datetime(d.year, d.month, d.day, eh, em)
        scheduled_min = int((shift_end - shift_start).total_seconds() / 60)

        # Hourly rate for this shift
        shift_cfg = await db.scalar(
            select(ShiftSalaryConfig).where(ShiftSalaryConfig.shift_id == shift.id)
        )
        if cfg.pay_type == PayType.hourly:
            rate = shift_cfg.hourly_rate if shift_cfg else cfg.base_salary
        else:
            # monthly: 月薪 ÷ 每月標準工時 = 每小時工資
            rate = cfg.base_salary / cfg.monthly_work_hours

        day_att = att_by_date.get(d, {})
        clock_in  = day_att.get(CheckType.clock_in)
        clock_out = day_att.get(CheckType.clock_out)

        # 異常：完全缺席、只有上班、或只有下班（覆寫可補齊）
        ov_c = ov_map_calc.get(d)
        eff_in  = clock_in  or (ov_c.clock_in  if ov_c else None)
        eff_out = clock_out or (ov_c.clock_out if ov_c else None)
        if not eff_in or not eff_out:
            total_anomaly += 1

        if not clock_in:
            continue

        # 跨日班：clock_out 可能是前一晚的下班打卡（時間在 clock_in 之前），捨棄
        if clock_out and clock_out <= clock_in:
            clock_out = None

        # Actual work end
        actual_end   = clock_out if clock_out else shift_end
        actual_start = clock_in

        worked_min = max(0, int((actual_end - actual_start).total_seconds() / 60))
        # 扣除休息時間
        worked_min = max(0, worked_min - shift.break_minutes)
        late_min   = max(0, int((actual_start - shift_start).total_seconds() / 60))
        early_min  = max(0, int((shift_end - actual_end).total_seconds() / 60)) if clock_out else 0
        # 排班標記加班日：全部工時計加班；否則依門檻計算
        if sched.is_overtime:
            ot_min  = worked_min
            reg_min = 0
        elif cfg.overtime_rate > 0:
            over = worked_min - threshold_min
            # 未達最低起算分鐘數，不算加班
            ot_min  = max(0, over) if over >= cfg.overtime_min_minutes else 0
            reg_min = worked_min - ot_min
        else:
            ot_min  = 0
            reg_min = worked_min

        total_worked   += worked_min
        total_late     += late_min
        total_early    += early_min
        total_overtime += ot_min
        if is_holiday:
            total_holiday += worked_min

        # Base pay (per minute)，每筆先四捨五入再累加
        per_min = rate / 60

        if is_holiday and cfg.holiday_rate > 0:
            day_hol = round(worked_min * per_min * cfg.holiday_rate)
            total_hol_pay += day_hol
        else:
            if cfg.overtime_rate > 0:
                day_base = round(reg_min * per_min)
                day_ot   = round(ot_min * per_min * cfg.overtime_rate)
            else:
                # 無加班倍率設定：加班時數仍計入統計，薪資全數算底薪
                day_base = round(worked_min * per_min)
                day_ot   = 0
            total_base   += day_base
            total_ot_pay += day_ot

        # Deductions — 每次扣款也四捨五入
        if (late_min > 0 or early_min > 0) and cfg.deduction_type != DeductionType.none:
            penalty_min = late_min + early_min
            if cfg.deduction_type == DeductionType.per_minute:
                total_deductions += round(penalty_min * cfg.deduction_per_minute)
            elif cfg.deduction_type == DeductionType.fixed:
                total_deductions += round(cfg.deduction_fixed)
            else:  # both
                total_deductions += round(penalty_min * cfg.deduction_per_minute + cfg.deduction_fixed)

    # 有打卡但無排班的天數
    for att_date in att_by_date:
        if att_date not in sched_dates:
            total_unscheduled += 1

    # 月薪制：底薪固定為完整月薪，不因出勤時數不足而減少
    if cfg.pay_type == PayType.monthly:
        total_base = cfg.base_salary

    # 勞健保 & 勞退自提（以底薪為基數）
    insurance_deduction = 0.0
    pension_deduction   = 0.0
    if getattr(cfg, 'insurance_enabled', False):
        insurance_deduction = round(total_base * getattr(cfg, 'insurance_rate', 6.0) / 100)
    if getattr(cfg, 'pension_enabled', False):
        pension_deduction = round(total_base * getattr(cfg, 'pension_rate', 6.0) / 100)
    total_deductions += insurance_deduction + pension_deduction

    total_pay = total_base + total_ot_pay + total_hol_pay - total_deductions

    # Upsert record（已結算的薪資單拒絕重算）
    rec = await db.scalar(
        select(PayrollRecord).where(
            and_(PayrollRecord.employee_id == employee_id,
                 PayrollRecord.year == year,
                 PayrollRecord.month == month)
        )
    )
    if rec and rec.status == "finalized":
        raise HTTPException(400, f"員工 {emp.display_name} {year}/{month} 薪資單已結算，無法重算")
    if not rec:
        rec = PayrollRecord(employee_id=employee_id, year=year, month=month)
        db.add(rec)

    rec.worked_minutes      = total_worked
    rec.overtime_minutes    = total_overtime
    rec.late_minutes        = total_late
    rec.early_leave_minutes = total_early
    rec.holiday_minutes     = total_holiday
    rec.base_pay            = round(total_base)
    rec.overtime_pay        = round(total_ot_pay)
    rec.holiday_pay         = round(total_hol_pay)
    rec.deductions          = round(total_deductions)
    rec.insurance_deduction = round(insurance_deduction)
    rec.pension_deduction   = round(pension_deduction)
    rec.total_pay           = round(total_pay)
    rec.anomaly_days        = total_anomaly
    rec.unscheduled_days    = total_unscheduled
    rec.status              = "draft"
    rec.calculated_at       = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(rec)
    return rec


@router.get("/payroll", response_model=list[PayrollRecordOut])
async def list_payroll(
    year: int,
    month: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(PayrollRecord, Employee)
        .join(Employee, PayrollRecord.employee_id == Employee.id)
        .where(PayrollRecord.year == year)
        .where(PayrollRecord.month == month)
        .order_by(Employee.display_name)
    )).all()
    out = []
    for rec, emp in rows:
        d = PayrollRecordOut(
            id=rec.id, employee_id=rec.employee_id, employee_name=emp.display_name,
            year=rec.year, month=rec.month,
            worked_minutes=rec.worked_minutes, overtime_minutes=rec.overtime_minutes,
            late_minutes=rec.late_minutes, early_leave_minutes=rec.early_leave_minutes,
            holiday_minutes=rec.holiday_minutes,
            base_pay=rec.base_pay, overtime_pay=rec.overtime_pay,
            holiday_pay=rec.holiday_pay, deductions=rec.deductions, total_pay=rec.total_pay,
            anomaly_days=rec.anomaly_days if rec.anomaly_days else 0,
            unscheduled_days=rec.unscheduled_days if rec.unscheduled_days else 0,
            status=rec.status, calculated_at=rec.calculated_at,
        )
        out.append(d)
    return out


@router.post("/payroll/calculate")
async def calculate_payroll(
    year: int,
    month: int,
    employee_ids: Optional[str] = None,   # comma-separated; omit = all
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger calculation for one month. Returns list of results."""
    if employee_ids:
        ids = [int(x) for x in employee_ids.split(",") if x.strip()]
    else:
        ids = list((await db.execute(
            select(Employee.id).where(Employee.is_active == True)
        )).scalars().all())

    results = []
    errors  = []
    for eid in ids:
        try:
            rec = await _calculate_payroll(eid, year, month, db)
            emp = await db.get(Employee, eid)
            results.append({"employee_id": eid, "name": emp.display_name, "total_pay": rec.total_pay})
        except HTTPException as e:
            errors.append({"employee_id": eid, "error": e.detail})

    return {"calculated": results, "errors": errors}


@router.patch("/payroll/{record_id}/finalize")
async def finalize_payroll(
    record_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PayrollRecord, record_id)
    if not rec:
        raise HTTPException(404, "薪資單不存在")
    rec.status = "finalized"
    await db.commit()
    return {"ok": True}


@router.get("/payroll/{record_id}/detail", response_model=list[PayrollDailyDetail])
async def payroll_daily_detail(
    record_id: int,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PayrollRecord, record_id)
    if not rec:
        raise HTTPException(404, "薪資單不存在")

    cfg = await db.scalar(
        select(EmployeeSalaryConfig).where(EmployeeSalaryConfig.employee_id == rec.employee_id)
    )

    year, month = rec.year, rec.month
    first_day = date(year, month, 1)
    last_day  = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)

    scheds = (await db.execute(
        select(Schedule, Shift)
        .join(Shift, Schedule.shift_id == Shift.id)
        .where(Schedule.employee_id == rec.employee_id)
        .where(Schedule.work_date >= first_day)
        .where(Schedule.work_date <= last_day)
        .order_by(Schedule.work_date)
    )).all()

    from sqlalchemy import extract
    holiday_dates: set[date] = set(
        (await db.execute(
            select(Holiday.date)
            .where(extract("year", Holiday.date) == year)
            .where(extract("month", Holiday.date) == month)
        )).scalars().all()
    )

    win_start = tw_midnight_utc(first_day)
    win_end   = tw_midnight_utc(last_day) + timedelta(days=1)
    att_rows  = (await db.execute(
        select(Attendance)
        .where(Attendance.employee_id == rec.employee_id)
        .where(Attendance.checked_at >= win_start)
        .where(Attendance.checked_at < win_end)
    )).scalars().all()

    att_by_date: dict[date, dict] = {}
    for a in att_rows:
        tw_dt = utc_to_tw(a.checked_at)
        d = tw_dt.date()
        if d not in att_by_date:
            att_by_date[d] = {}
        existing = att_by_date[d].get(a.check_type)
        if existing is None:
            att_by_date[d][a.check_type] = tw_dt
        elif a.check_type == CheckType.clock_in and tw_dt < existing:
            att_by_date[d][a.check_type] = tw_dt
        elif a.check_type == CheckType.clock_out and tw_dt > existing:
            att_by_date[d][a.check_type] = tw_dt

    # 載入手動覆寫
    ov_rows = (await db.execute(
        select(PayrollDayOverride).where(PayrollDayOverride.payroll_record_id == record_id)
    )).scalars().all()
    overrides_map: dict[date, PayrollDayOverride] = {ov.work_date: ov for ov in ov_rows}

    details = []
    for sched, shift in scheds:
        d = sched.work_date
        is_holiday = d in holiday_dates  # 僅手動設定的假日才計假日薪 or d.weekday() >= 5

        sh, sm = _parse_time(shift.start_time)
        eh, em = _parse_time(shift.end_time)
        shift_start = datetime(d.year, d.month, d.day, sh, sm)
        if eh < sh or (eh == sh and em < sm):
            shift_end = datetime(d.year, d.month, d.day, eh, em) + timedelta(days=1)
        else:
            shift_end = datetime(d.year, d.month, d.day, eh, em)

        day_att   = att_by_date.get(d, {})
        clock_in  = day_att.get(CheckType.clock_in)
        clock_out = day_att.get(CheckType.clock_out)

        # 跨日班：clock_out 在 clock_in 之前表示是前一晚的殘留，捨棄
        if clock_in and clock_out and clock_out <= clock_in:
            clock_out = None

        worked_min = late_min = early_min = 0
        daily_pay  = 0.0

        ot_min = 0
        if clock_in:
            actual_end = clock_out if clock_out else shift_end
            worked_min = max(0, int((actual_end - clock_in).total_seconds() / 60))
            # 扣除休息時間
            worked_min = max(0, worked_min - shift.break_minutes)
            late_min   = max(0, int((clock_in - shift_start).total_seconds() / 60))
            early_min  = max(0, int((shift_end - actual_end).total_seconds() / 60)) if clock_out else 0

            if cfg:
                shift_cfg = await db.scalar(
                    select(ShiftSalaryConfig).where(ShiftSalaryConfig.shift_id == shift.id)
                )
                rate = (shift_cfg.hourly_rate if shift_cfg else cfg.base_salary) if cfg.pay_type == PayType.hourly else cfg.base_salary / cfg.monthly_work_hours
                per_min = rate / 60
                if sched.is_overtime:
                    ot_min  = worked_min
                    reg_min = 0
                elif cfg.overtime_rate > 0:
                    thr = int(cfg.overtime_threshold_hours * 60)
                    over = worked_min - thr
                    ot_min  = max(0, over) if over >= cfg.overtime_min_minutes else 0
                    reg_min = worked_min - ot_min
                else:
                    ot_min  = 0
                    reg_min = worked_min
                if is_holiday and cfg.holiday_rate > 0:
                    daily_pay = round(worked_min * per_min * cfg.holiday_rate)
                elif cfg.overtime_rate > 0:
                    daily_pay = round(reg_min * per_min) + round(ot_min * per_min * cfg.overtime_rate)
                else:
                    daily_pay = round(worked_min * per_min)

        # 套用手動覆寫
        ov = overrides_map.get(d)
        has_ov = ov is not None
        if ov:
            need_recalc = False
            if ov.clock_in  is not None: clock_in  = ov.clock_in;  need_recalc = True
            if ov.clock_out is not None: clock_out = ov.clock_out; need_recalc = True
            if ov.late_minutes           is not None: late_min  = ov.late_minutes;  need_recalc = False  # explicit override, skip
            if ov.early_leave_minutes    is not None: early_min = ov.early_leave_minutes
            if ov.overtime_minutes       is not None: ot_min    = ov.overtime_minutes

            # 如果覆寫了打卡時間但沒有直接指定薪資，就用新時間重算
            if ov.daily_pay is not None:
                daily_pay = ov.daily_pay
            elif need_recalc and clock_in and cfg:
                actual_end = clock_out if clock_out else shift_end
                worked_min = max(0, int((actual_end - clock_in).total_seconds() / 60))
                worked_min = max(0, worked_min - shift.break_minutes)
                if ov.late_minutes is None:
                    late_min = max(0, int((clock_in - shift_start).total_seconds() / 60))
                if ov.early_leave_minutes is None:
                    early_min = max(0, int((shift_end - actual_end).total_seconds() / 60)) if clock_out else 0
                shift_cfg2 = await db.scalar(
                    select(ShiftSalaryConfig).where(ShiftSalaryConfig.shift_id == shift.id)
                )
                rate2 = (shift_cfg2.hourly_rate if shift_cfg2 else cfg.base_salary) if cfg.pay_type == PayType.hourly else cfg.base_salary / cfg.monthly_work_hours
                per_min2 = rate2 / 60
                if ov.overtime_minutes is None:
                    if sched.is_overtime:
                        ot_min = worked_min
                    elif cfg.overtime_rate > 0:
                        thr2 = int(cfg.overtime_threshold_hours * 60)
                        over2 = worked_min - thr2
                        ot_min = max(0, over2) if over2 >= cfg.overtime_min_minutes else 0
                    else:
                        ot_min = 0
                reg_min2 = worked_min - ot_min
                if is_holiday and cfg.holiday_rate > 0:
                    daily_pay = round(worked_min * per_min2 * cfg.holiday_rate)
                else:
                    daily_pay = round(reg_min2 * per_min2) + round(ot_min * per_min2 * cfg.overtime_rate)

        details.append(PayrollDailyDetail(
            work_date=d,
            shift_name=shift.name,
            start_time=shift.start_time,
            end_time=shift.end_time,
            clock_in=clock_in,
            clock_out=clock_out,
            worked_minutes=worked_min,
            overtime_minutes=ot_min,
            late_minutes=late_min,
            early_leave_minutes=early_min,
            is_holiday=is_holiday,
            is_overtime=sched.is_overtime,
            daily_pay=round(daily_pay),
            has_override=has_ov,
        ))

    return details


@router.get("/anomaly", response_model=list[EmployeeAnomalyReport])
async def get_anomaly_report(
    year:        int,
    month:       int,
    employee_id: Optional[int] = None,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """回傳指定月份各員工的打卡異常明細。"""
    first_day = date(year, month, 1)
    last_day  = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)

    # 員工清單
    emp_q = select(Employee).where(Employee.is_active == True)
    if employee_id:
        emp_q = emp_q.where(Employee.id == employee_id)
    employees = (await db.execute(emp_q.order_by(Employee.display_name))).scalars().all()

    # 出勤視窗（UTC）
    win_start = tw_midnight_utc(first_day)
    win_end   = tw_midnight_utc(last_day) + timedelta(days=1)

    result = []
    for emp in employees:
        # 排班
        scheds = (await db.execute(
            select(Schedule, Shift)
            .join(Shift, Schedule.shift_id == Shift.id)
            .where(Schedule.employee_id == emp.id)
            .where(Schedule.work_date >= first_day)
            .where(Schedule.work_date <= last_day)
        )).all()
        sched_dates = {s.work_date for s, _ in scheds}

        # 出勤
        att_rows = (await db.execute(
            select(Attendance)
            .where(Attendance.employee_id == emp.id)
            .where(Attendance.checked_at >= win_start)
            .where(Attendance.checked_at < win_end)
            .order_by(Attendance.checked_at)
        )).scalars().all()

        att_by_date: dict[date, dict] = {}
        for a in att_rows:
            tw_dt = utc_to_tw(a.checked_at)
            d = tw_dt.date()
            if d not in att_by_date:
                att_by_date[d] = {}
            existing = att_by_date[d].get(a.check_type)
            if existing is None:
                att_by_date[d][a.check_type] = tw_dt
            elif a.check_type == CheckType.clock_in and tw_dt < existing:
                att_by_date[d][a.check_type] = tw_dt
            elif a.check_type == CheckType.clock_out and tw_dt > existing:
                att_by_date[d][a.check_type] = tw_dt

        # 異常：排班但缺上班或下班打卡（覆寫可補齊）
        # 載入覆寫
        rec = await db.scalar(
            select(PayrollRecord).where(
                and_(PayrollRecord.employee_id == emp.id,
                     PayrollRecord.year == year,
                     PayrollRecord.month == month)
            )
        )
        ov_map: dict[date, PayrollDayOverride] = {}
        if rec:
            ov_rows = (await db.execute(
                select(PayrollDayOverride).where(PayrollDayOverride.payroll_record_id == rec.id)
            )).scalars().all()
            ov_map = {ov.work_date: ov for ov in ov_rows}

        anomaly_items: list[AnomalyDayItem] = []
        for sched_date in sorted(sched_dates):
            day_att = att_by_date.get(sched_date, {})
            ov = ov_map.get(sched_date)
            ci = day_att.get(CheckType.clock_in)  or (ov.clock_in  if ov else None)
            co = day_att.get(CheckType.clock_out) or (ov.clock_out if ov else None)
            if not ci or not co:
                anomaly_items.append(AnomalyDayItem(
                    date=sched_date,
                    clock_in=ci,
                    clock_out=co,
                ))

        # 未排班打卡：有出勤但不在排班中
        unscheduled_items: list[AnomalyDayItem] = []
        for att_date in sorted(att_by_date.keys()):
            if att_date not in sched_dates:
                day = att_by_date[att_date]
                unscheduled_items.append(AnomalyDayItem(
                    date=att_date,
                    clock_in=day.get(CheckType.clock_in),
                    clock_out=day.get(CheckType.clock_out),
                ))

        if anomaly_items or unscheduled_items:
            result.append(EmployeeAnomalyReport(
                employee_id=emp.id,
                employee_name=emp.display_name,
                anomaly_days=anomaly_items,
                unscheduled_days=unscheduled_items,
            ))

    return result


@router.put("/payroll/{record_id}/day-override")
async def upsert_day_override(
    record_id: int,
    body: PayrollDayOverrideIn,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PayrollRecord, record_id)
    if not rec:
        raise HTTPException(404, "薪資單不存在")
    existing = await db.scalar(
        select(PayrollDayOverride).where(
            PayrollDayOverride.payroll_record_id == record_id,
            PayrollDayOverride.work_date == body.work_date,
        )
    )
    if existing:
        for k, v in body.dict(exclude={"work_date"}).items():
            setattr(existing, k, v)
    else:
        db.add(PayrollDayOverride(payroll_record_id=record_id, **body.dict()))
    await db.commit()
    return {"success": True}


@router.delete("/payroll/{record_id}/day-override/{work_date}")
async def delete_day_override(
    record_id: int,
    work_date: date,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(PayrollDayOverride).where(
            PayrollDayOverride.payroll_record_id == record_id,
            PayrollDayOverride.work_date == work_date,
        )
    )
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"success": True}
