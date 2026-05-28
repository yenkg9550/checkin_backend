# CheckIn Backend — FastAPI

LINE 打卡系統的後端 API，使用 FastAPI + SQLAlchemy（async）+ SQLite（開發）/ PostgreSQL（正式）。

## 技術棧

- Python 3.9+
- FastAPI 0.111
- SQLAlchemy 2.0（async）
- aiosqlite（開發）/ asyncpg（正式）
- Passlib + bcrypt（密碼雜湊）
- python-jose（JWT）
- openpyxl（Excel 匯出）

## 快速開始

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

> 首次啟動時會自動建立資料庫表格，並建立超級管理員帳號（預設 `superadmin` / `changeme123`）。

## 環境變數

在根目錄建立 `.env` 檔（可選，有預設值）：

```
DATABASE_URL=sqlite+aiosqlite:///./checkin.db
SECRET_KEY=your-secret-key
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=changeme123
LINE_CHANNEL_ID=your-line-channel-id
```

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

## 一鍵 Commit 與自動推送

```bash
# 自動偵測變動檔案、產生 commit message，並 git push
bash commit.sh

# 使用自訂 commit message
bash commit.sh "fix(auth): 修正登入驗證邏輯"
```

腳本會自動：
1. 若尚未 `git init` 則自動初始化
2. `git add -A` 加入所有變動
3. 依變動的檔案路徑（models、schemas、auth、admin 等）自動產生 commit message
4. `git commit`
5. 若已設定 remote origin 則自動 `git push`
