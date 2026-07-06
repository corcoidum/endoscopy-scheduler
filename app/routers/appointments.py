from calendar import Calendar
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.audit import write_audit_log
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import (
    AppointmentStatus,
    BowelPrepType,
    EndoscopyType,
    EndoscopyAppointment,
    Holiday,
    PatientMinimal,
    PreparationStatus,
    ProcedureType,
    Role,
    ScheduleCapacity,
    User,
)
from app.security import mask_chart_number, mask_name


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]
PAPER_SLOT_MINIMUM = 5
ULTRASOUND_OPTIONS = [
    ("ultrasound_abdomen", "복부"),
    ("ultrasound_thyroid", "갑상선"),
    ("ultrasound_carotid", "경동맥"),
    ("ultrasound_cardiac", "심장"),
]
ACTIVE_STATUSES = [
    AppointmentStatus.reserved.value,
    AppointmentStatus.needs_confirmation.value,
    AppointmentStatus.prepared.value,
    AppointmentStatus.arrived.value,
    AppointmentStatus.in_progress.value,
]


def template_context(request: Request, user: User, **extra: object) -> dict[str, object]:
    context: dict[str, object] = {
        "request": request,
        "current_user": user,
        "procedures": list(ProcedureType),
        "endoscopy_types": list(EndoscopyType),
        "ultrasound_options": ULTRASOUND_OPTIONS,
        "weekday_labels": WEEKDAY_LABELS,
        "statuses": list(AppointmentStatus),
        "preparations": list(PreparationStatus),
        "bowel_preps": list(BowelPrepType),
        "mask_name": mask_name,
        "mask_chart_number": mask_chart_number,
        "exam_summary": exam_summary,
        "ultrasound_labels": ultrasound_labels,
    }
    context.update(extra)
    return context


def parse_bool(value: str | None) -> bool:
    return value in {"on", "true", "1", "yes"}


def ultrasound_labels(appointment: EndoscopyAppointment) -> list[str]:
    labels: list[str] = []
    if appointment.ultrasound_abdomen:
        labels.append("복부")
    if appointment.ultrasound_thyroid:
        labels.append("갑상선")
    if appointment.ultrasound_carotid:
        labels.append("경동맥")
    if appointment.ultrasound_cardiac:
        labels.append("심장")
    return labels


def build_procedure_label(endoscopy_type: str, ultrasound_values: dict[str, bool]) -> str:
    """내시경 종류와 초음파 시행 여부를 운영 화면용 한 줄 요약으로 만듭니다."""

    parts: list[str] = []
    if endoscopy_type and endoscopy_type != EndoscopyType.none.value:
        parts.append(endoscopy_type)
    sono = [label for field, label in ULTRASOUND_OPTIONS if ultrasound_values.get(field)]
    if sono:
        parts.append("초음파(" + ", ".join(sono) + ")")
    return " + ".join(parts) if parts else EndoscopyType.none.value


def exam_summary(appointment: EndoscopyAppointment) -> str:
    return build_procedure_label(
        appointment.endoscopy_type or appointment.procedure_type,
        {
            "ultrasound_abdomen": appointment.ultrasound_abdomen,
            "ultrasound_thyroid": appointment.ultrasound_thyroid,
            "ultrasound_carotid": appointment.ultrasound_carotid,
            "ultrasound_cardiac": appointment.ultrasound_cardiac,
        },
    )


def endoscopy_capacity_key(endoscopy_type: str) -> str:
    return "ANY" if endoscopy_type == EndoscopyType.none.value else endoscopy_type


def build_paper_rows(grouped: dict[date, list[EndoscopyAppointment]]) -> list[list[EndoscopyAppointment | None]]:
    max_count = max([len(items) for items in grouped.values()] + [PAPER_SLOT_MINIMUM])
    rows: list[list[EndoscopyAppointment | None]] = []
    days = list(grouped.keys())
    for index in range(max_count):
        rows.append([grouped[day][index] if index < len(grouped[day]) else None for day in days])
    return rows


def get_or_create_patient(
    db: Session,
    *,
    chart_number: str,
    patient_name: str,
    sex: str,
    age: int | None,
    phone_last4: str | None,
) -> PatientMinimal:
    patient = db.scalar(select(PatientMinimal).where(PatientMinimal.chart_number == chart_number))
    if patient:
        patient.patient_name = patient_name
        patient.sex = sex
        patient.age = age
        patient.phone_last4 = phone_last4
        return patient
    patient = PatientMinimal(chart_number=chart_number, patient_name=patient_name, sex=sex, age=age, phone_last4=phone_last4)
    db.add(patient)
    db.flush()
    return patient


