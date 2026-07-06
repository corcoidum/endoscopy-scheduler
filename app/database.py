from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


settings = get_settings()

# SQLite는 개발 편의를 위한 기본값입니다. 운영은 PostgreSQL URL을 사용합니다.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema_compatibility() -> None:
    """개발 SQLite DB가 이전 MVP 스키마일 때 새 컬럼을 보정합니다.

    운영 PostgreSQL은 Alembic migration으로 관리하고, 이 함수는 로컬 개발 편의를 위해
    SQLite에서만 동작합니다.
    """

    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "endoscopy_appointments" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("endoscopy_appointments")}
    statements = {
        "endoscopy_type": "ALTER TABLE endoscopy_appointments ADD COLUMN endoscopy_type VARCHAR(40) NOT NULL DEFAULT '위내시경'",
        "ultrasound_abdomen": "ALTER TABLE endoscopy_appointments ADD COLUMN ultrasound_abdomen BOOLEAN NOT NULL DEFAULT 0",
        "ultrasound_thyroid": "ALTER TABLE endoscopy_appointments ADD COLUMN ultrasound_thyroid BOOLEAN NOT NULL DEFAULT 0",
        "ultrasound_carotid": "ALTER TABLE endoscopy_appointments ADD COLUMN ultrasound_carotid BOOLEAN NOT NULL DEFAULT 0",
        "ultrasound_cardiac": "ALTER TABLE endoscopy_appointments ADD COLUMN ultrasound_cardiac BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
