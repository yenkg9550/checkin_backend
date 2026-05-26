"""
執行方式：python3 setup_rich_menu.py
會自動建立六宮格 Rich Menu 並上傳圖片設為預設
"""
import httpx
import json
import sys

ACCESS_TOKEN = "nLiIqbp717X3PFrKC1McDTUxkR61KeierNXGH1Dlb4zH8rg4/mPmOgQrS866KMSi7F7ftu3Vpb9ZliuQDqTyY9gmhybGGvlbpBVElPEX8hM007v+X1LV95AcOxZhXpDTsca+OzhZ2/94fAzJbkEd+AdB04t89/1O/w1cDnyilFU="

# 你的 LIFF ID（打卡頁）和後台管理網址，按需修改
LIFF_CHECKIN_URL  = "https://liff.line.me/2010192211-jzEBENO5"
LIFF_HISTORY_URL  = "https://liff.line.me/2010192211-jzEBENO5#/history"
ADMIN_URL         = "https://superinnocent-violeta-laggingly.ngrok-free.dev"

IMAGE_PATH = "../checkin/rich-menu/rich_menu_2500x1686.png"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

# ── Step 1：建立 Rich Menu ─────────────────────────────────────────────────────
rich_menu = {
    "size": {"width": 2500, "height": 1686},
    "selected": True,
    "name": "天天樂打卡選單",
    "chatBarText": "打卡選單",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
            "action": {"type": "postback", "label": "上班打卡", "data": "action=clock_in",
                       "displayText": "上班打卡"}
        },
        {
            "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
            "action": {"type": "postback", "label": "下班打卡", "data": "action=clock_out",
                       "displayText": "下班打卡"}
        },
        {
            "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
            "action": {"type": "uri", "label": "打卡記錄", "uri": LIFF_HISTORY_URL}
        },
        {
            "bounds": {"x": 0, "y": 843, "width": 833, "height": 843},
            "action": {"type": "uri", "label": "後台管理", "uri": ADMIN_URL}
        },
        {
            "bounds": {"x": 833, "y": 843, "width": 834, "height": 843},
            "action": {"type": "message", "label": "待新增", "text": "此功能即將推出"}
        },
        {
            "bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
            "action": {"type": "message", "label": "待新增", "text": "此功能即將推出"}
        },
    ]
}

print("📋 Step 1：建立 Rich Menu...")
with httpx.Client() as client:
    r = client.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        json=rich_menu,
    )
    if r.status_code != 200:
        print(f"❌ 建立失敗：{r.text}")
        sys.exit(1)

    rich_menu_id = r.json()["richMenuId"]
    print(f"✅ Rich Menu 建立成功：{rich_menu_id}")

# ── Step 2：上傳圖片 ───────────────────────────────────────────────────────────
print("🖼️  Step 2：上傳圖片...")
with open(IMAGE_PATH, "rb") as f:
    image_data = f.read()

with httpx.Client() as client:
    r = client.post(
        f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "image/png",
        },
        content=image_data,
    )
    if r.status_code != 200:
        print(f"❌ 上傳失敗：{r.text}")
        sys.exit(1)
    print("✅ 圖片上傳成功")

# ── Step 3：設為預設選單 ───────────────────────────────────────────────────────
print("🔗 Step 3：設為預設選單...")
with httpx.Client() as client:
    r = client.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    )
    if r.status_code != 200:
        print(f"❌ 設定失敗：{r.text}")
        sys.exit(1)
    print("✅ 已設為預設選單")

print(f"\n🎉 完成！Rich Menu ID：{rich_menu_id}")
print("所有好友打開聊天室即可看到六宮格選單")