def validate_appointment_slot(
    db: Session,
    *,
    patient_id: int,
    appointment_date: date,
    appointment_time: object,
    procedure_type: str,
    appointment_id: int | None,
    is_admin: bool,
    override_reason: str | None,
) -> list[str]:
    errors: list[str] = []

    holiday = db.scalar(select(Holiday).where(Holiday.holiday_date == appointment_date))
    if holiday and not holiday.is_endoscopy_available:
        errors.append("휴진일 또는 내시경 미운영일입니다.")

    if appointment_time >= datetime.strptime("11:30", "%H:%M").time() and appointment_time < datetime.strptime("14:00", "%H:%M").time():
        errors.append("오전 검사는 11:30 이후 예약할 수 없습니다.")

    duplicate_query = select(EndoscopyAppointment).where(
        EndoscopyAppointment.patient_id == patient_id,
        EndoscopyAppointment.appointment_date == appointment_date,
        EndoscopyAppointment.status.in_(ACTIVE_STATUSES),
    )
    if appointment_id:
        duplicate_query = duplicate_query.where(EndoscopyAppointment.id != appointment_id)
    if db.scalar(duplicate_query):
        errors.append("같은 환자의 동일 날짜 예약이 이미 있습니다.")

    weekday = appointment_date.weekday()
    capacity = db.scalar(
        select(ScheduleCapacity).where(
            ScheduleCapacity.weekday == weekday,
            ScheduleCapacity.start_time == appointment_time,
            ScheduleCapacity.is_active.is_(True),
            or_(ScheduleCapacity.procedure_type == procedure_type, ScheduleCapacity.procedure_type == "ANY"),
        )
    )
    if not capacity:
        errors.append("예약 가능한 시간대가 아닙니다.")
    else:
        count_query = select(func.count()).select_from(EndoscopyAppointment).where(
            EndoscopyAppointment.appointment_date == appointment_date,
            EndoscopyAppointment.appointment_time == appointment_time,
            EndoscopyAppointment.status.in_(ACTIVE_STATUSES),
        )
        if appointment_id:
            count_query = count_query.where(EndoscopyAppointment.id != appointment_id)
        count = db.scalar(count_query) or 0
        if count >= capacity.max_capacity and not (is_admin and override_reason):
            errors.append("시간대 정원을 초과했습니다. 관리자 예외 등록은 사유가 필요합니다.")
    return errors


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    today_date = date.today()
    appointments = db.scalars(
        select(EndoscopyAppointment)
        .options(joinedload(EndoscopyAppointment.patient))
        .where(EndoscopyAppointment.appointment_date == today_date)
        .order_by(EndoscopyAppointment.appointment_time)
    ).all()
    counts = {
        "total": len(appointments),
        "gastroscopy": sum(1 for item in appointments if item.endoscopy_type == EndoscopyType.gastroscopy.value),
        "colonoscopy": sum(1 for item in appointments if item.endoscopy_type == EndoscopyType.colonoscopy.value),
        "both": sum(1 for item in appointments if item.endoscopy_type == EndoscopyType.both.value),
        "ultrasound": sum(1 for item in appointments if ultrasound_labels(item)),
        "not_prepared": sum(1 for item in appointments if item.preparation_status == PreparationStatus.not_done.value),
        "medication_check": sum(1 for item in appointments if item.medication_check_required),
        "guardian_notice": sum(1 for item in appointments if item.guardian_notice),
        "cancelled_or_no_show": sum(1 for item in appointments if item.status in [AppointmentStatus.cancelled.value, AppointmentStatus.no_show.value]),
        "completed": sum(1 for item in appointments if item.status == AppointmentStatus.completed.value),
    }
    write_audit_log(db, request=request, user=user, action="view_today", target_type="appointment", target_id=None)
    db.commit()
    return templates.TemplateResponse("today.html", template_context(request, user, appointments=appointments, counts=counts, today=today_date))


