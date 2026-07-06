from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.database import get_db
from app.dependencies import require_roles
from app.models import AuditLog, RetentionPolicy, Role, ScheduleCapacity, User


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

