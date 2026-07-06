from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


SENSITIVE_FIELDS = {"patient_name", "phone_last4", "notes"}


def safe_changed_fields(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    """감사 로그에 환자 개인정보가 반복 저장되지 않도록 민감 필드를 요약합니다."""

    if not changes:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in changes.items():
        cleaned[key] = "[masked]" if key in SENSITIVE_FIELDS else value
    return cleaned


def write_audit_log(
    db: Session,
    *,
    request: Request | None,
    user: User | None,
    action: str,
    target_type: str,
    target_id: int | None,
    changed_fields: dict[str, Any] | None = None,
    result: str = "success",
) -> None:
    ip_address = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            changed_fields=safe_changed_fields(changed_fields),
            ip_address=ip_address,
            result=result,
        )
    )

