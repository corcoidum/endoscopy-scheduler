# 내시경 예약 관리 앱 개선 진단 계획

진단일: 2026-07-06
대상: FastAPI + Jinja2 + HTMX 기반 의원 내부용 내시경 예약 관리 앱
범위: 코드 수정 없이 README 실행 경로, 테스트 상태, 설계 원칙 준수 여부, 직원 사용성, 캘린더/당일업무/리스크 표시/테스트 공백 진단

## 0. 버전 관리 기준선

- `git init` 후 전체 파일을 초기 커밋했다.
- 초기 커밋: `1f1bc28 chore: initial local baseline`
- 원격 저장소는 연결하지 않았다. 이 앱은 의원 내부용이므로 GitHub에 올리지 않는다.
- 커밋 전 확인 결과 `.env`, `.venv/`, `*.db`, `backups/`, `.pytest_cache/`, `__pycache__/`는 git 추적 대상이 아니라 ignored 상태였다.

## 1. README 실행 및 테스트 결과

README 순서대로 로컬 환경 구성을 시도했다.

- `python -m venv .venv`: 성공
- `pip install -r requirements.txt -r requirements-dev.txt`: 성공
- `copy .env.example .env`: 성공
- `python .\scripts\bootstrap_admin.py`: 실패

실패 원인:

`.env.example`에는 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `BACKUP_ENCRYPTION_PASSPHRASE`가 있지만 `app/config.py`의 `Settings`에는 이 필드들이 정의되어 있지 않다. 현재 Pydantic Settings는 extra 입력을 금지하므로 부트스트랩이 시작 전에 중단된다.

README의 테스트 명령도 그대로 실행했다.

- `pytest -q --tb=short`: 실패
- 실패 위치: collection 단계
- 오류: `ModuleNotFoundError: No module named 'app'`

보조 확인으로 `PYTHONPATH=.`을 지정한 뒤 다시 실행했다.

- `$env:PYTHONPATH='.'; .\.venv\Scripts\pytest.exe -q --tb=short`: 실패
- 실패 위치: `app.config.Settings()` 로딩 단계
- 오류: `.env.example`에서 복사된 추가 환경변수 4개가 extra forbidden으로 처리됨

따라서 현재 상태에서는 README 그대로 신규 직원/개발자가 앱을 띄우거나 테스트를 실행할 수 없다.

## 2. 설계 원칙 대조

| 설계 원칙 | 현재 구현 | 판정 | 근거/메모 |
| --- | --- | --- | --- |
| 감사 로그에 PII 중복 저장 금지 | `app/audit.py`의 `safe_changed_fields()`가 `patient_name`, `phone_last4`, `notes`를 마스킹한다. 예약 생성 로그는 필드명 중심이고, 취소 사유는 `[recorded]`로 저장한다. | 부분 준수 | 현재 예약 수정 로그의 `before/after`는 비식별 필드 중심이라 큰 누출은 없어 보인다. 다만 마스킹이 top-level key만 처리해 중첩 dict 안의 민감 필드는 놓칠 수 있다. `chart_number`, `age`도 감사 로그 정책상 민감 후보로 봐야 한다. |
| Optimistic locking | `EndoscopyAppointment.version` 컬럼이 있고 수정/취소 시 form version과 DB version을 비교한다. 성공 시 version을 증가시킨다. | 준수 | `edit_appointment`, `cancel_appointment`에 충돌 검사가 있다. 단, `advance_status`는 hidden version 없이 상태를 변경한다. |
| 약제 중단일수는 앱이 판단하지 않고 플래그만 저장 | `medication_check_required: bool`만 저장한다. 화면 라벨도 `항응고제/항혈소판제 확인 필요`다. | 준수 | 중단일수, 복약 지시, 임상 판단 값은 저장하지 않는다. |
| 관리자 예외 등록은 사유와 감사 로그 필수 | 정원 초과는 admin + `override_reason`일 때만 허용되고 생성/수정 로그가 남는다. | 부분 준수 | 예외 사유 자체는 감사 로그에 직접 기록되지 않는다. PII는 아니지만 운영 감사상 `override_used`/`reason_recorded` 같은 비식별 로그가 있으면 더 명확하다. |
| 조회 사용자(viewer)는 조회 중심 | `viewer`가 `/appointments/{id}/advance-status`를 호출할 수 있다. | 미준수 가능성 | 설계상 viewer는 조회 사용자로 보이므로 상태 변경 권한은 staff/admin으로 좁히는 것이 안전하다. |
| 개발 SQLite와 운영 PostgreSQL 분리 | README와 설계 문서에는 분리되어 있다. 기본 `DATABASE_URL`은 SQLite다. | 부분 준수 | 환경 설정 오류 때문에 PostgreSQL 관련 env 예시와 실제 Settings가 어긋나 있다. |

