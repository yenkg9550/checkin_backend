from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    line_channel_id: str = ""
    liff_id: str = ""

    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    jwt_secret: str = "dev-secret-please-change"
    jwt_expire_hours: int = 24

    office_lat: float = 23.4617157
    office_lng: float = 120.2494022
    office_radius_m: float = 200.0

    database_url: str = "sqlite+aiosqlite:///./checkin.db"
    # Render 提供的 PostgreSQL URL (格式: postgresql://user:pass@host/db)
    # 設定後會覆蓋 database_url
    DATABASE_URL: str = ""

    # 舊版單帳號設定（已棄用，保留向下相容）
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # 超級管理員初始帳密（第一次啟動自動建立，之後請從後台修改密碼）
    super_admin_username: str = "superadmin"
    super_admin_password: str = "changeme123"

    # 正式環境設為 false 關閉 API 文件
    enable_docs: bool = True

    # CORS 允許的來源，逗號分隔；留空則允許全部（開發用）
    cors_origins: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