@router.get("/appointments/new", response_class=HTMLResponse)
def new_appointment_page(
    request: Request,
    selected_date: date | None = Query(default=None),
    selected_time: str | None = Query(default=None),
    user: User = Depends(require_roles(Role.admin, Role.staff)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "appointment_form.html",
        template_context(request, user, appointment=None, errors=[], selected_date=selected_date or date.today(), selected_time=selected_time),
    )


@router.post("/appointments")
def create_appointment(
    request: Request,
    chart_number: str = Form(...),
    patient_name: str = Form(...),
    sex: str = Form(...),
    age: int | None = Form(default=None),
    phone_last4: str | None = Form(default=None),
    appointment_date: date = Form(...),
    appointment_time: str = Form(...),
    endoscopy_type: str = Form(default=EndoscopyType.gastroscopy.value),
    ultrasound_abdomen: str | None = Form(default=None),
    ultrasound_thyroid: str | None = Form(default=None),
    ultrasound_carotid: str | None = Form(default=None),
    ultrasound_cardiac: str | None = Form(default=None),
    sedation: str | None = Form(default=None),
    preparation_status: str = Form(default=PreparationStatus.not_done.value),
    medication_check_required: str | None = Form(default=None),
    bowel_prep_type: str | None = Form(default=None),
    guardian_notice: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    override_reason: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.staff)),
):
    parsed_time = datetime.strptime(appointment_time, "%H:%M").time()
    ultrasound_values = {
        "ultrasound_abdomen": parse_bool(ultrasound_abdomen),
        "ultrasound_thyroid": parse_bool(ultrasound_thyroid),
        "ultrasound_carotid": parse_bool(ultrasound_carotid),
        "ultrasound_cardiac": parse_bool(ultrasound_cardiac),
    }
    procedure_type = build_procedure_label(endoscopy_type, ultrasound_values)
    patient = get_or_create_patient(
        db,
        chart_number=chart_number.strip(),
        patient_name=patient_name.strip(),
        sex=sex,
        age=age,
        phone_last4=phone_last4,
    )
    errors = validate_appointment_slot(
        db,
        patient_id=patient.id,
        appointment_date=appointment_date,
        appointment_time=parsed_time,
        procedure_type=endoscopy_capacity_key(endoscopy_type),
        appointment_id=None,
        is_admin=user.role == Role.admin.value,
        override_reason=override_reason,
    )
    if errors:
        db.rollback()
        return templates.TemplateResponse(
            "appointment_form.html",
            template_context(request, user, appointment=None, errors=errors, selected_date=appointment_date, selected_time=appointment_time),
            status_code=400,
        )

    appointment = EndoscopyAppointment(
        patient_id=patient.id,
        appointment_date=appointment_date,
        appointment_time=parsed_time,
        procedure_type=procedure_type,
        endoscopy_type=endoscopy_type,
        ultrasound_abdomen=ultrasound_values["ultrasound_abdomen"],
        ultrasound_thyroid=ultrasound_values["ultrasound_thyroid"],
        ultrasound_carotid=ultrasound_values["ultrasound_carotid"],
        ultrasound_cardiac=ultrasound_values["ultrasound_cardiac"],
        sedation=parse_bool(sedation),
        preparation_status=preparation_status,
        medication_check_required=parse_bool(medication_check_required),
        bowel_prep_type=bowel_prep_type or None,
        guardian_notice=parse_bool(guardian_notice),
        notes=notes,
        created_by=user.id,
        updated_by=user.id,
        override_reason=override_reason if user.role == Role.admin.value else None,
    )
    db.add(appointment)
    db.flush()
    write_audit_log(
        db,
        request=request,
        user=user,
        action="create_appointment",
        target_type="appointment",
        target_id=appointment.id,
        changed_fields={"fields": ["appointment_date", "appointment_time", "endoscopy_type", "ultrasound", "sedation", "preparation_status"]},
    )
    db.commit()
    return RedirectResponse(f"/appointments/{appointment.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/appointments/{appointment_id}", response_class=HTMLResponse)
def appointment_detail(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    appointment = db.scalar(
        select(EndoscopyAppointment).options(joinedload(EndoscopyAppointment.patient)).where(EndoscopyAppointment.id == appointment_id)
    )
    if not appointment:
        raise HTTPException(status_code=404)
    write_audit_log(db, request=request, user=user, action="view_appointment", target_type="appointment", target_id=appointment.id)
    db.commit()
    return templates.TemplateResponse("appointment_detail.html", template_context(request, user, appointment=appointment))


@router.get("/appointments/{appointment_id}/edit", response_class=HTMLResponse)
def edit_appointment_page(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.staff)),
) -> HTMLResponse:
    appointment = db.scalar(
        select(EndoscopyAppointment).options(joinedload(EndoscopyAppointment.patient)).where(EndoscopyAppointment.id == appointment_id)
    )
    if not appointment:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("appointment_form.html", template_context(request, user, appointment=appointment, errors=[]))