## 3. 우선순위별 개선 후보

### P1. README 실행 경로와 테스트 부팅 실패 수정

발견사항:

- README 그대로 `bootstrap_admin.py` 실행 시 Settings validation error가 발생한다.
- README의 `pytest` 명령은 `app` import path를 못 잡는다.
- `PYTHONPATH=.`로 보정해도 `.env` extra key 문제로 테스트 collection이 중단된다.

왜 중요한가:

신규 설치, 장애 복구, 인수인계 시 가장 먼저 실패하는 지점이다. 내부용 앱일수록 “문서대로 실행하면 켜진다”가 운영 안정성의 시작점이다.

예상 변경 범위:

- 모델: 없음
- 라우터: 없음
- 템플릿: 없음
- 설정/문서: `app/config.py`, `.env.example`, README 중 하나 이상 정합성 조정
- 테스트: pytest 실행 명령 또는 `pyproject.toml`/pytest 설정 추가 검토

### P1. 조회 사용자(viewer)의 상태 변경 권한 정리

발견사항:

`advance_status` 라우터가 `Role.admin`, `Role.staff`, `Role.viewer`를 모두 허용한다. viewer가 원장/조회 전용 역할이라면 “다음 상태” 변경은 권한 범위를 넘는다.

왜 중요한가:

상태 변경은 감사와 책임 소재가 걸리는 업무 행위다. 조회 역할이 실수로 내원/검사 진행/완료 상태를 바꿀 수 있으면 운영 리스크가 커진다.

예상 변경 범위:

- 모델: 없음
- 라우터: `app/routers/appointments.py`의 `advance_status` 권한
- 템플릿: viewer에게 상태 변경 버튼 숨김
- 테스트: viewer가 상태 변경 POST 시 403인지 검증

### P1. 오늘 업무 화면을 리스크 보드로 강화

발견사항:

현재 첫 화면은 전체/위/대장/동시/초음파/준비 미확인/완료 KPI와 목록을 제공한다. 하지만 실제 직원이 아침에 확인해야 하는 누락 리스크가 한눈에 분리되어 있지 않다.

필요한 리스크:

- 준비 안내 미발송 또는 환자 확인 미완료
- 검사 임박인데 준비상태 미확인
- 약제 확인 필요
- 보호자 동반 안내 필요
- 노쇼/취소 후 후속 조치 필요
- 예약 시간은 지났는데 상태가 아직 예약/내원 전인 건

예상 변경 범위:

- 모델: 우선 없음. 필요 시 follow-up 플래그 추가는 v2에서 검토
- 라우터: `today()`에서 risk buckets 계산
- 템플릿: `today.html`에 “지금 확인할 것” 섹션 추가
- 테스트: risk count와 목록 필터링 테스트 추가

### P1. 감사 로그 마스킹을 재귀적으로 안전하게 만들기

발견사항:

`safe_changed_fields()`는 top-level key만 마스킹한다. 현재 `update_appointment`는 `changed_fields={"before": {...}, "after": {...}}` 구조를 쓰므로 향후 `before.patient_name`, `after.notes` 같은 중첩 값이 들어오면 마스킹되지 않는다.

왜 중요한가:

감사 로그는 장기 보존될 가능성이 있어 PII가 한 번 들어가면 제거와 검토가 어렵다. 의료기관 내부 앱에서는 방어적으로 구현하는 편이 낫다.

예상 변경 범위:

- 모델: 없음
- 라우터: 감사 로그에 넘기는 변경 필드 정책 정리
- 템플릿: 없음
- 테스트: 중첩 dict/list 안의 `patient_name`, `phone_last4`, `chart_number`, `notes`가 마스킹되는지 추가

### P2. Month view 추가

발견사항:

