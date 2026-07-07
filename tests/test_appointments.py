from datetime import date, timedelta

from sqlalchemy import select

from app.models import AppointmentStatus, AuditLog, EndoscopyAppointment, Holiday, ScheduleCapacity
from tests.conftest import login


BASE_APPOINTMENT = {
    "chart_number": "C20260001",
    "patient_name": "가상환자",
    "sex": "여",
    "age": "67",
    "phone_last4": "1234",
    "appointment_date": "2026-07-06",
    "appointment_time": "09:00",
    "procedure_type": "위내시경",
    "preparation_status": "안내 완료",
}


def create_appointment(client, **overrides):
    data = BASE_APPOINTMENT | overrides
    return client.post("/appointments", data=data, follow_redirects=False)


def test_create_appointment(client, db_session):
    login(client, "staff")
    response = create_appointment(client)

    assert response.status_code == 303
    appointment = db_session.scalar(select(EndoscopyAppointment))
    assert appointment is not None
    assert appointment.version == 1
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "create_appointment")) is not None


def test_create_appointment_splits_endoscopy_and_ultrasound(client, db_session):
    login(client, "staff")
    response = create_appointment(
        client,
        chart_number="C20260002",
        patient_name="초음파가상",
        appointment_time="09:30",
        endoscopy_type="위·대장 동시 검사",
        ultrasound_abdomen="on",
        ultrasound_thyroid="on",
    )

    assert response.status_code == 303
    appointment = db_session.scalar(select(EndoscopyAppointment).where(EndoscopyAppointment.patient.has(chart_number="C20260002")))
    assert appointment.endoscopy_type == "위·대장 동시 검사"
    assert appointment.ultrasound_abdomen is True
    assert appointment.ultrasound_thyroid is True
    assert "초음파" in appointment.procedure_type


def test_duplicate_same_patient_same_day_is_blocked(client, db_session):
    login(client, "staff")
    assert create_appointment(client).status_code == 303
    response = create_appointment(client, appointment_time="09:30")

    assert response.status_code == 400
    assert "동일 날짜 예약" in response.text


def test_capacity_over_limit_is_blocked(client):
    login(client, "staff")
    assert create_appointment(client, chart_number="C1", patient_name="가상A").status_code == 303
    response = create_appointment(client, chart_number="C2", patient_name="가상B")

    assert response.status_code == 400
    assert "정원을 초과" in response.text


def test_update_appointment_and_optimistic_lock(client, db_session):
    login(client, "staff")
    assert create_appointment(client).status_code == 303
    appointment = db_session.scalar(select(EndoscopyAppointment))

    response = client.post(
        f"/appointments/{appointment.id}/edit",
        data=BASE_APPOINTMENT | {"version": "0", "appointment_time": "09:30"},
    )

    assert response.status_code == 409
    assert "다른 사용자가 먼저 수정" in response.text


