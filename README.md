# CheckIn Backend — FastAPI

LINE 打卡系統的後端 API，使用 FastAPI + SQLAlchemy（async）+ PostgreSQL。

## 技術棧

- Python 3.11+
- FastAPI 0.111
- SQLAlchemy 2.0（async）
- asyncpg（PostgreSQL）
- Passlib + bcrypt（密碼雜湊）
- python-jose（JWT）
- openpyxl（Excel 匯出）

## 啟動方式

### 方式一：Docker（推薦）

從專案根目錄執行，一鍵啟動 PostgreSQL + 後端：

```bash
cd /Users/caramel/Desktop/F2E/checkIn
docker compose up --build
```

首次啟動會自動建立資料庫表格與超級管理員帳號。

### 方式二：本地開發

需先自行準備 PostgreSQL，並在 `.env` 設定 `DATABASE_URL`。

```bash
# 1. 建立虛擬環境（第一次才需要）
cd /Users/caramel/Desktop/F2E/checkIn/backend
python3 -m venv venv

# 2. 啟用虛擬環境
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 啟動開發伺服器
uvicorn main:app --reload --port 8000
```

## 環境變數

複製 `.env.example` 為 `.env` 並填入設定：

```
# PostgreSQL 連線（Docker 版已自動注入，本地開發需自行填寫）
DATABASE_URL=postgresql://user:password@localhost:5432/checkin

LINE_CHANNEL_ID=your-line-channel-id
LINE_CHANNEL_SECRET=your-line-channel-secret
LINE_CHANNEL_ACCESS_TOKEN=your-line-channel-access-token

JWT_SECRET=your-secret-key

# 超級管理員初始帳密（首次啟動自動建立）
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=changeme123
```

> 預設管理員帳號：`superadmin` / `changeme123`，請登入後台後立即修改密碼。

## API 路由

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/auth/line` | LINE LIFF 員工登入 |
| POST | `/api/v1/auth/admin-login` | 管理後台登入 |
| GET | `/api/v1/admin/report` | 每日打卡報表 |
| GET | `/api/v1/admin/employees` | 員工列表 |
| GET | `/api/v1/admin/settings` | 取得系統設定 |
| PUT | `/api/v1/admin/settings` | 更新系統設定 |
| GET | `/api/v1/admin/export/monthly` | 匯出月報表（Excel） |
| GET | `/api/v1/admin/admins` | 管理員列表 |
| POST | `/api/v1/admin/admins` | 新增管理員 |
| DELETE | `/api/v1/admin/admins/{id}` | 刪除管理員 |
| PUT | `/api/v1/admin/admins/{id}/password` | 修改管理員密碼 |
| GET | `/health` | 健康檢查 |

## 角色說明

| 角色 | 說明 |
|------|------|
| `super_admin` | 超級管理員，唯一且不可被刪除，可管理所有管理員帳號 |
| `admin` | 一般管理員，由 super_admin 建立，可使用後台所有功能 |
| `employee` | 一般員工，使用 LINE LIFF 打卡 |

