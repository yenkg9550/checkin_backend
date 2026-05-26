from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from datetime import datetime, date, timezone, timedelta
from typing import Optional
import io, calendar
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from database import get_db
from models import Attendance, Employee, Override, CheckType, SystemSettings
from schemas import AttendanceWithUser, OverrideRequest, EmployeeOut, SystemSettingsOut, SystemSettingsUpdate
from utils.jwt_helper import require_admin

TZ_TAIPEI = timezone(timedelta(hours=8))

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
        approved_by=int(admin["sub"]) if admin["sub"].isdigit() else None,
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


@router.get("/settings", response_model=SystemSettingsOut)
async def get_settings(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """取得系統設定"""
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = SystemSettings(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@router.put("/settings", response_model=SystemSettingsOut)
async def update_settings(
    body: SystemSettingsUpdate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新系統設定"""
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = SystemSettings(id=1)
        db.add(cfg)
    if body.gps_enabled is not None:
        cfg.gps_enabled = body.gps_enabled
    if body.office_lat is not None:
        cfg.office_lat = body.office_lat
    if body.office_lng is not None:
        cfg.office_lng = body.office_lng
    if body.office_radius_m is not None:
        cfg.office_radius_m = body.office_radius_m
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.get("/export/monthly")
async def export_monthly(
    year:  int,
    month: int,
    admin: dict = Depends(require_admin),
    db:    AsyncSession = Depends(get_db),
):
    """匯出指定年月的打卡記錄為 Excel"""
    # 該月範圍
    last_day = calendar.monthrange(year, month)[1]
    day_start = datetime(year, month, 1)
    day_end   = datetime(year, month, last_day, 23, 59, 59)

    # 查詢
    result = await db.execute(
        select(Attendance, Employee.display_name)
        .join(Employee, Attendance.employee_id == Employee.id)
        .where(and_(Attendance.checked_at >= day_start, Attendance.checked_at <= day_end))
        .order_by(Employee.display_name, Attendance.checked_at)
    )
    rows = result.all()

    # 先按員工分成 clock_in / clock_out 兩個清單
    emp_ins:  dict[str, list] = {}
    emp_outs: dict[str, list] = {}
    for att, name in rows:
        local_dt = att.checked_at.replace(tzinfo=timezone.utc).astimezone(TZ_TAIPEI)
        if att.check_type == CheckType.clock_in:
            emp_ins.setdefault(name, []).append(local_dt)
        else:
            emp_outs.setdefault(name, []).append(local_dt)

    # 以上班時間的日期為主，找該次上班後 24 小時內第一筆下班
    data: dict[str, dict] = {}
    for name, ins in emp_ins.items():
        ins.sort()
        outs = sorted(emp_outs.get(name, []))
        used = set()
        data[name] = {}
        for ci in ins:
            d = ci.date()
            data[name].setdefault(d, {"clock_in": None, "clock_out": None})
            if data[name][d]["clock_in"] is None:
                data[name][d]["clock_in"] = ci
            # 找 ci 之後、24 小時內最近的未用下班紀錄
            for i, co in enumerate(outs):
                if i not in used and co > ci and (co - ci).total_seconds() <= 86400:
                    data[name][d]["clock_out"] = co
                    used.add(i)
                    break

    # 員工列表（查全部，包含沒打卡的）
    emp_result = await db.execute(select(Employee).order_by(Employee.display_name))
    all_employees = [e.display_name for e in emp_result.scalars().all()]

    # ── 建立 Excel ────────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{year}年{month}月打卡記錄"

    # 顏色
    CLR_HEADER  = "1E293B"
    CLR_DATE    = "334155"
    CLR_PRESENT = "D1FAE5"
    CLR_ABSENT  = "FEE2E2"
    CLR_PARTIAL = "FEF3C7"
    CLR_WEEKEND = "F1F5F9"
    CLR_WHITE   = "FFFFFF"

    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]

    # ── 標題行 ────────────────────────────────────────────────────────────────
    headers = ["員工", "日期", "星期", "上班打卡", "下班打卡", "工時", "狀態"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font      = Font(bold=True, color=CLR_WHITE, size=11)
        cell.fill      = PatternFill("solid", fgColor=CLR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border    = border
    ws.row_dimensions[1].height = 22

    # ── 資料行 ────────────────────────────────────────────────────────────────
    row_idx = 2
    for emp_name in all_employees:
        emp_data = data.get(emp_name, {})
        cur = date(year, month, 1)
        end = date(year, month, last_day)
        while cur <= end:
            weekday = cur.weekday()
            is_weekend = weekday >= 5
            rec = emp_data.get(cur)

            ci = rec["clock_in"]  if rec else None
            co = rec["clock_out"] if rec else None

            if is_weekend:
                status, bg = "休", CLR_WEEKEND
            elif ci and co:
                status, bg = "正常", CLR_PRESENT
            elif ci:
                status, bg = "未下班", CLR_PARTIAL
            else:
                status, bg = "未出勤", CLR_ABSENT

            # 計算工時
            work_hours = ""
            if ci and co:
                delta = co - ci
                h2 = int(delta.total_seconds() // 3600)
                m2 = int((delta.total_seconds() % 3600) // 60)
                work_hours = f"{h2}:{m2:02d}"

            fill = PatternFill("solid", fgColor=bg)
            values = [
                emp_name,
                cur.strftime("%Y/%m/%d"),
                WEEKDAY_ZH[weekday],
                ci.strftime("%H:%M") if ci else "—",
                co.strftime("%H:%M") if co else "—",
                work_hours or "—",
                status,
            ]
            aligns = ["left", "center", "center", "center", "center", "center", "center"]
            for col, (val, aln) in enumerate(zip(values, aligns), 1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.fill      = fill
                cell.border    = border
                cell.alignment = Alignment(horizontal=aln, vertical="center")
                if col == 1:
                    cell.font = Font(bold=True, size=10)
                else:
                    cell.font = Font(size=10)
            ws.row_dimensions[row_idx].height = 18
            row_idx += 1
            cur += timedelta(days=1)

    # ── 欄寬 ─────────────────────────────────────────────────────────────────
    col_widths = [18, 14, 6, 12, 12, 8, 8]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # 凍結首行
    ws.freeze_panes = "A2"

    # ── 輸出 ──────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"attendance_{year}_{month:02d}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
