# CheckIn Backend — FastAPI

LINE 打卡系統的後端 API，使用 FastAPI + SQLAlchemy（async）+ PostgreSQL。

## 技術棧

- Python 3.11+、FastAPI、SQLAlchemy 2.0（async）、asyncpg
- Passlib + bcrypt、python-jose（JWT）、openpyxl

## 快速開始（Docker，本機開發統一用這個）

```bash
cd ..   # 到 checkIn 根目錄
docker compose up -d --build
```

`docker-compose.yml` 會啟動 PostgreSQL（`db` 服務）與本服務（`backend`），並自動把
`DATABASE_URL` 覆蓋成 PostgreSQL 連線字串。

查看 log：

```bash
docker compose logs -f backend
```

## 環境變數

複製 `.env.example` 為 `.env` 並填入：

```
DATABASE_URL=postgresql://user:password@localhost:5432/checkin

LINE_CHANNEL_ID=
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
LIFF_ID=

JWT_SECRET=           # 用 openssl rand -hex 32 產生
JWT_EXPIRE_HOURS=24

SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=

ENABLE_DOCS=false     # 正式環境請關閉
CORS_ORIGINS=https://your-admin-domain.com,https://your-app-domain.com

OFFICE_LAT=23.4617157
OFFICE_LNG=120.2494022
OFFICE_RADIUS_M=200
```

> ⚠️ `.env` 已加入 `.gitignore`，請勿提交真實金鑰。

## 主要 API 路由

### 員工端

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/auth/line` | LINE LIFF 登入 |
| POST | `/api/v1/attendance` | 打卡（上/下班） |
| GET  | `/api/v1/attendance/today` | 今日打卡狀況 |
| GET  | `/api/v1/attendance/me` | 個人打卡紀錄 |
| GET  | `/api/v1/attendance/my-schedule` | 個人班表 |
| POST | `/api/v1/attendance/override-request` | 補打卡申請 |
| GET  | `/api/v1/attendance/override-requests` | 我的補打卡申請 |
| GET  | `/api/v1/attendance/my-leave-types` | 可用假別及餘額 |
| POST | `/api/v1/attendance/leave-request` | 請假申請 |
| GET  | `/api/v1/attendance/leave-requests` | 我的請假申請 |

### 管理端

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/auth/admin-login` | 管理後台登入 |
| GET  | `/api/v1/admin/report` | 每日出勤報表 |
| GET  | `/api/v1/admin/attendance/monthly` | 月份出勤紀錄 |
| GET  | `/api/v1/admin/overrides` | 補打卡紀錄 |
| GET  | `/api/v1/admin/override-requests` | 補打卡申請列表 |
| PATCH | `/api/v1/admin/override-requests/{id}/approve` | 審核通過補打卡 |
| PATCH | `/api/v1/admin/override-requests/{id}/reject` | 駁回補打卡 |
| GET  | `/api/v1/admin/leave-requests` | 請假申請列表 |
| PATCH | `/api/v1/admin/leave-requests/{id}/approve` | 審核通過請假（自動扣假） |
| PATCH | `/api/v1/admin/leave-requests/{id}/reject` | 駁回請假 |
| GET  | `/api/v1/admin/employees` | 員工列表 |
| GET  | `/api/v1/admin/schedule/` | 排班管理 |
| GET  | `/api/v1/admin/salary/payroll` | 薪資單 |
| GET  | `/api/v1/admin/positions` | 職位設定 |
| GET  | `/api/v1/admin/leave-types` | 假別設定 |

完整文件：`http://localhost:8000/docs`（正式環境設 `ENABLE_DOCS=false` 關閉）

## 角色說明

| 角色 | 說明 |
|------|------|
| `super_admin` | 超級管理員，可管理所有後台帳號 |
| `admin` | 一般管理員，由 super_admin 建立 |
| `employee` | 員工，使用 LINE LIFF |

## 安全機制

- JWT Token 驗證（預設 24 小時過期）
- 同帳號重複登入自動踢出
- 管理後台密碼 bcrypt 雜湊
- GPS / IP 打卡範圍驗證
- 補打卡、請假均需管理員審核才生效

## 部署（GitHub Actions → AWS EC2）

`.github/workflows/deploy.yml` 在 push 到 `main` 時自動 SSH 進 EC2 執行 `docker compose up -d --build`。

所需 GitHub Secrets：
- `EC2_HOST`：EC2 公開 IP
- `EC2_SSH_KEY`：SSH 私鑰內容

## 一鍵 Commit & Push

```bash
bash commit.sh
bash commit.sh "自訂訊息"
```
