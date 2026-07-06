from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, ensure_sqlite_schema_compatibility
from app.routers import admin, appointments, auth, users


def create_app() -> FastAPI:
    app = FastAPI(title="내시경 예약·스케줄 관리")

    # MVP 개발 편의를 위해 테이블이 없으면 생성합니다. 운영은 Alembic migration을 사용하세요.
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema_compatibility()

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(auth.router)
    app.include_router(appointments.router)
    app.include_router(users.router)
    app.include_router(admin.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    return app


app = create_app()
