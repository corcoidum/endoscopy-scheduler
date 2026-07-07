from datetime import date, time

from sqlalchemy import select

from app.models import AuditLog, Holiday, ScheduleCapacity
from app.services.schedule_import import parse_schedule_import_csv
from tests.conftest import login


def test_schedule_import_preview_accepts_korean_headers():
    csv_text = """구분,날짜,요일,시작시간,정원,검사종류,활성,설명,내시경운영
정원,,월,09:00,2,ANY,true,,
휴진,2026-08-15,,,,,,광복절 휴진,false
"""

    plan = parse_schedule_import_csv(csv_text)

    assert not plan.has_errors
    assert plan.capacity_count == 1
    assert plan.holiday_count == 1
    assert plan.rows[0].values["weekday"] == 0
    assert plan.rows[1].values["holiday_date"] == date(2026, 8, 15)


def test_schedule_import_preview_blocks_patient_like_columns():
    csv_text = """row_type,patient_name,weekday,start_time,max_capacity
capacity,가상환자,월,09:00,2
"""

    plan = parse_schedule_import_csv(csv_text)

    assert plan.has_errors
    assert "환자/차트/전화번호" in plan.errors[0]


def test_admin_schedule_import_apply_updates_capacity_holiday_and_audit(client, db_session):
    login(client, "admin")
    csv_text = """row_type,date,weekday,start_time,max_capacity,procedure_type,is_active,description,is_endoscopy_available
capacity,,월,09:00,3,ANY,true,,
holiday,2026-08-15,,,,,,광복절 휴진,false
"""

    response = client.post(
        "/admin/capacity/import/apply",
        data={"csv_text": csv_text, "confirm_text": "적용"},
    )

    assert response.status_code == 200
    capacity = db_session.scalar(
        select(ScheduleCapacity).where(
            ScheduleCapacity.weekday == 0,
            ScheduleCapacity.start_time == time(9, 0),
            ScheduleCapacity.procedure_type == "ANY",
        )
    )
    holiday = db_session.scalar(select(Holiday).where(Holiday.holiday_date == date(2026, 8, 15)))
    audit_log = db_session.scalar(select(AuditLog).where(AuditLog.action == "import_schedule_csv"))

    assert capacity.max_capacity == 3
    assert capacity.is_active is True
    assert holiday is not None
    assert holiday.description == "광복절 휴진"
    assert holiday.is_endoscopy_available is False
    assert audit_log is not None
    assert audit_log.changed_fields["summary"]["capacity_updated"] == 1


def test_admin_schedule_import_apply_requires_confirmation(client, db_session):
    login(client, "admin")
    csv_text = """row_type,date,weekday,start_time,max_capacity,procedure_type,is_active,description,is_endoscopy_available
capacity,,월,09:00,3,ANY,true,,
"""

    response = client.post(
        "/admin/capacity/import/apply",
        data={"csv_text": csv_text, "confirm_text": ""},
    )
    capacity = db_session.scalar(
        select(ScheduleCapacity).where(
            ScheduleCapacity.weekday == 0,
            ScheduleCapacity.start_time == time(9, 0),
            ScheduleCapacity.procedure_type == "ANY",
        )
    )
    failed_log = db_session.scalar(select(AuditLog).where(AuditLog.action == "import_schedule_csv"))

    assert response.status_code == 400
    assert capacity.max_capacity == 1
    assert failed_log is not None
    assert failed_log.result == "failed"
