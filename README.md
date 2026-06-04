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

---

## 啟動方式

### 方式一：本地開發

```bash
# 1. 建立虛擬環境（第一次才需要）
cd backend
python3 -m venv venv

# 2. 啟用虛擬環境
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 啟動開發伺服器
uvicorn main:app --reload --port 8000
```

### 方式二：Docker（本機）

從專案根目錄執行，一鍵啟動 PostgreSQL + 後端：

```bash
cd ..   # 到 checkIn 根目錄
docker compose up -d --build
```

---

## AWS EC2 部署

### 伺服器資訊

> 實際 IP 與金鑰路徑請查閱內部文件，不紀錄於此。

| 項目 | 說明 |
|------|------|
| 平台 | AWS EC2（東京 ap-northeast-1）|
| 使用者 | ubuntu |
| API 文件 | `http://<EC2_IP>:8000/docs`（正式環境請關閉） |

### SSH 連線

```bash
ssh -i <金鑰路徑>.pem ubuntu@<EC2_IP> -o "StrictHostKeyChecking=no"
```

### 首次部署

```bash
# 1. 上傳程式碼到 EC2（在 Mac 終端機執行）
scp -i <金鑰路徑>.pem ~/Desktop/F2E/checkIn/docker-compose.yml ubuntu@<EC2_IP>:~/
scp -i <金鑰路徑>.pem -r ~/Desktop/F2E/checkIn/backend ubuntu@<EC2_IP>:~/backend

# 2. SSH 進入 EC2
ssh -i <金鑰路徑>.pem ubuntu@<EC2_IP> -o "StrictHostKeyChecking=no"

# 3. 啟動服務
cd ~ && docker compose up -d
```

### 更新後端程式碼

每次修改程式碼後，在 **Mac 終端機**執行：

```bash
# 上傳最新程式碼
scp -i <金鑰路徑>.pem -r ~/Desktop/F2E/checkIn/backend ubuntu@<EC2_IP>:~/backend

# SSH 進入 EC2 重新 build
ssh -i <金鑰路徑>.pem ubuntu@<EC2_IP> -o "StrictHostKeyChecking=no"
cd ~ && docker compose up -d --build
```

### 更新管理後台前端（S3）

```bash
# 在 Mac 終端機執行
cd ~/Desktop/F2E/checkIn/admin
npm run build
aws s3 sync dist/ s3://checkin-admin-tw/ --delete
```

### 常用維護指令（在 EC2 上執行）

```bash
# 查看服務狀態
docker compose ps

# 查看後端 logs（即時）
docker compose logs backend -f

# 重啟後端
docker compose restart backend

# 完整重啟
docker compose down && docker compose up -d

# 進入資料庫
docker compose exec -T db psql -U checkin -d checkin
```

---

## 環境變數

複製 `.env.example` 為 `.env` 並填入設定：

```
# PostgreSQL 連線（Docker 版已自動注入，本地開發需自行填寫）
DATABASE_URL=postgresql://user:password@localhost:5432/checkin

LINE_CHANNEL_ID=your-line-channel-id
LINE_CHANNEL_SECRET=your-line-channel-secret
LINE_CHANNEL_ACCESS_TOKEN=your-line-channel-access-token
LIFF_ID=your-liff-id

JWT_SECRET=your-secret-key           # 正式環境請用 openssl rand -hex 32 產生
JWT_EXPIRE_HOURS=24

# 超級管理員初始帳密（首次啟動自動建立，請登入後立即修改密碼）
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=<自訂強密碼>

# 正式環境請關閉 API 文件
ENABLE_DOCS=false

# CORS 允許的來源（正式環境請設定，逗號分隔）
CORS_ORIGINS=https://your-admin-domain.com,https://your-app-domain.com

# GPS 打卡範圍
OFFICE_LAT=23.4617157
OFFICE_LNG=120.2494022
OFFICE_RADIUS_M=200
```

---

## API 路由（主要）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/auth/line` | LINE LIFF 員工登入 |
| POST | `/api/v1/auth/admin-login` | 管理後台登入 |
| GET  | `/api/v1/admin/employees` | 員工列表 |
| GET  | `/api/v1/admin/report` | 每日打卡報表 |
| GET  | `/api/v1/admin/schedule` | 排班管理 |
| GET  | `/api/v1/admin/salary/payroll` | 薪資單列表 |
| POST | `/api/v1/admin/salary/payroll/calculate` | 薪資計算 |
| GET  | `/api/v1/admin/salary/anomaly` | 打卡異常報告 |
| GET  | `/api/v1/admin/positions` | 職位設定 |
| GET  | `/api/v1/admin/leave-types` | 假別設定 |
| GET  | `/api/v1/admin/attendance/monthly` | 月出勤紀錄 |

完整文件請見：`http://<EC2_IP>:8000/docs`（正式環境請設定 `ENABLE_DOCS=false` 關閉）

---

## 角色說明

| 角色 | 說明 |
|------|------|
| `super_admin` | 超級管理員，唯一且不可被刪除，可管理所有管理員帳號 |
| `admin` | 一般管理員，由 super_admin 建立，可使用後台所有功能 |
| `employee` | 一般員工，使用 LINE LIFF 打卡 |

---

## 安全機制

- JWT Token 驗證，預設 24 小時過期
- 同帳號重複登入自動踢出：新登入後舊 token 立即失效，被踢出的裝置會收到提示
- 管理後台密碼使用 bcrypt 加密儲存
- GPS 打卡範圍驗證（可設定半徑）