def test_cancel_appointment(client, db_session):
    login(client, "staff")
    assert create_appointment(client).status_code == 303
    appointment = db_session.scalar(select(EndoscopyAppointment))

    response = client.post(
        f"/appointments/{appointment.id}/cancel",
        data={"version": str(appointment.version), "cancellation_reason": "환자 요청"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(appointment)
    assert appointment.status == "취소"


def test_month_calendar_shows_counts_holiday_and_capacity_warning(client, db_session):
    login(client, "staff")
    assert create_appointment(client, chart_number="C20260011", patient_name="월간가상A", endoscopy_type="위내시경").status_code == 303
    assert create_appointment(
        client,
        chart_number="C20260012",
        patient_name="월간가상B",
        appointment_time="09:30",
        endoscopy_type="대장내시경",
    ).status_code == 303
    capacities = db_session.scalars(select(ScheduleCapacity).where(ScheduleCapacity.weekday == 0)).all()
    for capacity in capacities:
        capacity.max_capacity = 1 if capacity.start_time.hour == 9 and capacity.start_time.minute == 0 else 0
    db_session.add(Holiday(holiday_date=date(2026, 7, 6), description="임시 휴일", is_endoscopy_available=False))
    db_session.commit()

    response = client.get("/calendar/month?month=2026-07")

    assert response.status_code == 200
    assert "월간 예약 현황" in response.text
    assert "2건" in response.text
    assert "위 1 · 대장 1" in response.text
    assert "임시 휴일" in response.text
    assert "정원 초과" in response.text
    assert "/calendar/day?day=2026-07-06" in response.text


def test_today_dashboard_shows_preparation_bowel_prep_and_status_action(client):
    login(client, "staff")
    today = date.today().isoformat()
    assert create_appointment(
        client,
        chart_number="C20260021",
        patient_name="오늘가상B",
        appointment_date=today,
        appointment_time="09:30",
        endoscopy_type="대장내시경",
        preparation_status="미안내",
        bowel_prep_type="수클리어산",
        medication_check_required="on",
        guardian_notice="on",
    ).status_code == 303
    assert create_appointment(
        client,
        chart_number="C20260020",
        patient_name="오늘가상A",
        appointment_date=today,
        appointment_time="09:00",
        endoscopy_type="위내시경",
        preparation_status="안내 완료",
    ).status_code == 303

    response = client.get("/")

    assert response.status_code == 200
    today_list = response.text.split("오늘 검사 목록", maxsplit=1)[1]
    assert today_list.index("09:00") < today_list.index("09:30")
    assert "오늘 검사 목록" in response.text
    assert "대장내시경" in response.text
    assert "미안내" in response.text
    assert "수클리어산" in response.text
    assert "약제" in response.text
    assert "보호자" in response.text
    assert "advance-status" in response.text


def test_today_dashboard_risk_panel_groups_missing_items(client, db_session):
    login(client, "staff")
    today = date.today()
    assert create_appointment(
        client,
        chart_number="C20260031",
        patient_name="준비위험",
        appointment_date=(today + timedelta(days=2)).isoformat(),
        appointment_time="09:00",
        preparation_status="미안내",
    ).status_code == 303
    assert create_appointment(
        client,
        chart_number="C20260032",
        patient_name="약제위험",
        appointment_date=(today + timedelta(days=4)).isoformat(),
        appointment_time="09:00",
        medication_check_required="on",
    ).status_code == 303
    assert create_appointment(
        client,
        chart_number="C20260033",
        patient_name="노쇼위험",
        appointment_date=today.isoformat(),
        appointment_time="09:30",
    ).status_code == 303
    no_show = db_session.scalar(select(EndoscopyAppointment).where(EndoscopyAppointment.patient.has(chart_number="C20260033")))
    no_show.status = AppointmentStatus.no_show.value
    db_session.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert "누락 리스크" in response.text
    assert "준비 안내 미발송 + 임박" in response.text
    assert "약제 확인 필요" in response.text
    assert "노쇼 후 미조치" in response.text
    assert "준비위험" in response.text
    assert "약제위험" in response.text
    assert "노쇼위험" in response.text


def test_appointment_form_groups_required_and_optional_inputs(client):
    login(client, "staff")

    response = client.get("/appointments/new")

    assert response.status_code == 200
    assert "필수 정보" in response.text
    assert "선택 정보" in response.text
    assert "준비/안전 확인" in response.text
    assert response.text.index("필수 정보") < response.text.index("선택 정보") < response.text.index("준비/안전 확인")


def test_cancel_flow_requires_reason_and_confirmation(client):
    login(client, "staff")
    assert create_appointment(client).status_code == 303

    response = client.get("/appointments/1")

    assert response.status_code == 200
    assert 'name="cancellation_reason" required' in response.text
    assert "confirm(" in response.text
    assert "취소 사유 입력 후 버튼을 누르면" in response.text