현재 캘린더는 `/calendar/day`, `/calendar/week`만 있다. 월간 흐름이 없어서 검사실 정원, 특정 주 쏠림, 휴진일, 예약 공백을 한눈에 보기 어렵다.

권장 방향:

첫 구현은 복잡한 드래그 캘린더보다 Jinja2 서버 렌더링 월간 표가 적합하다. 날짜별 건수, 위/대장/동시/초음파 요약, 준비 미확인 수, 등록 버튼만 보여주고 상세는 day/week로 연결한다.

예상 변경 범위:

- 모델: 없음
- 라우터: `/calendar/month?month=YYYY-MM` 추가
- 템플릿: `calendar_month.html` 추가, `base.html` 내비게이션에 월간 추가
- 테스트: 월간 화면 렌더링, 날짜별 카운트, 이전/다음 월 이동 테스트

### P2. 예약 등록 화면을 직원 온보딩형 단계로 재배치

발견사항:

현재 등록 폼은 필요한 필드가 한 화면에 나열되어 있다. 한국어 라벨은 좋지만 신규 직원 입장에서는 입력 순서와 필수 확인 항목의 우선순위가 덜 분명하다.

권장 구조:

1. 환자 식별: 차트번호, 이름, 성별, 나이, 연락처 뒤 4자리
2. 검사 일정: 날짜, 시간, 내시경 종류, 초음파
3. 준비 안내: 수면, 정결약, 보호자, 준비 상태
4. 안전 확인: 약제 확인 필요, 특이사항, 관리자 예외 사유

예상 변경 범위:

- 모델: 없음
- 라우터: 없음 또는 validation error 메시지 보강
- 템플릿: `appointment_form.html` 섹션화, helper text 추가
- 테스트: 필수 입력 누락 시 메시지, 기본값 유지 테스트

### P2. 노쇼/취소 후속 관리 흐름 보강

발견사항:

모델에는 `no_show` 상태가 있지만 오늘 화면의 상태 진행 flow에는 노쇼로 바꾸는 액션이 없다. 검색에서는 취소/노쇼 포함 여부가 있지만 후속 조치 화면은 없다.

권장 방향:

- 오늘 화면에서 “노쇼 처리” 버튼 또는 상세 화면에서 상태 변경 제공
- 노쇼 후 후속 메모/재예약 필요 플래그 기록
- 검색 또는 별도 follow-up 목록에서 미처리 건 표시

예상 변경 범위:

- 모델: follow-up 필드 추가 여부 검토
- 라우터: 노쇼 처리 라우트, follow-up 필터
- 템플릿: 상세/오늘/검색 화면 액션 추가
- 테스트: 노쇼 처리 권한, 감사 로그, follow-up 표시

### P2. 검색 화면의 결과 유지와 빠른 필터 개선

발견사항:

검색 폼은 기본 필터가 있으나 검색 후 입력값이 화면에 유지되지 않는다. 자주 쓰는 “오늘 이후”, “준비 미확인”, “약제 확인 필요”, “취소/노쇼 제외” 같은 빠른 필터도 없다.

예상 변경 범위:

- 모델: 없음
- 라우터: 검색 query context 반환, 약제/준비상태 필터 추가
- 템플릿: `search.html` 입력값 유지, 빠른 필터 버튼
- 테스트: 각 필터별 결과 검증

### P3. E2E smoke test 운영성 개선

발견사항:

`tests/test_e2e_smoke.py`는 `RUN_E2E=1`일 때만 실행된다. 로그인 smoke만 있어 핵심 흐름 보장은 약하다.

권장 방향:

- 기본 pytest와 별도로 유지하되 문서화 강화
- 최소 E2E: 로그인 → 예약 등록 → 오늘 화면 확인 → 상세 진입

예상 변경 범위:

- 모델: 없음
- 라우터: 없음
- 템플릿: 접근성 label 보강 가능
- 테스트: Playwright 시나리오 확장

### P3. 운영 문서와 화면 용어 통일

발견사항:

문서에는 “오늘 예약, 준비 미확인, 완료 수” 중심으로 설명되어 있고, 화면에는 “오늘/일간/주간/예약 등록/검색”이 있다. 실제 원내 도입 시 “아침 확인”, “예약 입력”, “검사 진행”, “마감 확인” 같은 업무 단계명으로 안내하면 온보딩이 쉬워진다.

예상 변경 범위:

