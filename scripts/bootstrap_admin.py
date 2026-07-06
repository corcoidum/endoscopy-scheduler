from datetime import time
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import ProcedureType, Role, ScheduleCapacity, User
from app.security import hash_password


def seed_default_capacities(db) -> None:
    """창녕 소규모 의원의 기본 오전 내시경 운영 시간표를 샘플로 넣습니다."""

    if db.scalar(select(ScheduleCapacity).limit(1)):
        return

    morning_slots = [
        (time(9, 0), 1),
        (time(9, 30), 2),
        (time(10, 0), 2),
        (time(10, 30), 2),
        (time(11, 0), 1),
    ]
    for weekday in range(0, 6):
        for start_time, max_capacity in morning_slots:
            db.add(ScheduleCapacity(weekday=weekday, start_time=start_time, max_capacity=max_capacity, procedure_type="ANY"))
        db.add(ScheduleCapacity(weekday=weekday, start_time=time(14, 0), max_capacity=1, procedure_type="ANY"))

    # 대장 또는 위·대장 동시 검사는 시간대당 1명 기준을 별도로 둘 수 있게 예시를 남깁니다.
    for weekday in range(0, 6):
        db.add(ScheduleCapacity(weekday=weekday, start_time=time(9, 0), max_capacity=1, procedure_type=ProcedureType.colonoscopy.value))
        db.add(ScheduleCapacity(weekday=weekday, start_time=time(9, 30), max_capacity=1, procedure_type=ProcedureType.both.value))


def main() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == settings.initial_admin_username))
        if not admin:
            admin = User(
                username=settings.initial_admin_username,
                display_name="관리자",
                role=Role.admin.value,
                password_hash=hash_password(settings.initial_admin_password),
                must_change_password=True,
            )
            db.add(admin)
            print(f"created admin user: {settings.initial_admin_username}")
        seed_default_capacities(db)
        db.commit()
        print("bootstrap complete")


if __name__ == "__main__":
    main()
