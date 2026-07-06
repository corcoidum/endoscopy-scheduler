from sqlalchemy import select

from app.models import AuditLog, User
from tests.conftest import login


def test_login_success_creates_session_and_audit_log(client, db_session):
    response = client.post("/login", data={"username": "staff", "password": "Password!123"}, follow_redirects=False)

    assert response.status_code == 303
    assert "session=" in response.headers["set-cookie"]
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "login")) is not None


def test_login_failure_increments_count(client, db_session):
    response = client.post("/login", data={"username": "staff", "password": "wrong"})
    user = db_session.scalar(select(User).where(User.username == "staff"))

    assert response.status_code == 200
    assert user.failed_login_count == 1


def test_inactive_user_cannot_login(client):
    response = client.post("/login", data={"username": "inactive", "password": "Password!123"})

    assert response.status_code == 200
    assert "로그인 정보를 확인하세요" in response.text


def test_staff_cannot_open_user_management(client):
    login(client, "staff")
    response = client.get("/admin/users")

    assert response.status_code == 403

