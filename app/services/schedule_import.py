from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holiday, ScheduleCapacity


MAX_CSV_BYTES = 64 * 1024
MAX_CAPACITY = 20
CSV_FIELDS = [
    "row_type",
    "date",
    "weekday",
    "start_time",
    "max_capacity",
    "procedure_type",
    "is_active",
    "description",
    "is_endoscopy_available",
]
HEADER_ALIASES = {
    "구분": "row_type",
    "종류": "row_type",
    "날짜": "date",
    "요일": "weekday",
    "시작시간": "start_time",
    "시작 시간": "start_time",
    "정원": "max_capacity",
    "최대인원": "max_capacity",
    "최대 인원": "max_capacity",
    "검사종류": "procedure_type",
    "검사 종류": "procedure_type",
    "활성": "is_active",
    "설명": "description",
    "비고": "description",
    "내시경운영": "is_endoscopy_available",
    "내시경 운영": "is_endoscopy_available",
}
SENSITIVE_HEADER_KEYWORDS = ["patient", "chart", "phone", "환자", "차트", "전화", "주민", "등록번호"]
WEEKDAY_ALIASES = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
TRUE_VALUES = {"1", "true", "yes", "y", "on", "운영", "사용", "활성", "진료", "가능", "o"}
FALSE_VALUES = {"0", "false", "no", "n", "off", "휴진", "미사용", "비활성", "불가", "x"}


@dataclass
class ImportPreviewRow:
    row_number: int
    row_type: str
    key: str
    action: str
    values: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def display_values(self) -> dict[str, Any]:
        return {key: _display_value(value) for key, value in self.values.items()}


@dataclass
class ScheduleImportPlan:
    rows: list[ImportPreviewRow]
    errors: list[str]
    csv_text: str

    @property
    def has_errors(self) -> bool:
        return bool(self.errors or any(row.errors for row in self.rows))

    @property
    def valid_rows(self) -> list[ImportPreviewRow]:
        return [row for row in self.rows if not row.errors]

    @property
    def capacity_count(self) -> int:
        return sum(1 for row in self.valid_rows if row.row_type == "capacity")

    @property
    def holiday_count(self) -> int:
        return sum(1 for row in self.valid_rows if row.row_type == "holiday")


def parse_schedule_import_csv(csv_text: str) -> ScheduleImportPlan:
    normalized_text = csv_text.strip("\ufeff\r\n ")
    errors: list[str] = []
    rows: list[ImportPreviewRow] = []

    if not normalized_text:
        return ScheduleImportPlan(rows=[], errors=["CSV 내용이 비어 있습니다."], csv_text="")
    if len(normalized_text.encode("utf-8")) > MAX_CSV_BYTES:
        return ScheduleImportPlan(rows=[], errors=["CSV는 64KB 이하로 업로드해 주세요."], csv_text=normalized_text)

    reader = csv.DictReader(StringIO(normalized_text))
    if not reader.fieldnames:
        return ScheduleImportPlan(rows=[], errors=["CSV 헤더를 찾을 수 없습니다."], csv_text=normalized_text)

    field_map = {_clean_header(name): _normalize_header(name) for name in reader.fieldnames if name}
    sensitive_headers = [name for name in field_map if _looks_sensitive_header(name)]
    if sensitive_headers:
        errors.append("환자/차트/전화번호로 보이는 컬럼이 있습니다. 근무표 CSV만 업로드하세요.")
    if "row_type" not in field_map.values():
        errors.append("필수 컬럼 row_type(또는 구분)이 필요합니다.")

    seen_capacity: set[tuple[int, time, str]] = set()
    seen_holidays: set[date] = set()
    for row_number, raw_row in enumerate(reader, start=2):
        normalized = _normalize_row(raw_row)
        row_type = _normalize_row_type(normalized.get("row_type", ""))
        if row_type == "capacity":
            row = _parse_capacity_row(row_number, normalized, seen_capacity)
        elif row_type == "holiday":
            row = _parse_holiday_row(row_number, normalized, seen_holidays)
        else:
            row = ImportPreviewRow(
                row_number=row_number,
                row_type=row_type or "unknown",
                key="-",
                action="skip",
                values={},
                errors=["row_type은 capacity(정원) 또는 holiday(휴진)이어야 합니다."],
            )
        rows.append(row)

    if not rows:
        errors.append("데이터 행이 없습니다.")
    return ScheduleImportPlan(rows=rows, errors=errors, csv_text=normalized_text)


