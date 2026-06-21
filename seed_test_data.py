"""
測試資料：林佳穎（日班）、張志強（晚班）兩位員工 + 對應班別 / 排班 / 打卡紀錄。

僅供後台「加入測試資料」隱藏頁面（/admin/seed-test-data）使用，
資料內容與原本 checkin.db 內的兩位 demo 員工一致。
"""
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee, Shift, Schedule, Attendance, Role, CheckType

EMPLOYEES = [
    {"line_user_id": "Udemo0000000day00000000000001", "display_name": "林佳穎", "hire_date": "2024-03-01"},
    {"line_user_id": "Udemo0000night000000000000002", "display_name": "張志強", "hire_date": "2024-06-01"},
]

SHIFTS = [
    {"name": "日班", "start_time": "09:00", "end_time": "18:00", "color": "#3b82f6", "break_minutes": 60},
    {"name": "晚班", "start_time": "22:00", "end_time": "07:00", "color": "#6366f1", "break_minutes": 60},
]

# (work_date, 員工1上班, 員工1下班, 員工2上班, 員工2下班) — 時間為 UTC，與原始 checkin.db 紀錄一致
WORK_DAYS = [
    ("2026-05-01", "00:53", "10:00", "13:58", "22:57"),
    ("2026-05-04", "00:57", "10:02", "13:53", "23:07"),
    ("2026-05-05", "00:52", "10:09", "14:03", "22:51"),
    ("2026-05-06", "00:50", "10:01", "13:56", "22:57"),
    ("2026-05-07", "01:06", "10:09", "13:50", "23:07"),
    ("2026-05-08", "00:56", "10:11", "14:07", "23:03"),
    ("2026-05-11", "00:57", "10:07", "14:08", "22:58"),
    ("2026-05-12", "00:50", "10:12", "13:55", "23:03"),
    ("2026-05-13", "01:00", "10:04", "13:54", "22:56"),
    ("2026-05-14", "01:00", "10:01", "13:52", "23:02"),
    ("2026-05-15", "00:53", "10:05", "14:01", "23:09"),
    ("2026-05-18", "00:58", "10:12", "13:51", "23:04"),
    ("2026-05-19", "01:07", "10:01", "14:02", "22:52"),
    ("2026-05-20", "01:07", "10:04", "14:01", "23:08"),
    ("2026-05-21", "00:56", "10:11", "13:52", "22:51"),
    ("2026-05-22", "00:57", "10:12", "13:59", "22:52"),
    ("2026-05-25", "00:57", "10:01", "14:02", "22:58"),
    ("2026-05-26", "01:04", "10:10", "14:01", "22:55"),
    ("2026-05-27", "01:01", "10:05", "13:56", "22:58"),
    ("2026-05-28", "00:52", "10:09", "13:55", "23:07"),
    ("2026-05-29", "00:57", "10:02", "14:04", "23:02"),
]


def _dt(d: str, hm: str) -> datetime:
    h, m = hm.split(":")
    y, mo, da = (int(x) for x in d.split("-"))
    return datetime(y, mo, da, int(h), int(m))


async def seed_demo_employees(db: AsyncSession) -> dict:
    """
    新增測試資料（林佳穎、張志強 + 日班/晚班 + 排班 + 打卡紀錄）。
    若兩位員工皆已存在（以 line_user_id 比對），視為已植入過，不重複新增。
    """
    existing_line_ids = {
        row[0] for row in (await db.execute(select(Employee.line_user_id))).all()
    }
    target_ids = {e["line_user_id"] for e in EMPLOYEES}
    if target_ids.issubset(existing_line_ids):
        return {"success": True, "already_seeded": True, "message": "測試資料已存在，未重複新增"}

    # 員工（已存在則沿用）
    emp_id_by_line = {}
    for e in EMPLOYEES:
        existing = await db.scalar(select(Employee).where(Employee.line_user_id == e["line_user_id"]))
        if existing:
            emp_id_by_line[e["line_user_id"]] = existing.id
            continue
        new_emp = Employee(
            line_user_id=e["line_user_id"],
            display_name=e["display_name"],
            role=Role.employee,
            is_active=True,
            hire_date=date.fromisoformat(e["hire_date"]),
        )
        db.add(new_emp)
        await db.flush()
        emp_id_by_line[e["line_user_id"]] = new_emp.id

    # 班別（已存在則沿用）
    shift_id_by_name = {}
    for s in SHIFTS:
        existing = await db.scalar(select(Shift).where(Shift.name == s["name"]))
        if existing:
            shift_id_by_name[s["name"]] = existing.id
            continue
        new_shift = Shift(**s)
        db.add(new_shift)
        await db.flush()
        shift_id_by_name[s["name"]] = new_shift.id

    emp1_id = emp_id_by_line[EMPLOYEES[0]["line_user_id"]]
    emp2_id = emp_id_by_line[EMPLOYEES[1]["line_user_id"]]
    shift1_id = shift_id_by_name[SHIFTS[0]["name"]]
    shift2_id = shift_id_by_name[SHIFTS[1]["name"]]

    sched_count = 0
    att_count = 0
    for work_date, in1, out1, in2, out2 in WORK_DAYS:
        wd = date.fromisoformat(work_date)
        db.add(Schedule(employee_id=emp1_id, shift_id=shift1_id, work_date=wd))
        db.add(Schedule(employee_id=emp2_id, shift_id=shift2_id, work_date=wd))
        sched_count += 2

        db.add(Attendance(employee_id=emp1_id, check_type=CheckType.clock_in,  checked_at=_dt(work_date, in1),  is_valid=True))
        db.add(Attendance(employee_id=emp1_id, check_type=CheckType.clock_out, checked_at=_dt(work_date, out1), is_valid=True))
        db.add(Attendance(employee_id=emp2_id, check_type=CheckType.clock_in,  checked_at=_dt(work_date, in2),  is_valid=True))
        db.add(Attendance(employee_id=emp2_id, check_type=CheckType.clock_out, checked_at=_dt(work_date, out2), is_valid=True))
        att_count += 4

    await db.commit()
    return {
        "success": True,
        "already_seeded": False,
        "message": f"已新增測試資料：員工 {len(emp_id_by_line)} 位、班別 {len(shift_id_by_name)} 個、排班 {sched_count} 筆、打卡 {att_count} 筆",
        "employees": len(EMPLOYEES),
        "shifts": len(SHIFTS),
        "schedules": sched_count,
        "attendance": att_count,
    }
