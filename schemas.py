from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import Optional
from models import CheckType, Role, AdminRole


# ── Auth ──────────────────────────────────────────────────────────────────────
class LineLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    line_user_id: str
    display_name: str
    picture_url: Optional[str]
    role: Role


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminUserInfo(BaseModel):
    id:           int
    username:     str
    display_name: str
    role:         AdminRole
    permissions:  list[str] = []

    class Config:
        from_attributes = True


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AdminUserInfo


# ── Admin Management ──────────────────────────────────────────────────────────
class AdminCreateRequest(BaseModel):
    username:     str
    password:     str
    display_name: str
    permissions:  list[str] = []   # 例：["attendance", "employees"]

    @field_validator("username")
    @classmethod
    def username_min_length(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("帳號至少 3 個字元")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密碼至少 6 個字元")
        return v


class AdminPasswordUpdate(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pwd_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密碼至少 6 個字元")
        return v


class AdminPermissionsUpdate(BaseModel):
    permissions: list[str]   # 完整覆蓋，例：["attendance", "schedule"]


class AdminUserOut(BaseModel):
    id:           int
    username:     str
    display_name: str
    role:         AdminRole
    permissions:  list[str] = []
    created_at:   datetime

    @classmethod
    def from_orm_with_perms(cls, obj):
        perms = [p for p in (obj.permissions or "").split(",") if p]
        return cls(
            id=obj.id,
            username=obj.username,
            display_name=obj.display_name,
            role=obj.role,
            permissions=perms,
            created_at=obj.created_at,
        )

    class Config:
        from_attributes = True


# ── Attendance ────────────────────────────────────────────────────────────────
class CheckInRequest(BaseModel):
    check_type: CheckType
    lat: Optional[float] = None
    lng: Optional[float] = None


class AttendanceRecord(BaseModel):
    id: int
    check_type: CheckType
    checked_at: datetime
    lat: Optional[float]
    lng: Optional[float]
    distance_m: Optional[float]
    is_valid: bool
    note: Optional[str]

    class Config:
        from_attributes = True


class AttendanceWithUser(AttendanceRecord):
    employee_id: int
    display_name: str
    picture_url: Optional[str]


# ── Admin ─────────────────────────────────────────────────────────────────────
class OverrideRequest(BaseModel):
    employee_id: int
    check_type: CheckType
    override_at: datetime
    reason: str


# 員工自助補打卡申請
class OverrideRequestCreate(BaseModel):
    check_type: CheckType
    override_at: datetime   # 台灣時間（前端送 ISO 字串）
    reason: str


class OverrideRequestOut(BaseModel):
    id: int
    employee_id: int
    display_name: str
    picture_url: Optional[str]
    check_type: CheckType
    override_at: datetime
    reason: str
    status: str
    reject_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OverrideApproveReject(BaseModel):
    reject_reason: Optional[str] = None


class SystemSettingsOut(BaseModel):
    check_mode:     str = "gps"
    gps_enabled:    bool
    office_lat:     float
    office_lng:     float
    office_radius_m: float
    ip_enabled:     bool = False
    allowed_ips:    str  = ""

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    check_mode:     Optional[str]   = None
    gps_enabled:    Optional[bool]  = None
    office_lat:     Optional[float] = None
    office_lng:     Optional[float] = None
    office_radius_m: Optional[float] = None
    ip_enabled:     Optional[bool]  = None
    allowed_ips:    Optional[str]   = None


# ── Schedule ──────────────────────────────────────────────────────────────────
class ShiftCreate(BaseModel):
    name:          str
    start_time:    str   # "HH:MM"
    end_time:      str   # "HH:MM"
    color:         str = "#3b82f6"
    break_minutes: int = 0  # 休息時間（分鐘）

class ShiftOut(ShiftCreate):
    id:         int
    created_at: datetime
    class Config:
        from_attributes = True

class ScheduleCreate(BaseModel):
    employee_id: int
    shift_id:    int
    work_date:   date
    note:        Optional[str] = None
    is_overtime: bool = False

class ScheduleOut(BaseModel):
    id:           int
    employee_id:  int
    shift_id:     int
    work_date:    date
    note:         Optional[str]
    is_overtime:  bool
    employee_name: str
    shift_name:   str
    shift_color:  str
    start_time:   str
    end_time:     str
    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
#  薪資模組 Schemas
# ══════════════════════════════════════════════════════════════════════════════

class SalaryConfigUpdate(BaseModel):
    pay_type:                  Optional[str]   = None
    base_salary:               Optional[float] = None
    overtime_threshold_hours:  Optional[float] = None
    overtime_min_minutes:      Optional[int]   = None
    overtime_rate:             Optional[float] = None
    deduction_type:            Optional[str]   = None
    deduction_per_minute:      Optional[float] = None
    deduction_fixed:           Optional[float] = None
    holiday_rate:              Optional[float] = None
    monthly_work_hours:        Optional[float] = None
    insurance_enabled:         Optional[bool]  = None
    insurance_rate:            Optional[float] = None
    pension_enabled:           Optional[bool]  = None
    pension_rate:              Optional[float] = None

class SalaryConfigOut(BaseModel):
    id:                        int
    employee_id:               int
    pay_type:                  str
    base_salary:               float
    overtime_threshold_hours:  float
    overtime_min_minutes:      int
    overtime_rate:             float
    deduction_type:            str
    deduction_per_minute:      float
    deduction_fixed:           float
    holiday_rate:              float
    monthly_work_hours:        float
    insurance_enabled:         bool
    insurance_rate:            float
    pension_enabled:           bool
    pension_rate:              float
    created_at:                datetime
    updated_at:                datetime
    class Config:
        from_attributes = True

class ShiftSalaryConfigUpdate(BaseModel):
    hourly_rate: float

class ShiftSalaryConfigOut(BaseModel):
    id:          int
    shift_id:    int
    hourly_rate: float
    class Config:
        from_attributes = True

class HolidayCreate(BaseModel):
    date: date
    name: str
    type: str = "custom"   # "national" | "custom"

class HolidayOut(BaseModel):
    id:   int
    date: date
    name: str
    type: str
    class Config:
        from_attributes = True

class PayrollRecordOut(BaseModel):
    id:                  int
    employee_id:         int
    employee_name:       str
    year:                int
    month:               int
    worked_minutes:      int
    overtime_minutes:    int
    late_minutes:        int
    early_leave_minutes: int
    holiday_minutes:     int
    base_pay:            float
    overtime_pay:        float
    holiday_pay:         float
    deductions:          float
    insurance_deduction: float = 0.0
    pension_deduction:   float = 0.0
    total_pay:           float
    anomaly_days:        int = 0
    unscheduled_days:    int = 0
    status:              str
    calculated_at:       datetime
    class Config:
        from_attributes = True

class PayrollDailyDetail(BaseModel):
    work_date:           date
    shift_name:          Optional[str]
    start_time:          Optional[str]
    end_time:            Optional[str]
    clock_in:            Optional[datetime]
    clock_out:           Optional[datetime]
    worked_minutes:      int
    overtime_minutes:    int
    late_minutes:        int
    early_leave_minutes: int
    is_holiday:          bool
    is_overtime:         bool = False
    daily_pay:           float
    has_override:        bool = False


class PayrollDayOverrideIn(BaseModel):
    work_date:           date
    clock_in:            Optional[datetime] = None
    clock_out:           Optional[datetime] = None
    late_minutes:        Optional[int]      = None
    early_leave_minutes: Optional[int]      = None
    overtime_minutes:    Optional[int]      = None
    daily_pay:           Optional[float]    = None
    note:                Optional[str]      = None


class AnomalyDayItem(BaseModel):
    date:      date
    clock_in:  Optional[datetime] = None
    clock_out: Optional[datetime] = None

class EmployeeAnomalyReport(BaseModel):
    employee_id:      int
    employee_name:    str
    anomaly_days:     list[AnomalyDayItem]      # 排班日但缺打卡
    unscheduled_days: list[AnomalyDayItem]       # 有打卡但無排班


class EmployeeOut(BaseModel):
    id: int
    line_user_id: str
    display_name: str
    picture_url: Optional[str]
    role: Role
    is_active: bool
    hire_date: Optional[date] = None
    position_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