- 모델: 없음
- 라우터: 없음
- 템플릿: 메뉴 라벨/페이지 제목 일부 조정
- 테스트: 없음 또는 스냅샷 수준 확인
- 문서: `docs/staff_user_manual.md` 업데이트

## 4. 테스트 커버리지 공백

현재 보장되는 것:

- 로그인 성공/실패/비활성 계정 차단
- staff의 사용자 관리 접근 차단
- 예약 생성
- 내시경/초음파 조합 저장
- 동일 환자 동일 날짜 중복 차단
- 시간대 정원 초과 차단
- 수정 optimistic lock 충돌
- 예약 취소
- 기본 마스킹 helper
- 백업/복구 스크립트 존재 여부

부족한 것:

- README 그대로 pytest가 실행되는지
- `.env.example`과 Settings 정합성
- 오늘 화면 KPI 및 리스크 bucket
- day/week/month 캘린더 렌더링
- 검색 필터별 결과
- viewer 권한의 쓰기 차단
- 상태 진행 flow의 감사 로그와 동시성
- 중첩 감사 로그 마스킹
- 개인정보 보유기간 설정 화면
- 관리자 예외 등록 사유 처리
- 노쇼/후속 조치 흐름
- 모바일 또는 작은 화면에서 종이형 캘린더 가독성

## 5. 추천 첫 개선 PR/커밋 범위

한 번에 대규모 리디자인을 하기보다 아래 순서가 안전하다.

1. P1 안정화: README 실행 경로, Settings/env 정합성, pytest 부팅 문제 해결
2. P1 권한/감사 안전성: viewer 상태 변경 차단, 감사 로그 재귀 마스킹
3. P1 오늘 업무 보드: 준비 미확인/약제 확인/임박 미확인/노쇼 후속을 첫 화면에 표시
4. P2 month view: 월간 예약량과 준비 미확인 수를 한눈에 표시
5. P2 등록 폼 온보딩: 섹션화와 실수 방지 메시지 개선

이 순서가 좋은 이유는 먼저 앱이 “문서대로 켜지고 테스트되는 상태”를 만든 뒤, 실제 직원이 매일 보는 첫 화면부터 개선할 수 있기 때문이다.

## 6. Sprint 1 구현 확인 기록

확인일: 2026-07-06

이번 구현 범위:

- [x] `/calendar/month` 월간 캘린더 추가
  - 날짜 셀 클릭 시 `/calendar/day?day=YYYY-MM-DD`로 이동
  - 예약 건수, 위/대장 요약, 휴일, 정원 초과 표시
- [x] 오늘 대시보드 강화
  - 오늘 검사 목록에 검사 종류, 준비상태, 장정결제, 약제/보호자 확인 표시
  - 상태 변경은 기존 `advance-status` 흐름 재사용
- [x] 누락 리스크 패널 추가
  - D-3 이내 준비 안내 미발송
  - 약제 확인 필요 플래그
  - 노쇼 후 미조치 건
  - 각 항목은 예약 상세로 이동
- [x] 입력/수정/취소 흐름 단순화
  - 예약 폼을 `필수 정보`, `선택 정보`, `준비/안전 확인` 접힘 구역으로 재배치
  - 취소 사유 입력 유지
  - 취소 버튼 제출 시 확인 창 유지

검증 결과:

- [x] `python .\scripts\bootstrap_admin.py`
  - 결과: `bootstrap complete`
- [x] `.\\.venv\\Scripts\\pytest.exe -q --tb=short`
  - 결과: `18 passed, 1 skipped`
- [x] uvicorn 수동 확인
  - 실행: `.\\.venv\\Scripts\\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`
  - 로그인 POST `/login`: 303
  - GET `/`: 200, `누락 리스크`, `오늘 검사 목록` 확인
  - GET `/calendar/month`: 200, `월간 예약 현황` 확인
  - GET `/calendar/day`: 200
  - GET `/calendar/week`: 200
  - GET `/appointments/new`: 200, `필수 정보`, `준비/안전 확인` 확인

구현 커밋:

- `3d744aa chore: stabilize local pytest runtime`
- `214b2bc feat: add monthly calendar overview`
- `9d6873c feat: improve today dashboard details`
- `d44ec25 feat: surface appointment risk panel`
- `bf306b8 feat: simplify appointment form and cancel flow`
