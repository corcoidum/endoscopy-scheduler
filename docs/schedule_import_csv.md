# 근무표 CSV 일괄 반영 포맷

관리자 화면의 `정원 > 근무표 CSV 반영`에서 Google Sheet 등에서 내려받은 CSV를 미리보기/검증한 뒤 적용합니다.

이 CSV에는 환자명, 차트번호, 전화번호, 검사 결과 등 환자 관련 정보를 넣지 않습니다. 시스템은 환자/차트/전화로 보이는 컬럼이 있으면 적용을 막습니다.

## 기본 규칙

- 첫 줄은 헤더입니다.
- `row_type`은 필수이며 `capacity` 또는 `holiday`를 입력합니다.
- `capacity` 행은 반복 요일별 검사 정원을 upsert합니다.
- `holiday` 행은 특정 날짜의 휴진/운영 예외를 upsert합니다.
- 적용 전 preview에서 오류가 0건이어야 하며, 최종 적용 시 확인 문구 `적용`을 입력해야 합니다.
- 적용 결과는 `import_schedule_csv` action으로 감사 로그에 남습니다.

## 권장 헤더

```csv
row_type,date,weekday,start_time,max_capacity,procedure_type,is_active,description,is_endoscopy_available
```

한국어 헤더도 사용할 수 있습니다.

```csv
구분,날짜,요일,시작시간,정원,검사종류,활성,설명,내시경운영
```

## 컬럼 설명

| 컬럼 | 대상 | 설명 | 예시 |
| --- | --- | --- | --- |
| `row_type` | 전체 | `capacity` 또는 `holiday` | `capacity` |
| `date` | holiday | 휴진/운영 예외 날짜, `YYYY-MM-DD` | `2026-08-15` |
| `weekday` | capacity | 월=0, 화=1, ..., 일=6 또는 `월`~`일` | `월` |
| `start_time` | capacity | 시작 시간, `HH:MM` | `09:00` |
| `max_capacity` | capacity | 시간대 정원, 0~20. 0이면 자동 비활성 처리 | `2` |
| `procedure_type` | capacity | 검사 종류. 비우면 `ANY` | `ANY`, `위내시경` |
| `is_active` | capacity | 활성 여부. 비우면 활성 | `true`, `false` |
| `description` | holiday | 휴진/운영 예외 사유 | `광복절 휴진` |
| `is_endoscopy_available` | holiday | 해당 날짜 내시경 운영 여부. 비우면 휴진 | `false`, `운영` |

## 예시

```csv
row_type,date,weekday,start_time,max_capacity,procedure_type,is_active,description,is_endoscopy_available
capacity,,월,09:00,2,ANY,true,,
capacity,,월,09:30,1,위내시경,true,,
capacity,,토,11:00,0,ANY,false,,
holiday,2026-08-15,,,,,,광복절 휴진,false
holiday,2026-09-01,,,,,,오전만 단축 운영,운영
```

## 운영 체크리스트

1. Google Sheet에서 근무표 탭만 CSV로 다운로드합니다.
2. 환자명/차트번호/전화번호 컬럼이 없는지 확인합니다.
3. 관리자 화면에서 CSV를 업로드하고 preview 오류를 확인합니다.
4. 휴진일과 정원 변경 요약을 동료 1명과 교차 확인합니다.
5. 확인 문구 `적용`을 입력해 반영합니다.
6. 감사 로그에서 `import_schedule_csv` 기록을 확인합니다.
