from collections.abc import Generator
from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Role, ScheduleCapacity, User
from app.security import hash_password


@pytest.fixture()
def db_session(tmp_path) -> Generator[Session, None, None]:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add(User(username="admin", display_name="관리자", role=Role.admin.value, password_hash=hash_password("Password!123")))
        db.add(User(username="staff", display_name="직원", role=Role.staff.value, password_hash=hash_password("Password!123")))
        db.add(User(username="viewer", display_name="원장", role=Role.viewer.value, password_hash=hash_password("Password!123")))
        db.add(User(username="inactive", display_name="퇴사자", role=Role.staff.value, password_hash=hash_password("Password!123"), is_active=False))
        for weekday in range(7):
            db.add(ScheduleCapacity(weekday=weekday, start_time=time(9, 0), max_capacity=1, procedure_type="ANY"))
            db.add(ScheduleCapacity(weekday=weekday, start_time=time(9, 30), max_capacity=1, procedure_type="ANY"))
        db.commit()
        yield db


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, username: str = "staff", password: str = "Password!123") -> None:
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303