def apply_schedule_import(db: Session, plan: ScheduleImportPlan) -> dict[str, int]:
    if plan.has_errors:
        raise ValueError("검증 오류가 있는 CSV는 적용할 수 없습니다.")

    summary = {
        "capacity_created": 0,
        "capacity_updated": 0,
        "capacity_unchanged": 0,
        "holiday_created": 0,
        "holiday_updated": 0,
        "holiday_unchanged": 0,
    }
    for row in plan.valid_rows:
        if row.row_type == "capacity":
            _apply_capacity_row(db, row, summary)
        elif row.row_type == "holiday":
            _apply_holiday_row(db, row, summary)
    return summary


def _apply_capacity_row(db: Session, row: ImportPreviewRow, summary: dict[str, int]) -> None:
    values = row.values
    capacity = db.scalar(
        select(ScheduleCapacity)
        .where(
            ScheduleCapacity.weekday == values["weekday"],
            ScheduleCapacity.start_time == values["start_time"],
            ScheduleCapacity.procedure_type == values["procedure_type"],
        )
        .order_by(ScheduleCapacity.id)
    )
    if not capacity:
        db.add(
            ScheduleCapacity(
                weekday=values["weekday"],
                start_time=values["start_time"],
                max_capacity=values["max_capacity"],
                procedure_type=values["procedure_type"],
                is_active=values["is_active"],
            )
        )
        summary["capacity_created"] += 1
        return

    changed = (
        capacity.max_capacity != values["max_capacity"]
        or capacity.is_active != values["is_active"]
        or capacity.procedure_type != values["procedure_type"]
    )
    if changed:
        capacity.max_capacity = values["max_capacity"]
        capacity.is_active = values["is_active"]
        capacity.procedure_type = values["procedure_type"]
        summary["capacity_updated"] += 1
    else:
        summary["capacity_unchanged"] += 1


def _apply_holiday_row(db: Session, row: ImportPreviewRow, summary: dict[str, int]) -> None:
    values = row.values
    holiday = db.scalar(select(Holiday).where(Holiday.holiday_date == values["holiday_date"]))
    if not holiday:
        db.add(
            Holiday(
                holiday_date=values["holiday_date"],
                description=values["description"],
                is_endoscopy_available=values["is_endoscopy_available"],
            )
        )
        summary["holiday_created"] += 1
        return

    changed = (
        holiday.description != values["description"]
        or holiday.is_endoscopy_available != values["is_endoscopy_available"]
    )
    if changed:
        holiday.description = values["description"]
        holiday.is_endoscopy_available = values["is_endoscopy_available"]
        summary["holiday_updated"] += 1
    else:
        summary["holiday_unchanged"] += 1


