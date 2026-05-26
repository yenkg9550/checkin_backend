import httpx
from fastapi import HTTPException
from config import settings


async def verify_line_id_token(id_token: str) -> dict:
    """
    向 LINE 驗證 LIFF ID Token，回傳 payload。
    payload 包含: sub (line_user_id), name, picture
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.line.me/oauth2/v2.1/verify",
            data={
                "id_token": id_token,
                "client_id": settings.line_channel_id,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="LINE ID Token 驗證失敗")

    return resp.json()
