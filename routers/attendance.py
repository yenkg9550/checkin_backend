import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, date as date_cls, timezone, timedelta
from database import get_db
from models import Attendance, Employee, CheckType, SystemSettings, Schedule, Shift, Override, LeaveRequest, LeaveRecord, EmployeeLeaveType, LeaveType
from schemas import CheckInRequest, AttendanceRecord, OverrideRequestCreate, OverrideRequestOut, LeaveRequestCreate, LeaveRequestOut
from utils.jwt_helper import get_current_user
from utils.gps import haversine_distance
from config import settings


def get_client_ip(request: Request) -> str:
    """取得真實客戶端 IP（支援 Nginx/反向代理）"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


def ip_in_whitelist(client_ip: str, allowed_ips: str) -> bool:
    """檢查 IP 是否在白名單中（支援精確 IP 和 CIDR，如 192.168.1.0/24）"""
    import ipaddress
    if not allowed_ips.strip():
        return False
    try:
        client = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed_ips.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if client in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if client == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/attendance", tags=["attendance"])

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


async def push_checkin_message(line_user_id: str, check_type: CheckType, checked_at: datetime):
    """打卡成功後推送 Flex Message 到 LINE 對話"""
    from datetime import timezone, timedelta
    # 後端存的是 UTC naive datetime，轉成台灣時間（UTC+8）再顯示
    TZ_TAIPEI   = timezone(timedelta(hours=8))
    local_time  = checked_at.replace(tzinfo=timezone.utc).astimezone(TZ_TAIPEI)

    is_clock_in  = check_type == CheckType.clock_in
    label        = "上班打卡" if is_clock_in else "下班打卡"
    header_color = "#10b981" if is_clock_in else "#f59e0b"
    time_str     = local_time.strftime("%H:%M")
    date_str     = local_time.strftime("%Y/%m/%d")

    flex = {
        "type": "flex",
        "altText": f"✅ {label}成功 {time_str}",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": header_color,
                "paddingAll": "16px",
                "contents": [{"type": "text", "text": "打卡成功 ✓", "color": "#ffffff", "size": "sm", "weight": "bold"}],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "contents": [
                    {"type": "text", "text": label, "weight": "bold", "size": "lg", "color": "#1a1a1a"},
                    {"type": "text", "text": time_str, "weight": "bold", "size": "3xl", "color": header_color, "margin": "sm"},
                    {"type": "separator", "margin": "lg", "color": "#f0f0f0"},
                    {
                        "type": "box", "layout": "baseline", "margin": "lg", "spacing": "sm",
                        "contents": [
                            {"type": "text", "text": "日期", "color": "#aaaaaa", "size": "sm", "flex": 2},
                            {"type": "text", "text": date_str, "color": "#333333", "size": "sm", "flex": 5},
                        ],
                    },
                ],
            },
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {settings.line_channel_access_token}",
                    "Content-Type": "application/json",
                },
                json={"to": line_user_id, "messages": [flex]},
            )
            if r.status_code != 200:
                logger.warning(f"LINE push failed {r.status_code}: {r.text}")
    except Exception as e:
        logger.error(f"LINE push error: {e}")


@router.post("", response_model=AttendanceRecord)
async def check_in(
    request: Request,
    body: CheckInRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """打卡（上班 / 下班）"""
    employee_id = int(user["sub"])

    # 讀取系統設定
    cfg_result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    cfg = cfg_result.scalar_one_or_none()
    if not cfg:
        cfg = SystemSettings(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

    distance_m = None
    is_valid = True
    note = None
    mode = getattr(cfg, "check_mode", "gps")

    if mode == "free":
        # 不限制，直接通過
        pass

    elif mode == "gps":
        # 純 GPS 模式
        if body.lat is not None and body.lng is not None:
            distance_m = haversine_distance(body.lat, body.lng, cfg.office_lat, cfg.office_lng)
            if distance_m > cfg.office_radius_m:
                is_valid = False
                note = f"距離公司 {distance_m:.0f} 公尺，超出允許範圍 {cfg.office_radius_m:.0f} 公尺"
        else:
            is_valid = False
            note = "未提供 GPS 座標，請開啟定位權限"
        if not is_valid:
            raise HTTPException(status_code=400, detail=note)

    elif mode == "ip":
        # 純 IP 模式
        client_ip = get_client_ip(request)
        if not ip_in_whitelist(client_ip, getattr(cfg, "allowed_ips", "")):
            raise HTTPException(status_code=400, detail=f"目前網路（{client_ip}）不在允許打卡的範圍內")

    elif mode == "both":
        # GPS 或 IP 任一通過即可
        gps_ok = False
        ip_ok  = False

        if body.lat is not None and body.lng is not None:
            distance_m = haversine_distance(body.lat, body.lng, cfg.office_lat, cfg.office_lng)
            gps_ok = distance_m <= cfg.office_radius_m

        client_ip = get_client_ip(request)
        ip_ok = ip_in_whitelist(client_ip, getattr(cfg, "allowed_ips", ""))

        if not gps_ok and not ip_ok:
            raise HTTPException(status_code=400, detail="GPS 位置及網路 IP 皆不符合打卡條件")

    # 避免同一天重複同類型打卡（以台灣時間 UTC+8 為基準）
    from datetime import timedelta, timezone
    TW = timezone(timedelta(hours=8))
    now_tw = datetime.now(tz=TW)
    tw_today_start = datetime(now_tw.year, now_tw.month, now_tw.day, 0, 0, 0)
    tw_today_end   = datetime(now_tw.year, now_tw.month, now_tw.day, 23, 59, 59)
    # 轉回 UTC naive 存入 DB 的格式
    utc_today_start = tw_today_start - timedelta(hours=8)
    utc_today_end   = tw_today_end   - timedelta(hours=8)
    dup = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                Attendance.check_type == body.check_type,
                Attendance.checked_at >= utc_today_start,
                Attendance.checked_at <= utc_today_end,
                Attendance.is_valid == True,
            )
        )
    )
    if dup.scalars().first():
        raise HTTPException(status_code=409, detail="今日已打過此類型的卡")

    # 取得員工的 LINE user ID
    emp_result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = emp_result.scalars().first()

    record = Attendance(
        employee_id=employee_id,
        check_type=body.check_type,
        lat=body.lat,
        lng=body.lng,
        distance_m=distance_m,
        is_valid=is_valid,
        note=note,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # 推送 LINE 訊息（不阻塞回傳）
    if employee and employee.line_user_id:
        await push_checkin_message(employee.line_user_id, record.check_type, record.checked_at)

    return record


@router.get("/me", response_model=list[AttendanceRecord])
async def my_history(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
):
    """查詢自己的打卡紀錄"""
    employee_id = int(user["sub"])
    result = await db.execute(
        select(Attendance)
        .where(Attendance.employee_id == employee_id)
        .order_by(Attendance.checked_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/me/by-date", response_model=list[AttendanceRecord])
async def my_records_by_date(
    date: str,          # YYYY-MM-DD
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查詢自己指定日期的打卡紀錄"""
    employee_id = int(user["sub"])
    try:
        target = date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式錯誤，請使用 YYYY-MM-DD")
    from datetime import timedelta
    # 台灣時間的一天 = UTC 前一天 16:00 ~ 當天 15:59:59
    day_start = datetime.combine(target, datetime.min.time()) - timedelta(hours=8)
    day_end   = datetime.combine(target, datetime.max.time()) - timedelta(hours=8)
    result = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                Attendance.checked_at >= day_start,
                Attendance.checked_at <= day_end,
            )
        ).order_by(Attendance.checked_at)
    )
    return result.scalars().all()


