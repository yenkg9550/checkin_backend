import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, date as date_cls
from database import get_db
from models import Attendance, Employee, CheckType, SystemSettings
from schemas import CheckInRequest, AttendanceRecord
from utils.jwt_helper import get_current_user
from utils.gps import haversine_distance
from config import settings

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
    body: CheckInRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """打卡（上班 / 下班）"""
    employee_id = int(user["sub"])

    # 讀取系統設定（GPS 開關 / 位置 / 半徑）
    cfg_result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    cfg = cfg_result.scalar_one_or_none()
    if not cfg:
        cfg = SystemSettings(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

    # GPS 驗證
    distance_m = None
    is_valid = True
    note = None

    if cfg.gps_enabled:
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

    # 避免同一天重複同類型打卡
    today_start = datetime.combine(date_cls.today(), datetime.min.time())
    today_end = datetime.combine(date_cls.today(), datetime.max.time())
    dup = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                Attendance.check_type == body.check_type,
                Attendance.checked_at >= today_start,
                Attendance.checked_at <= today_end,
                Attendance.is_valid == True,
            )
        )
    )
    if dup.scalar_one_or_none():
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
    day_start = datetime.combine(target, datetime.min.time())
    day_end   = datetime.combine(target, datetime.max.time())
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
    employee_id = int(user["sub"])
    today_start = datetime.combine(date_cls.today(), datetime.min.time())
    today_end = datetime.combine(date_cls.today(), datetime.max.time())
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