@router.post("/appointments/{appointment_id}/edit")
def edit_appointment(
    appointment_id: int,
    request: Request,
    chart_number: str = Form(...),
    patient_name: str = Form(...),
    sex: str = Form(...),
    age: int | None = Form(default=None),
    phone_last4: str | None = Form(default=None),
    appointment_date: date = Form(...),
    appointment_time: str = Form(...),
    endoscopy_type: str = Form(default=EndoscopyType.gastroscopy.value),
    ultrasound_abdomen: str | None = Form(default=None),
    ultrasound_thyroid: str | None = Form(default=None),
    ultrasound_carotid: str | None = Form(default=None),
    ultrasound_cardiac: str | None = Form(default=None),
    sedation: str | None = Form(default=None),
    preparation_status: str = Form(default=PreparationStatus.not_done.value),
    medication_check_required: str | None = Form(default=None),
    bowel_prep_type: str | None = Form(default=None),
    guardian_notice: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    override_reason: str | None = Form(default=None),
    version: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.staff)),
):
    appointment = db.scalar(
        select(EndoscopyAppointment).options(joinedload(EndoscopyAppointment.patient)).where(EndoscopyAppointment.id == appointment_id)
    )
    if not appointment:
        raise HTTPException(status_code=404)
    if appointment.version != version:
        return templates.TemplateResponse(
            "appointment_form.html",
            template_context(request, user, appointment=appointment, errors=["다른 사용자가 먼저 수정했습니다. 화면을 새로고침한 뒤 다시 확인하세요."]),
            status_code=409,
        )

    parsed_time = datetime.strptime(appointment_time, "%H:%M").time()
    ultrasound_values = {
        "ultrasound_abdomen": parse_bool(ultrasound_abdomen),
        "ultrasound_thyroid": parse_bool(ultrasound_thyroid),
        "ultrasound_carotid": parse_bool(ultrasound_carotid),
        "ultrasound_cardiac": parse_bool(ultrasound_cardiac),
    }
    procedure_type = build_procedure_label(endoscopy_type, ultrasound_values)
    patient = get_or_create_patient(
        db,
        chart_number=chart_number.strip(),
        patient_name=patient_name.strip(),
        sex=sex,
        age=age,
        phone_last4=phone_last4,
    )
    errors = validate_appointment_slot(
        db,
        patient_id=patient.id,
        appointment_date=appointment_date,
        appointment_time=parsed_time,
        procedure_type=endoscopy_capacity_key(endoscopy_type),
        appointment_id=appointment.id,
        is_admin=user.role == Role.admin.value,
        override_reason=override_reason,
    )
    if errors:
        return templates.TemplateResponse(
            "appointment_form.html",
            template_context(request, user, appointment=appointment, errors=errors),
            status_code=400,
        )

    before = {
        "appointment_date": appointment.appointment_date.isoformat(),
        "appointment_time": appointment.appointment_time.strftime("%H:%M"),
        "procedure_type": appointment.procedure_type,
        "endoscopy_type": appointment.endoscopy_type,
        "ultrasound": ultrasound_labels(appointment),
        "status": appointment.status,
    }
    appointment.patient_id = patient.id
    appointment.appointment_date = appointment_date
    appointment.appointment_time = parsed_time
    appointment.procedure_type = procedure_type
    appointment.endoscopy_type = endoscopy_type
    appointment.ultrasound_abdomen = ultrasound_values["ultrasound_abdomen"]
    appointment.ultrasound_thyroid = ultrasound_values["ultrasound_thyroid"]
    appointment.ultrasound_carotid = ultrasound_values["ultrasound_carotid"]
    appointment.ultrasound_cardiac = ultrasound_values["ultrasound_cardiac"]
    appointment.sedation = parse_bool(sedation)
    appointment.preparation_status = preparation_status
    appointment.medication_check_required = parse_bool(medication_check_required)
    appointment.bowel_prep_type = bowel_prep_type or None
    appointment.guardian_notice = parse_bool(guardian_notice)
    appointment.notes = notes
    appointment.updated_by = user.id
    appointment.version += 1
    appointment.override_reason = override_reason if user.role == Role.admin.value else appointment.override_reason
    after = {
        "appointment_date": appointment.appointment_date.isoformat(),
        "appointment_time": appointment.appointment_time.strftime("%H:%M"),
        "procedure_type": appointment.procedure_type,
        "endoscopy_type": appointment.endoscopy_type,
        "ultrasound": ultrasound_labels(appointment),
        "status": appointment.status,
    }
    write_audit_log(
        db,
        request=request,
        user=user,
        action="update_appointment",
        target_type="appointment",
        target_id=appointment.id,
        changed_fields={"before": before, "after": after},
    )
    db.commit()
    return RedirectResponse(f"/appointments/{appointment.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    request: Request,
    cancellation_reason: str = Form(...),
    version: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.staff)),
) -> RedirectResponse:
    appointment = db.get(EndoscopyAppointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404)
    if appointment.version != version:
        raise HTTPException(status_code=409, detail="다른 사용자가 먼저 수정했습니다.")
    appointment.status = AppointmentStatus.cancelled.value
    appointment.cancelled_at = datetime.utcnow()
    appointment.cancellation_reason = cancellation_reason
    appointment.updated_by = user.id
    appointment.version += 1
    write_audit_log(
        db,
        request=request,
        user=user,
        action="cancel_appointment",
        target_type="appointment",
        target_id=appointment.id,
        changed_fields={"status": "취소", "reason": "[recorded]"},
    )
    db.commit()
    return RedirectResponse(f"/appointments/{appointment.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/appointments/{appointment_id}/advance-status")