@router.get("/today", response_model=list[AttendanceRecord])
async def today_status(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查詢今日打卡狀況"""
    from datetime import timezone, timedelta
    employee_id = int(user["sub"])
    TZ_TW = timezone(timedelta(hours=8))
    now_tw = datetime.now(tz=TZ_TW)
    today_start = datetime(now_tw.year, now_tw.month, now_tw.day) - timedelta(hours=8)
    today_end   = datetime(now_tw.year, now_tw.month, now_tw.day, 23, 59, 59) - timedelta(hours=8)
    result = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                Attendance.checked_at >= today_start,
                Attendance.checked_at <= today_end,
            )
        ).order_by(Attendance.checked_at)
    )
    return result.scalars().all()


@router.post("/override-request", status_code=201)
async def submit_override_request(
    body: OverrideRequestCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工提交補打卡申請（待管理員審核）"""
    employee_id = int(user["sub"])
    TZ_TW = timezone(timedelta(hours=8))

    # override_at 前端送台灣時間，轉 UTC 存入
    ov_at = body.override_at
    if ov_at.tzinfo is not None:
        ov_at = ov_at.astimezone(timezone.utc).replace(tzinfo=None)

    # 檢查該日是否已有正式打卡紀錄（同類型）
    # 以台灣日期為基準，換算 UTC 範圍
    tw_date = (ov_at + timedelta(hours=8)).date()
    day_start = datetime.combine(tw_date, datetime.min.time()) - timedelta(hours=8)
    day_end   = datetime.combine(tw_date, datetime.max.time()) - timedelta(hours=8)

    existing = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                Attendance.check_type  == body.check_type,
                Attendance.checked_at  >= day_start,
                Attendance.checked_at  <= day_end,
            )
        )
    )
    if existing.scalars().first():
        type_label = "上班" if body.check_type == CheckType.clock_in else "下班"
        raise HTTPException(
            status_code=409,
            detail=f"{tw_date.strftime('%m/%d')} 已有{type_label}打卡紀錄，無需補打卡"
        )

    # 也檢查是否已有待審核或已通過的補打卡申請（同日同類型）
    dup_req = await db.execute(
        select(Override).where(
            and_(
                Override.employee_id == employee_id,
                Override.check_type  == body.check_type,
                Override.override_at >= day_start,
                Override.override_at <= day_end,
                Override.status.in_(["pending", "approved"]),
            )
        )
    )
    if dup_req.scalars().first():
        type_label = "上班" if body.check_type == CheckType.clock_in else "下班"
        raise HTTPException(
            status_code=409,
            detail=f"{tw_date.strftime('%m/%d')} 已有{type_label}補打卡申請，請勿重複送出"
        )

    override = Override(
        employee_id=employee_id,
        check_type=body.check_type,
        override_at=ov_at,
        reason=body.reason,
        status="pending",
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)
    return {"id": override.id, "status": "pending"}


