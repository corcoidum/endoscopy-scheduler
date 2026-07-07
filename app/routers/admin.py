from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.database import get_db
from app.dependencies import require_roles
from app.models import AuditLog, RetentionPolicy, Role, ScheduleCapacity, User
from app.services.schedule_import import MAX_CSV_BYTES, apply_schedule_import, parse_schedule_import_csv


router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("/capacity", response_class=HTMLResponse)
def capacity_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    capacities = db.scalars(select(ScheduleCapacity).order_by(ScheduleCapacity.weekday, ScheduleCapacity.start_time)).all()
    return templates.TemplateResponse("capacity.html", {"request": request, "current_user": current_user, "capacities": capacities})


@router.post("/capacity")
def create_capacity(
    request: Request,
    weekday: int = Form(...),
    start_time: str = Form(...),
    max_capacity: int = Form(...),
    procedure_type: str = Form(default="ANY"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> RedirectResponse:
    capacity = ScheduleCapacity(
        weekday=weekday,
        start_time=datetime.strptime(start_time, "%H:%M").time(),
        max_capacity=max_capacity,
        procedure_type=procedure_type or "ANY",
    )
    db.add(capacity)
    db.flush()
    write_audit_log(db, request=request, user=current_user, action="create_capacity", target_type="schedule_capacity", target_id=capacity.id)
    db.commit()
    return RedirectResponse("/admin/capacity", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/capacity/import", response_class=HTMLResponse)
def capacity_import_page(
    request: Request,
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "capacity_import.html",
        {"request": request, "current_user": current_user, "plan": None, "applied_summary": None, "csv_text": ""},
    )


@router.post("/capacity/import/preview", response_class=HTMLResponse)
def preview_capacity_import(
    request: Request,
    csv_text: str = Form(default=""),
    csv_file: UploadFile | None = File(default=None),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    import_text = read_import_text(csv_text, csv_file)
    plan = parse_schedule_import_csv(import_text)
    return templates.TemplateResponse(
        "capacity_import.html",
        {"request": request, "current_user": current_user, "plan": plan, "applied_summary": None, "csv_text": plan.csv_text},
        status_code=400 if plan.has_errors else 200,
    )


@router.post("/capacity/import/apply", response_class=HTMLResponse)
def apply_capacity_import(
    request: Request,
    csv_text: str = Form(...),
    confirm_text: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    plan = parse_schedule_import_csv(csv_text)
    if confirm_text.strip() != "적용":
        plan.errors.append("적용하려면 확인 문구에 '적용'을 입력하세요.")
    if plan.has_errors:
        write_audit_log(
            db,
            request=request,
            user=current_user,
            action="import_schedule_csv",
            target_type="schedule_import",
            target_id=None,
            changed_fields={"result": "blocked", "errors": len(plan.errors), "rows": len(plan.rows)},
            result="failed",
        )
        db.commit()
        return templates.TemplateResponse(
            "capacity_import.html",
            {"request": request, "current_user": current_user, "plan": plan, "applied_summary": None, "csv_text": plan.csv_text},
            status_code=400,
        )

    summary = apply_schedule_import(db, plan)
    write_audit_log(
        db,
        request=request,
        user=current_user,
        action="import_schedule_csv",
        target_type="schedule_import",
        target_id=None,
        changed_fields={"summary": summary, "capacity_rows": plan.capacity_count, "holiday_rows": plan.holiday_count},
    )
    db.commit()
    return templates.TemplateResponse(
        "capacity_import.html",
        {"request": request, "current_user": current_user, "plan": plan, "applied_summary": summary, "csv_text": plan.csv_text},
    )


@router.get("/audit-logs", response_class=HTMLResponse)
def audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()
    return templates.TemplateResponse("audit_logs.html", {"request": request, "current_user": current_user, "logs": logs})


@router.get("/backups", response_class=HTMLResponse)
def backups_page(
    request: Request,
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    return templates.TemplateResponse("backups.html", {"request": request, "current_user": current_user})


@router.get("/privacy-retention", response_class=HTMLResponse)
def privacy_retention_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    policy = db.scalar(select(RetentionPolicy).order_by(RetentionPolicy.id).limit(1))
    if not policy:
        policy = RetentionPolicy()
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return templates.TemplateResponse("privacy_retention.html", {"request": request, "current_user": current_user, "policy": policy})


@router.post("/privacy-retention")
def update_privacy_retention(
    request: Request,
    completed_retention_days: int = Form(...),
    anonymize_name: str | None = Form(default=None),
    anonymize_phone_last4: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> RedirectResponse:
    policy = db.scalar(select(RetentionPolicy).order_by(RetentionPolicy.id).limit(1))
    if not policy:
        policy = RetentionPolicy()
        db.add(policy)
    policy.completed_retention_days = completed_retention_days
    policy.anonymize_name = anonymize_name == "on"
    policy.anonymize_phone_last4 = anonymize_phone_last4 == "on"
    policy.updated_by = current_user.id
    write_audit_log(db, request=request, user=current_user, action="update_retention_policy", target_type="retention_policy", target_id=policy.id)
    db.commit()
    return RedirectResponse("/admin/privacy-retention", status_code=status.HTTP_303_SEE_OTHER)


def read_import_text(csv_text: str, csv_file: UploadFile | None) -> str:
    if csv_file and csv_file.filename:
        data = csv_file.file.read(MAX_CSV_BYTES + 1)
        if len(data) > MAX_CSV_BYTES:
            return ""
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("cp949")
    return csv_text
