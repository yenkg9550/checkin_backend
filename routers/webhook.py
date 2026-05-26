import hmac
import hashlib
import base64
import httpx
import logging
import math
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, date, timezone, timedelta

TZ_TAIPEI = timezone(timedelta(hours=8))

def to_local(dt: datetime) -> datetime:
    """UTC naive datetime → 台灣時間"""
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ_TAIPEI)

from database import get_db
from models import Attendance, Employee, CheckType
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

# 暫存使用者待確認的打卡動作（user_id -> "clock_in" or "clock_out"）
pending_actions: dict = {}


# ── 工具函數 ───────────────────────────────────────────────────────────────────

def verify_signature(body: bytes, signature: str) -> bool:
    secret = settings.line_channel_secret.encode("utf-8")
    hash_ = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def calc_distance(lat1, lng1, lat2, lng2) -> float:
    """Haversine 公式計算兩點距離（公尺）"""
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) *
         math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


async def _post(reply_token: str, messages: list):
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {"replyToken": reply_token, "messages": messages}
    async with httpx.AsyncClient() as client:
        r = await client.post(LINE_REPLY_URL, json=payload, headers=headers)
        if r.status_code != 200:
            logger.error(f"LINE reply failed {r.status_code}: {r.text}")


async def reply_text(reply_token: str, text: str):
    await _post(reply_token, [{"type": "text", "text": text}])


async def reply_location_request(reply_token: str, label: str):
    """請求員工分享位置"""
    await _post(reply_token, [{
        "type": "text",
        "text": f"請分享您的位置以完成{label} 📍\n（需在公司範圍 {int(settings.office_radius_m)} 公尺內）",
        "quickReply": {
            "items": [{
                "type": "action",
                "action": {"type": "location", "label": "📍 分享位置"}
            }]
        }
    }])


def build_checkin_flex(label: str, time_str: str, date_str: str, name: str) -> dict:
    """建立打卡成功 Flex Message 卡片"""
    is_clock_in = label == "上班打卡"
    header_color = "#27ACB2" if is_clock_in else "#FF6B6B"
    icon_text = "🟢" if is_clock_in else "🔴"

    return {
        "type": "flex",
        "altText": f"✅ {label}成功 {time_str}",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "打卡成功 ✓",
                        "color": "#ffffff",
                        "size": "sm",
                        "weight": "bold"
                    }
                ],
                "backgroundColor": header_color,
                "paddingAll": "16px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{icon_text} {label}",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#1a1a1a"
                    },
                    {
                        "type": "text",
                        "text": time_str,
                        "weight": "bold",
                        "size": "3xl",
                        "color": header_color,
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "lg",
                        "color": "#f0f0f0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "員工",
                                        "color": "#aaaaaa",
                                        "size": "sm",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": name,
                                        "wrap": True,
                                        "color": "#333333",
                                        "size": "sm",
                                        "flex": 5,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "日期",
                                        "color": "#aaaaaa",
                                        "size": "sm",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": date_str,
                                        "wrap": True,
                                        "color": "#333333",
                                        "size": "sm",
                                        "flex": 5
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "paddingAll": "20px"
            }
        }
    }


# ── 資料庫查詢 ─────────────────────────────────────────────────────────────────

async def get_employee(line_user_id: str, db: AsyncSession):
    result = await db.execute(
        select(Employee).where(Employee.line_user_id == line_user_id)
    )
    return result.scalars().first()


async def get_today_record(employee_id: int, check_type: CheckType, db: AsyncSession):
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())
    result = await db.execute(
        select(Attendance).where(and_(
            Attendance.employee_id == employee_id,
            Attendance.check_type  == check_type,
            Attendance.checked_at  >= today_start,
            Attendance.checked_at  <= today_end,
        ))
    )
    return result.scalars().first()


async def create_attendance(employee_id: int, check_type: CheckType,
                            lat: float, lng: float, distance: float, db: AsyncSession) -> datetime:
    now = datetime.now()
    att = Attendance(
        employee_id=employee_id,
        check_type=check_type,
        checked_at=now,
        lat=lat,
        lng=lng,
        distance_m=distance,
        is_valid=True,
        note="LINE 選單打卡",
    )
    db.add(att)
    await db.commit()
    return now


# ── Webhook 主處理 ─────────────────────────────────────────────────────────────

@router.post("")
async def line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = await request.json()

    async for db in get_db():
        for event in data.get("events", []):
            event_type  = event.get("type")
            reply_token = event.get("replyToken")
            user_id     = event.get("source", {}).get("userId", "")

            # ── Postback（點選單按鈕）──────────────────────────────────────────
            if event_type == "postback":
                postback_data = event.get("postback", {}).get("data", "")

                if postback_data in ("action=clock_in", "action=clock_out"):
                    check_type = CheckType.clock_in if postback_data == "action=clock_in" else CheckType.clock_out
                    label = "上班打卡" if check_type == CheckType.clock_in else "下班打卡"

                    employee = await get_employee(user_id, db)
                    if not employee:
                        await reply_text(reply_token, "❌ 找不到您的員工資料\n請先透過 LIFF 完成登入")
                        continue

                    # 下班必須先打上班
                    if check_type == CheckType.clock_out:
                        ci = await get_today_record(employee.id, CheckType.clock_in, db)
                        if not ci:
                            await reply_text(reply_token, "⚠️ 您今天尚未打上班卡\n請先完成上班打卡！")
                            continue

                    # 檢查今日是否已打過
                    existing = await get_today_record(employee.id, check_type, db)
                    if existing:
                        t = to_local(existing.checked_at).strftime("%H:%M")
                        await reply_text(reply_token, f"⚠️ 您今天已於 {t} 完成{label}\n一天只能打一次喔！")
                        continue

                    # 暫存動作，請求分享位置
                    pending_actions[user_id] = postback_data.replace("action=", "")
                    await reply_location_request(reply_token, label)

            # ── 位置訊息（員工分享位置後）────────────────────────────────────
            elif event_type == "message":
                msg = event.get("message", {})
                if msg.get("type") != "location":
                    continue

                action = pending_actions.pop(user_id, None)
                if not action:
                    await reply_text(reply_token, "⚠️ 請先從選單點選上班或下班打卡")
                    continue

                lat = msg.get("latitude")
                lng = msg.get("longitude")
                if lat is None or lng is None:
                    await reply_text(reply_token, "❌ 無法取得位置資訊，請重試")
                    continue

                distance = calc_distance(lat, lng, settings.office_lat, settings.office_lng)

                if distance > settings.office_radius_m:
                    await reply_text(
                        reply_token,
                        f"❌ 您距離公司 {int(distance)} 公尺\n需在 {int(settings.office_radius_m)} 公尺內才能打卡"
                    )
                    continue

                check_type = CheckType.clock_in if action == "clock_in" else CheckType.clock_out
                label = "上班打卡" if check_type == CheckType.clock_in else "下班打卡"

                employee = await get_employee(user_id, db)
                if not employee:
                    await reply_text(reply_token, "❌ 找不到員工資料")
                    continue

                now = await create_attendance(employee.id, check_type, lat, lng, distance, db)
                local_now = to_local(now)
                flex_msg = build_checkin_flex(label, local_now.strftime("%H:%M"), local_now.strftime("%Y/%m/%d"), employee.display_name)
                await _post(reply_token, [flex_msg])

            # ── 加好友歡迎 ────────────────────────────────────────────────────
            elif event_type == "follow":
                await reply_text(
                    reply_token,
                    "👋 歡迎加入天天樂打卡系統！\n請使用下方選單進行上下班打卡。"
                )

    return {"status": "ok"}
