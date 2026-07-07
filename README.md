# 내시경 예약·스케줄 관리 MVP

소규모 내과의원 내부 사용을 가정한 FastAPI/Jinja2/HTMX 기반 MVP입니다.

이 프로젝트는 EMR을 대체하지 않으며, 내시경 예약과 일정 관리에 필요한 최소정보만 저장합니다.

## 기술 선택

- Backend: Python 3.12+, FastAPI, SQLAlchemy, Pydantic Settings
- Frontend: Jinja2 + HTMX + 단순 CSS
- DB: 운영 PostgreSQL, 개발 SQLite
- 배포: Docker Compose

React/Next.js 대신 Jinja2 + HTMX를 선택한 이유는 직원 5명 규모 내부 업무앱에서 빌드 체인과 유지보수 부담을 줄이기 위해서입니다.

## 로컬 실행

```powershell
cd .\endoscopy-scheduler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
python .\scripts\bootstrap_admin.py
uvicorn app.main:app --reload
```

초기 계정:

- ID: `admin`
- PW: `.env`의 `INITIAL_ADMIN_PASSWORD`

운영 전에는 반드시 초기 비밀번호를 변경하세요.

## 테스트

```powershell
pytest
```

Playwright E2E는 브라우저 설치가 필요합니다.

```powershell
python -m playwright install chromium
pytest tests\test_e2e_smoke.py
```

## Docker Compose

```powershell
docker compose up --build
```

앱은 기본적으로 `http://localhost:8000`에서 실행됩니다. 운영에서는 reverse proxy로 내부 TLS를 적용하고 외부 인터넷 직접 접속을 차단하세요.

