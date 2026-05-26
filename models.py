from sqlalchemy import String, Float, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
import enum
from database import Base


class Role(str, enum.Enum):
    employee = "employee"
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    attendance: Mapped[list["Attendance"]] = relationship(back_populates="employee")
    overrides: Mapped[list["Override"]] = relationship(back_populates="employee", foreign_keys="[Override.employee_id]")


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    check_type: Mapped[CheckType] = mapped_column(SAEnum(CheckType, native_enum=False))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    gps_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    office_lat: Mapped[float] = mapped_column(Float, default=23.4617157)
    office_lng: Mapped[float] = mapped_column(Float, default=120.2494022)
    office_radius_m: Mapped[float] = mapped_column(Float, default=200.0)


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    check_type: Mapped[CheckType] = mapped_column(SAEnum(CheckType, native_enum=False))
    override_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(300))
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship(back_populates="overrides", foreign_keys=[employee_id])