def advance_status(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.staff, Role.viewer)),
) -> RedirectResponse:
    appointment = db.get(EndoscopyAppointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404)
    flow = [
        AppointmentStatus.reserved.value,
        AppointmentStatus.arrived.value,
        AppointmentStatus.in_progress.value,
        AppointmentStatus.completed.value,
    ]
    if appointment.status in flow[:-1]:
        before = appointment.status
        appointment.status = flow[flow.index(appointment.status) + 1]
        appointment.updated_by = user.id
        appointment.version += 1
        write_audit_log(
            db,
            request=request,
            user=user,
            action="advance_status",
            target_type="appointment",
            target_id=appointment.id,
            changed_fields={"before": {"status": before}, "after": {"status": appointment.status}},
        )
        db.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/calendar/day", response_class=HTMLResponse)
def day_calendar(
    request: Request,
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    target_day = day or date.today()
    appointments = db.scalars(
        select(EndoscopyAppointment)
        .options(joinedload(EndoscopyAppointment.patient))
        .where(EndoscopyAppointment.appointment_date == target_day)
        .order_by(EndoscopyAppointment.appointment_time)
    ).all()
    rows = [[appointment] for appointment in appointments]
    while len(rows) < PAPER_SLOT_MINIMUM:
        rows.append([None])
    write_audit_log(db, request=request, user=user, action="view_day", target_type="appointment", target_id=None)
    db.commit()
    return templates.TemplateResponse("calendar_day.html", template_context(request, user, appointments=appointments, day=target_day, rows=rows))


@router.get("/calendar/week", response_class=HTMLResponse)
def week_calendar(
    request: Request,
    start: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    today = date.today()
    week_start = start or (today - timedelta(days=today.weekday()))
    week_end = week_start + timedelta(days=5)
    appointments = db.scalars(
        select(EndoscopyAppointment)
        .options(joinedload(EndoscopyAppointment.patient))
        .where(and_(EndoscopyAppointment.appointment_date >= week_start, EndoscopyAppointment.appointment_date <= week_end))
        .order_by(EndoscopyAppointment.appointment_date, EndoscopyAppointment.appointment_time)
    ).all()
    grouped = {week_start + timedelta(days=i): [] for i in range(6)}
    for appointment in appointments:
        grouped[appointment.appointment_date].append(appointment)
    rows = build_paper_rows(grouped)
    write_audit_log(db, request=request, user=user, action="view_week", target_type="appointment", target_id=None)
    db.commit()
    return templates.TemplateResponse("calendar_week.html", template_context(request, user, grouped=grouped, rows=rows, week_start=week_start, week_end=week_end))


@router.get("/calendar/month", response_class=HTMLResponse)
def month_calendar(
    request: Request,
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    today = date.today()
    try:
        month_start = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month는 YYYY-MM 형식이어야 합니다.")

    weeks = Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    period_start = weeks[0][0]
    period_end = weeks[-1][-1]
    appointments = db.scalars(
        select(EndoscopyAppointment)
        .options(joinedload(EndoscopyAppointment.patient))
        .where(and_(EndoscopyAppointment.appointment_date >= period_start, EndoscopyAppointment.appointment_date <= period_end))
        .order_by(EndoscopyAppointment.appointment_date, EndoscopyAppointment.appointment_time)
    ).all()
    holidays = {
        item.holiday_date: item
        for item in db.scalars(
            select(Holiday).where(and_(Holiday.holiday_date >= period_start, Holiday.holiday_date <= period_end))
        ).all()
    }
    capacities = db.scalars(select(ScheduleCapacity).where(ScheduleCapacity.is_active.is_(True))).all()
    daily_capacity = {
        weekday: sum(item.max_capacity for item in capacities if item.weekday == weekday)
        for weekday in range(7)
    }
    grouped: dict[date, list[EndoscopyAppointment]] = {day: [] for week in weeks for day in week}
    for appointment in appointments:
        grouped.setdefault(appointment.appointment_date, []).append(appointment)

    month_cells = []
    for week in weeks:
        row = []
        for day in week:
            items = grouped.get(day, [])
            active_items = [item for item in items if item.status in ACTIVE_STATUSES]
            capacity_total = daily_capacity.get(day.weekday(), 0)
            stomach_count = sum(
                1 for item in active_items if item.endoscopy_type in [EndoscopyType.gastroscopy.value, EndoscopyType.both.value]
            )
            colon_count = sum(
                1 for item in active_items if item.endoscopy_type in [EndoscopyType.colonoscopy.value, EndoscopyType.both.value]
            )
            row.append(
                {
                    "day": day,
                    "is_current_month": day.month == month_start.month,
                    "appointments": active_items,
                    "total": len(active_items),
                    "stomach": stomach_count,
                    "colon": colon_count,
                    "holiday": holidays.get(day),
                    "capacity_total": capacity_total,
                    "is_over_capacity": capacity_total > 0 and len(active_items) > capacity_total,
                }
            )
        month_cells.append(row)

    previous_month = (month_start.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    write_audit_log(db, request=request, user=user, action="view_month", target_type="appointment", target_id=None)
    db.commit()
    return templates.TemplateResponse(
        "calendar_month.html",
        template_context(
            request,
            user,
            month_start=month_start,
            previous_month=previous_month,
            next_month=next_month,
            month_cells=month_cells,
        ),
    )


@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: str | None = Query(default=None),
    chart_number: str | None = Query(default=None),
    appointment_date: date | None = Query(default=None),
    procedure_type: str | None = Query(default=None),
    endoscopy_type: str | None = Query(default=None),
    ultrasound_only: bool = Query(default=False),
    status_value: str | None = Query(default=None),
    include_cancelled: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    stmt = select(EndoscopyAppointment).options(joinedload(EndoscopyAppointment.patient)).join(PatientMinimal)
    if q:
        stmt = stmt.where(PatientMinimal.patient_name.contains(q))
    if chart_number:
        stmt = stmt.where(PatientMinimal.chart_number.contains(chart_number))
    if appointment_date:
        stmt = stmt.where(EndoscopyAppointment.appointment_date == appointment_date)
    if procedure_type:
        stmt = stmt.where(EndoscopyAppointment.procedure_type == procedure_type)
    if endoscopy_type:
        stmt = stmt.where(EndoscopyAppointment.endoscopy_type == endoscopy_type)
    if ultrasound_only:
        stmt = stmt.where(
            or_(
                EndoscopyAppointment.ultrasound_abdomen.is_(True),
                EndoscopyAppointment.ultrasound_thyroid.is_(True),
                EndoscopyAppointment.ultrasound_carotid.is_(True),
                EndoscopyAppointment.ultrasound_cardiac.is_(True),
            )
        )
    if status_value:
        stmt = stmt.where(EndoscopyAppointment.status == status_value)
    if not include_cancelled:
        stmt = stmt.where(EndoscopyAppointment.status.notin_([AppointmentStatus.cancelled.value, AppointmentStatus.no_show.value]))
    appointments = db.scalars(stmt.order_by(EndoscopyAppointment.appointment_date.desc(), EndoscopyAppointment.appointment_time)).all()
    write_audit_log(db, request=request, user=user, action="search_appointments", target_type="appointment", target_id=None)
    db.commit()
    return templates.TemplateResponse("search.html", template_context(request, user, appointments=appointments))