def _parse_capacity_row(row_number: int, row: dict[str, str], seen: set[tuple[int, time, str]]) -> ImportPreviewRow:
    errors: list[str] = []
    weekday = _parse_weekday(row.get("weekday", ""), errors)
    start_time = _parse_time(row.get("start_time", ""), errors)
    max_capacity = _parse_int(row.get("max_capacity", ""), "max_capacity", errors)
    procedure_type = (row.get("procedure_type") or "ANY").strip() or "ANY"
    if len(procedure_type) > 40:
        errors.append("procedure_type은 40자 이하로 입력하세요.")
    is_active = _parse_bool(row.get("is_active", ""), default=True, errors=errors)

    if max_capacity is not None and not 0 <= max_capacity <= MAX_CAPACITY:
        errors.append(f"max_capacity는 0~{MAX_CAPACITY} 사이여야 합니다.")
    if max_capacity == 0:
        is_active = False

    key = "-"
    values: dict[str, Any] = {}
    if weekday is not None and start_time is not None and max_capacity is not None:
        key = f"{weekday}:{start_time.strftime('%H:%M')}:{procedure_type}"
        duplicate_key = (weekday, start_time, procedure_type)
        if duplicate_key in seen:
            errors.append("CSV 안에 같은 요일/시간/검사종류 정원 행이 중복되었습니다.")
        seen.add(duplicate_key)
        values = {
            "weekday": weekday,
            "start_time": start_time,
            "max_capacity": max_capacity,
            "procedure_type": procedure_type,
            "is_active": is_active,
        }

    return ImportPreviewRow(row_number=row_number, row_type="capacity", key=key, action="upsert", values=values, errors=errors)


def _parse_holiday_row(row_number: int, row: dict[str, str], seen: set[date]) -> ImportPreviewRow:
    errors: list[str] = []
    holiday_date = _parse_date(row.get("date", ""), errors)
    description = (row.get("description") or "휴진").strip()[:120]
    is_available = _parse_bool(row.get("is_endoscopy_available", ""), default=False, errors=errors)

    key = "-"
    values: dict[str, Any] = {}
    if holiday_date:
        key = holiday_date.isoformat()
        if holiday_date in seen:
            errors.append("CSV 안에 같은 휴진 날짜가 중복되었습니다.")
        seen.add(holiday_date)
        values = {
            "holiday_date": holiday_date,
            "description": description,
            "is_endoscopy_available": is_available,
        }
    return ImportPreviewRow(row_number=row_number, row_type="holiday", key=key, action="upsert", values=values, errors=errors)


def _normalize_row(raw_row: dict[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for header, value in raw_row.items():
        if not header:
            continue
        normalized[_normalize_header(header)] = (value or "").strip()
    return normalized


def _normalize_header(header: str) -> str:
    cleaned = _clean_header(header)
    return HEADER_ALIASES.get(cleaned, cleaned)


def _clean_header(header: str) -> str:
    return header.strip().replace("\ufeff", "")


def _looks_sensitive_header(header: str) -> bool:
    lowered = header.lower()
    return any(keyword in lowered for keyword in SENSITIVE_HEADER_KEYWORDS)


def _normalize_row_type(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"capacity", "schedule_capacity", "정원", "시간", "slot"}:
        return "capacity"
    if lowered in {"holiday", "휴진", "휴일", "공휴일", "closed"}:
        return "holiday"
    return lowered


def _parse_weekday(value: str, errors: list[str]) -> int | None:
    cleaned = value.strip()
    if cleaned in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[cleaned]
    try:
        weekday = int(cleaned)
    except ValueError:
        errors.append("weekday는 0~6 또는 월~일로 입력하세요.")
        return None
    if not 0 <= weekday <= 6:
        errors.append("weekday는 0(월)~6(일) 범위여야 합니다.")
        return None
    return weekday


def _parse_time(value: str, errors: list[str]) -> time | None:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        errors.append("start_time은 HH:MM 형식이어야 합니다.")
        return None


def _parse_date(value: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        errors.append("date는 YYYY-MM-DD 형식이어야 합니다.")
        return None


def _parse_int(value: str, field_name: str, errors: list[str]) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        errors.append(f"{field_name}은 정수여야 합니다.")
        return None


def _parse_bool(value: str, *, default: bool, errors: list[str]) -> bool:
    cleaned = value.strip().lower()
    if not cleaned:
        return default
    if cleaned in TRUE_VALUES:
        return True
    if cleaned in FALSE_VALUES:
        return False
    errors.append("활성/운영 여부는 true/false, 1/0, 운영/휴진 등으로 입력하세요.")
    return default


def _display_value(value: Any) -> Any:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value
