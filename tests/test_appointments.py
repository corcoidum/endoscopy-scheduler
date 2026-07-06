from datetime import date

from sqlalchemy import select

from app.models import AuditLog, EndoscopyAppointment
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
