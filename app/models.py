from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now_utc() -> datetime:
    return datetime.utcnow()


class Role(StrEnum):
    admin = "admin"
    staff = "staff"
    viewer = "viewer"


class ProcedureType(StrEnum):
    gastroscopy = "위내시경"
    colonoscopy = "대장내시경"
    both = "위·대장 동시 검사"
    abdomen_ultrasound = "복부초음파"
    thyroid_ultrasound = "갑상선초음파"
    carotid_ultrasound = "경동맥초음파"
    cardiac_ultrasound = "심장초음파"


class EndoscopyType(StrEnum):
    none = "내시경 없음"
    gastroscopy = "위내시경"
    colonoscopy = "대장내시경"
    both = "위·대장 동시 검사"


class AppointmentStatus(StrEnum):
    reserved = "예약"
    needs_confirmation = "확인 필요"
    prepared = "준비 완료"
    arrived = "내원"
    in_progress = "검사 진행"
    completed = "검사 완료"
    changed = "변경"
    cancelled = "취소"
    no_show = "노쇼"


class PreparationStatus(StrEnum):
    not_done = "미안내"
    explained = "안내 완료"
    confirmed = "환자 확인"


class BowelPrepType(StrEnum):
    none = ""
    easyprep = "이지프렘"
    suclear = "수클리어산"
    suprep = "수프렙미니에스정"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.staff.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)


class PatientMinimal(Base):
    __tablename__ = "patients_minimal"
    __table_args__ = (UniqueConstraint("chart_number", name="uq_patients_chart_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chart_number: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    patient_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str] = mapped_column(String(10), nullable=False)
    phone_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    appointments: Mapped[list["EndoscopyAppointment"]] = relationship(back_populates="patient")


class EndoscopyAppointment(Base):
    __tablename__ = "endoscopy_appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients_minimal.id"), nullable=False, index=True)
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    appointment_time: Mapped[time] = mapped_column(Time, nullable=False, index=True)
    procedure_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    endoscopy_type: Mapped[str] = mapped_column(String(40), nullable=False, default=EndoscopyType.gastroscopy.value, index=True)
    ultrasound_abdomen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ultrasound_thyroid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ultrasound_carotid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ultrasound_cardiac: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sedation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preparation_status: Mapped[str] = mapped_column(String(20), nullable=False, default=PreparationStatus.not_done.value)
    medication_check_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bowel_prep_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    guardian_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AppointmentStatus.reserved.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    patient: Mapped[PatientMinimal] = relationship(back_populates="appointments")
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])


class ScheduleCapacity(Base):
    __tablename__ = "schedule_capacity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False, index=True)
    max_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    procedure_type: Mapped[str] = mapped_column(String(40), nullable=False, default="ANY")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc, index=True)

    user: Mapped[User | None] = relationship()


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_endoscopy_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    completed_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    anonymize_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    anonymize_phone_last4: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)