@router.get("/override-requests", response_model=list[OverrideRequestOut])
async def my_override_requests(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工查詢自己的補打卡申請列表"""
    employee_id = int(user["sub"])
    TZ_TW = timezone(timedelta(hours=8))
    result = await db.execute(
        select(Override, Employee.display_name, Employee.picture_url)
        .join(Employee, Override.employee_id == Employee.id)
        .where(Override.employee_id == employee_id)
        .order_by(Override.created_at.desc())
        .limit(30)
    )
    rows = result.all()
    return [
        OverrideRequestOut(
            id=ov.id,
            employee_id=ov.employee_id,
            display_name=name,
            picture_url=pic,
            check_type=ov.check_type,
            override_at=ov.override_at.replace(tzinfo=timezone.utc).astimezone(TZ_TW),
            reason=ov.reason,
            status=ov.status,
            reject_reason=ov.reject_reason,
            created_at=ov.created_at.replace(tzinfo=timezone.utc).astimezone(TZ_TW),
        )
        for ov, name, pic in rows
    ]


@router.get("/my-leave-types")
async def my_leave_types(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工查詢自己可用的假別及剩餘天數"""
    from sqlalchemy import func, extract
    employee_id = int(user["sub"])
    year = datetime.now(timezone(timedelta(hours=8))).year

    lt_res = await db.execute(
        select(EmployeeLeaveType.leave_type_id).where(EmployeeLeaveType.employee_id == employee_id)
    )
    lt_ids = [r[0] for r in lt_res.all()]
    if not lt_ids:
        return []

    lts_res = await db.execute(select(LeaveType).where(LeaveType.id.in_(lt_ids)))
    lts = {lt.id: lt for lt in lts_res.scalars().all()}

    used_res = await db.execute(
        select(LeaveRecord.leave_type_id, func.sum(LeaveRecord.days))
        .where(
            LeaveRecord.employee_id == employee_id,
            extract('year', LeaveRecord.leave_date) == year,
        )
        .group_by(LeaveRecord.leave_type_id)
    )
    used_map = {r[0]: float(r[1]) for r in used_res.all()}

    emp = await db.get(Employee, employee_id)
    hire_date = emp.hire_date if emp else None

    def _annual_days(hd) -> int:
        from datetime import date as d_cls
        today = d_cls.today()
        years = (today - hd).days / 365.25
        if years < 0.5:  return 0
        if years < 1:    return 3
        if years < 2:    return 7
        if years < 3:    return 10
        if years < 5:    return 14
        if years < 10:   return 15
        return min(15 + int(years - 10) + 1, 30)

    out = []
    for lt_id in lt_ids:
        lt = lts.get(lt_id)
        if not lt:
            continue
        used = used_map.get(lt_id, 0.0)
        max_d = lt.max_days
        if lt.name == "特休" and hire_date:
            max_d = _annual_days(hire_date)
        out.append({
            "leave_type_id": lt_id,
            "name": lt.name,
            "color": lt.color,
            "is_paid": lt.is_paid,
            "max_days": max_d,
            "used_days": used,
            "remaining": round((max_d - used), 1) if max_d and max_d > 0 else None,
        })
    return out


@router.post("/leave-request", status_code=201)
async def submit_leave_request(
    body: LeaveRequestCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工提交請假申請"""
    employee_id = int(user["sub"])

    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="結束日期不能早於開始日期")

    # 確認假別在員工可用清單內
    elt = await db.execute(
        select(EmployeeLeaveType).where(
            EmployeeLeaveType.employee_id == employee_id,
            EmployeeLeaveType.leave_type_id == body.leave_type_id,
        )
    )
    if not elt.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="此假別不在您的可用假別中")

    req = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=body.leave_type_id,
        start_date=body.start_date,
        end_date=body.end_date,
        days=body.days,
        reason=body.reason,
        status="pending",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "status": "pending"}


@router.get("/leave-requests", response_model=list[LeaveRequestOut])
async def my_leave_requests(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工查詢自己的請假申請"""
    employee_id = int(user["sub"])
    result = await db.execute(
        select(LeaveRequest, Employee.display_name, Employee.picture_url, LeaveType.name, LeaveType.color)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(LeaveRequest.employee_id == employee_id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(30)
    )
    TZ_TW = timezone(timedelta(hours=8))
    return [
        LeaveRequestOut(
            id=r.id, employee_id=r.employee_id,
            display_name=name, picture_url=pic,
            leave_type_id=r.leave_type_id,
            leave_type_name=lt_name, leave_type_color=lt_color,
            start_date=r.start_date, end_date=r.end_date,
            days=r.days, reason=r.reason, status=r.status,
            reject_reason=r.reject_reason,
            created_at=r.created_at.replace(tzinfo=timezone.utc).astimezone(TZ_TW),
        )
        for r, name, pic, lt_name, lt_color in result.all()
    ]


@router.get("/my-schedule")
async def my_schedule(
    year: int,
    month: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """員工查詢自己的班表（上/這/下個月）"""
    from datetime import date, timedelta
    employee_id = int(user["sub"])

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    rows = (await db.execute(
        select(Schedule, Shift)
        .join(Shift, Schedule.shift_id == Shift.id)
        .where(Schedule.employee_id == employee_id)
        .where(Schedule.work_date >= first_day)
        .where(Schedule.work_date <= last_day)
        .order_by(Schedule.work_date)
    )).all()

    return [
        {
            "id": sched.id,
            "work_date": sched.work_date.isoformat(),
            "is_overtime": sched.is_overtime,
            "shift": {
                "id": shift.id,
                "name": shift.name,
                "start_time": shift.start_time,
                "end_time": shift.end_time,
                "color": shift.color,
                "break_minutes": shift.break_minutes,
            },
        }
        for sched, shift in rows
    ]
