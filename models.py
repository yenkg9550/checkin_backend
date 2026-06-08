from __future__ import annotations

from sqlalchemy import String, Float, DateTime, Boolean, ForeignKey, Enum as SAEnum, Date, Integer, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, date, timezone
from typing import Optional
import enum
from database import Base


def _utcnow() -> datetime:
    """回傳 UTC naive datetime，取代已棄用的 datetime.utcnow()。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UTCDateTime(TypeDecorator):
    """
    跨資料庫 DateTime TypeDecorator：
    - PostgreSQL：使用原生 TIMESTAMP（impl=DateTime），直接存 datetime 物件。
    - SQLite：SQLAlchemy 內建 DateTime 以 'YYYY-MM-DD HH:MM:SS'（空格）格式存字串，
      確保字串比較運算（>=, <=）結果正確，不產生 T-format 問題。
    - 寫入：統一轉為 UTC naive datetime 物件。
    - 讀取：容錯舊 T-separator 字串，自動轉回 datetime 物件。
    """
    impl      = DateTime
    cache_ok  = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('T', ' '))
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            # PostgreSQL 可能回傳 timezone-aware，統一轉 naive UTC
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace('T', ' '))
        return value


class Role(str, enum.Enum):
    employee = "employee"
    admin = "admin"


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"


class CheckType(str, enum.Enum):
    clock_in = "clock_in"
    clock_out = "clock_out"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    picture_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[Role] = mapped_column(SAEnum(Role, native_enum=False), default=Role.employee)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    hire_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id", use_alter=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)

    attendance: Mapped[list["Attendance"]] = relationship(back_populates="employee")
    overrides: Mapped[list["Override"]] = relationship(back_populates="employee", foreign_keys="[Override.employee_id]")
    position: Mapped[Optional["Position"]] = relationship(foreign_keys=[position_id])
    leave_types: Mapped[list["EmployeeLeaveType"]] = relationship(back_populates="employee", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    check_type: Mapped[CheckType] = mapped_column(SAEnum(CheckType, native_enum=False))
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="attendance")


class SystemSettings(Base):
    """全域系統設定（單例，id 永遠是 1）"""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # 打卡模式: gps | ip | both | free
    check_mode:     Mapped[str]  = mapped_column(String(10), default="gps")
    # GPS
    gps_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    office_lat: Mapped[float] = mapped_column(Float, default=23.4617157)
    office_lng: Mapped[float] = mapped_column(Float, default=120.2494022)
    office_radius_m: Mapped[float] = mapped_column(Float, default=200.0)
    # IP
    ip_enabled:   Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_ips:  Mapped[str]  = mapped_column(String(1000), default="")  # 逗號分隔


class AdminUser(Base):
    """管理後台帳號（獨立於 LINE 員工帳號）"""
    __tablename__ = "admin_users"

    id:              Mapped[int]           = mapped_column(primary_key=True)
    username:        Mapped[str]           = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str]           = mapped_column(String(200))
    display_name:    Mapped[str]           = mapped_column(String(100))
    role:            Mapped[AdminRole]     = mapped_column(
                                               SAEnum(AdminRole, native_enum=False),
                                               default=AdminRole.admin,
                                           )
    # 逗號分隔的權限清單，例："attendance,employees,schedule"
    # super_admin 忽略此欄位（自動擁有全部權限）
    permissions:     Mapped[str]           = mapped_column(String(300), default="")
    token_version:   Mapped[int]           = mapped_column(Integer, default=1)
    created_at:      Mapped[datetime]      = mapped_column(UTCDateTime, default=_utcnow)


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    check_type: Mapped[CheckType] = mapped_column(SAEnum(CheckType, native_enum=False))
    override_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(String(300))
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    # status: "pending" | "approved" | "rejected"（舊資料預設為 approved）
    status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)

    employee: Mapped["Employee"] = relationship(back_populates="overrides", foreign_keys=[employee_id])


class Shift(Base):
    """班別定義（早班、晚班等）"""
    __tablename__ = "shifts"

    id:             Mapped[int]      = mapped_column(primary_key=True)
    name:           Mapped[str]      = mapped_column(String(50))
    start_time:     Mapped[str]      = mapped_column(String(5))   # "HH:MM"
    end_time:       Mapped[str]      = mapped_column(String(5))   # "HH:MM"
    color:          Mapped[str]      = mapped_column(String(7), default="#3b82f6")  # hex color
    break_minutes:  Mapped[int]      = mapped_column(Integer, default=0)  # 休息時間（分鐘）
    created_at:     Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)

    schedules: Mapped[list["Schedule"]] = relationship(back_populates="shift")


class Schedule(Base):
    """排班記錄：指定員工在特定日期的班別"""
    __tablename__ = "schedules"

    id:          Mapped[int]  = mapped_column(primary_key=True)
    employee_id: Mapped[int]  = mapped_column(ForeignKey("employees.id"))
    shift_id:    Mapped[int]  = mapped_column(ForeignKey("shifts.id"))
    work_date:   Mapped[date] = mapped_column(Date)
    note:        Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    employee: Mapped["Employee"] = relationship()
    shift:    Mapped["Shift"]    = relationship(back_populates="schedules")


# ══════════════════════════════════════════════════════════════════════════════
#  薪資模組
# ══════════════════════════════════════════════════════════════════════════════

class PayType(str, enum.Enum):
    hourly  = "hourly"   # 時薪制（兼職）
    monthly = "monthly"  # 月薪制（正職）

class DeductionType(str, enum.Enum):
    none       = "none"        # 不扣款
    per_minute = "per_minute"  # 按分鐘扣
    fixed      = "fixed"       # 每次固定扣
    both       = "both"        # 兩種都用


class EmployeeSalaryConfig(Base):
    """每位員工的薪資設定"""
    __tablename__ = "employee_salary_configs"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    employee_id:  Mapped[int]           = mapped_column(ForeignKey("employees.id"), unique=True)
    pay_type:     Mapped[PayType]       = mapped_column(SAEnum(PayType, native_enum=False), default=PayType.hourly)
    base_salary:  Mapped[float]         = mapped_column(Float, default=0.0)
    # 加班設定
    overtime_threshold_hours: Mapped[float] = mapped_column(Float, default=8.0)
    overtime_min_minutes:     Mapped[int]   = mapped_column(Integer, default=0)
    overtime_rate:            Mapped[float] = mapped_column(Float, default=1.5)
    # 扣薪設定
    deduction_type:           Mapped[DeductionType] = mapped_column(
                                  SAEnum(DeductionType, native_enum=False), default=DeductionType.per_minute)
    deduction_per_minute:     Mapped[float] = mapped_column(Float, default=0.0)
    deduction_fixed:          Mapped[float] = mapped_column(Float, default=0.0)
    # 特別假日加給
    holiday_rate:             Mapped[float] = mapped_column(Float, default=2.0)
    # 每月標準工時（月薪制換算時薪用，勞基法預設 174 小時）
    monthly_work_hours:       Mapped[float] = mapped_column(Float, default=174.0)
    # 勞健保自動扣除
    insurance_enabled:        Mapped[bool]  = mapped_column(Boolean, default=False)
    insurance_rate:           Mapped[float] = mapped_column(Float, default=6.0)   # 單位 %
    # 勞退自提
    pension_enabled:          Mapped[bool]  = mapped_column(Boolean, default=False)
    pension_rate:             Mapped[float] = mapped_column(Float, default=6.0)   # 單位 %

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow, onupdate=_utcnow)

    employee: Mapped["Employee"] = relationship()


class ShiftSalaryConfig(Base):
    """班別時薪設定（覆蓋員工預設時薪）"""
    __tablename__ = "shift_salary_configs"

    id:          Mapped[int]   = mapped_column(primary_key=True)
    shift_id:    Mapped[int]   = mapped_column(ForeignKey("shifts.id"), unique=True)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0)

    shift: Mapped["Shift"] = relationship()


class Holiday(Base):
    """例假日設定"""
    __tablename__ = "holidays"

    id:   Mapped[int]  = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str]  = mapped_column(String(100))
    type: Mapped[str]  = mapped_column(String(20), default="custom")  # "national" | "custom"


class PayrollRecord(Base):
    """每月薪資單（計算後快取）"""
    __tablename__ = "payroll_records"

    id:           Mapped[int] = mapped_column(primary_key=True)
    employee_id:  Mapped[int] = mapped_column(ForeignKey("employees.id"))
    year:         Mapped[int] = mapped_column(Integer)
    month:        Mapped[int] = mapped_column(Integer)

    # 工時統計（分鐘）
    worked_minutes:      Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes:    Mapped[int] = mapped_column(Integer, default=0)
    late_minutes:        Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    holiday_minutes:     Mapped[int] = mapped_column(Integer, default=0)

    # 薪資金額
    base_pay:      Mapped[float] = mapped_column(Float, default=0.0)
    overtime_pay:  Mapped[float] = mapped_column(Float, default=0.0)
    holiday_pay:   Mapped[float] = mapped_column(Float, default=0.0)
    deductions:          Mapped[float] = mapped_column(Float, default=0.0)
    insurance_deduction: Mapped[float] = mapped_column(Float, default=0.0)
    pension_deduction:   Mapped[float] = mapped_column(Float, default=0.0)
    total_pay:           Mapped[float] = mapped_column(Float, default=0.0)

    anomaly_days:      Mapped[int] = mapped_column(Integer, default=0)  # 只有上班或只有下班的天數
    unscheduled_days:  Mapped[int] = mapped_column(Integer, default=0)  # 有打卡但無排班的天數
    status:     Mapped[str]      = mapped_column(String(20), default="draft")  # draft | finalized
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)

    employee: Mapped["Employee"] = relationship()


# ══════════════════════════════════════════════════════════════════════════════
#  職位模組
# ══════════════════════════════════════════════════════════════════════════════

class Position(Base):
    """職位定義（含薪資預設值）"""
    __tablename__ = "positions"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    name:         Mapped[str]           = mapped_column(String(100), unique=True)
    description:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 薪資預設值（同 EmployeeSalaryConfig）
    pay_type:                  Mapped[PayType]       = mapped_column(SAEnum(PayType, native_enum=False), default=PayType.monthly)
    base_salary:               Mapped[float]         = mapped_column(Float, default=0.0)
    overtime_threshold_hours:  Mapped[float]         = mapped_column(Float, default=8.0)
    overtime_min_minutes:      Mapped[int]           = mapped_column(Integer, default=0)
    overtime_rate:             Mapped[float]         = mapped_column(Float, default=1.5)
    deduction_type:            Mapped[DeductionType] = mapped_column(SAEnum(DeductionType, native_enum=False), default=DeductionType.per_minute)
    deduction_per_minute:      Mapped[float]         = mapped_column(Float, default=0.0)
    deduction_fixed:           Mapped[float]         = mapped_column(Float, default=0.0)
    holiday_rate:              Mapped[float]         = mapped_column(Float, default=2.0)
    monthly_work_hours:        Mapped[float]         = mapped_column(Float, default=174.0)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)

    leave_types: Mapped[list["PositionLeaveType"]] = relationship(back_populates="position", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
#  假別模組
# ══════════════════════════════════════════════════════════════════════════════

class LeaveType(Base):
    """假別定義（全域）"""
    __tablename__ = "leave_types"

    id:         Mapped[int]           = mapped_column(primary_key=True)
    name:       Mapped[str]           = mapped_column(String(100), unique=True)
    is_paid:    Mapped[bool]          = mapped_column(Boolean, default=True)
    max_days:   Mapped[Optional[int]]  = mapped_column(Integer, nullable=True, default=None)  # null = 依勞基法年資計算
    color:      Mapped[str]           = mapped_column(String(7), default="#10b981")
    note:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]      = mapped_column(UTCDateTime, default=_utcnow)

    position_assignments: Mapped[list["PositionLeaveType"]] = relationship(back_populates="leave_type", cascade="all, delete-orphan")
    employee_assignments: Mapped[list["EmployeeLeaveType"]] = relationship(back_populates="leave_type", cascade="all, delete-orphan")


class PositionLeaveType(Base):
    """職位預設假別（多對多關聯）"""
    __tablename__ = "position_leave_types"

    position_id:   Mapped[int] = mapped_column(ForeignKey("positions.id"),   primary_key=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), primary_key=True)

    position:   Mapped["Position"]   = relationship(back_populates="leave_types")
    leave_type: Mapped["LeaveType"]  = relationship(back_populates="position_assignments")


class EmployeeLeaveType(Base):
    """員工個別假別（多對多關聯）"""
    __tablename__ = "employee_leave_types"

    employee_id:   Mapped[int] = mapped_column(ForeignKey("employees.id"),   primary_key=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), primary_key=True)

    employee:   Mapped["Employee"]   = relationship(back_populates="leave_types")
    leave_type: Mapped["LeaveType"]  = relationship(back_populates="employee_assignments")


class PayrollDayOverride(Base):
    """每日薪資手動覆寫（管理員編輯）"""
    __tablename__ = "payroll_day_overrides"

    id:               Mapped[int]           = mapped_column(primary_key=True)
    payroll_record_id:Mapped[int]           = mapped_column(ForeignKey("payroll_records.id"))
    work_date:        Mapped[date]          = mapped_column(Date)
    clock_in:         Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    clock_out:        Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    late_minutes:     Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    early_leave_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overtime_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_pay:        Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note:             Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at:       Mapped[datetime]      = mapped_column(UTCDateTime, default=_utcnow)

    __table_args__ = (UniqueConstraint("payroll_record_id", "work_date"),)


class LeaveRequest(Base):
    """員工請假申請（待管理員審核）"""
    __tablename__ = "leave_requests"

    id:             Mapped[int]           = mapped_column(primary_key=True)
    employee_id:    Mapped[int]           = mapped_column(ForeignKey("employees.id"))
    leave_type_id:  Mapped[int]           = mapped_column(ForeignKey("leave_types.id"))
    start_date:     Mapped[date]          = mapped_column(Date)
    end_date:       Mapped[date]          = mapped_column(Date)
    days:           Mapped[float]         = mapped_column(Float, default=1.0)
    reason:         Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # status: "pending" | "approved" | "rejected"
    status:         Mapped[str]           = mapped_column(String(20), default="pending")
    reject_reason:  Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    leave_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leave_records.id"), nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(UTCDateTime, default=_utcnow)

    employee:   Mapped["Employee"]  = relationship(foreign_keys=[employee_id])
    leave_type: Mapped["LeaveType"] = relationship()


class LeaveRecord(Base):
    """員工請假紀錄（假別使用明細）"""
    __tablename__ = "leave_records"

    id:            Mapped[int]           = mapped_column(primary_key=True)
    employee_id:   Mapped[int]           = mapped_column(ForeignKey("employees.id"))
    leave_type_id: Mapped[int]           = mapped_column(ForeignKey("leave_types.id"))
    leave_date:    Mapped[date]          = mapped_column(Date)
    days:          Mapped[float]         = mapped_column(Float, default=1.0)
    note:          Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at:    Mapped[datetime]      = mapped_column(UTCDateTime, default=_utcnow)

    employee:   Mapped["Employee"]  = relationship()
    leave_type: Mapped["LeaveType"] = relationship()
