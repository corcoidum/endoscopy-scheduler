# 관리자 설치 매뉴얼

## 1. 준비

- 병원 내부 서버 또는 미니 PC 준비
- 외부 인터넷 직접 접속 차단
- Docker와 Docker Compose 설치
- 운영용 `.env` 작성
- 백업 저장장치 준비

## 2. 설치

```powershell
copy .env.example .env
docker compose up --build -d
docker compose exec web python scripts/bootstrap_admin.py
```

## 3. 운영 전 필수 작업

- 초기 관리자 비밀번호 변경
- 직원 개인 계정 생성
- 시간대별 정원 확인
- 백업 암호 별도 보관
- 복구 테스트 1회 수행
- 내부 TLS 또는 VPN 구성

## 4. 장애 대응

- 앱 장애 시 종이 예약표로 임시 전환
- 장애 시간 동안 변경된 예약은 복구 후 직원 2인이 교차 입력 확인
- 복구 후 감사 로그와 당일 일정 대조

