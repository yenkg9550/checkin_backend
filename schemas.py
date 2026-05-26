from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from models import CheckType, Role


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


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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


class SystemSettingsOut(BaseModel):
    gps_enabled: bool
    office_lat: float
    office_lng: float
    office_radius_m: float

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    gps_enabled: Optional[bool] = None
    office_lat: Optional[float] = None
    office_lng: Optional[float] = None
    office_radius_m: Optional[float] = None


class EmployeeOut(BaseModel):
    id: int
    line_user_id: str
    display_name: str
    picture_url: Optional[str]
    role: Role
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
