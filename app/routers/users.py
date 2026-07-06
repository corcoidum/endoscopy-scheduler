from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.database import get_db
from app.dependencies import require_roles
from app.models import Role, User
from app.security import hash_password


router = APIRouter(prefix="/admin/users")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> HTMLResponse:
    users = db.scalars(select(User).order_by(User.username)).all()
    return templates.TemplateResponse("users.html", {"request": request, "current_user": current_user, "users": users, "roles": list(Role)})


@router.post("")
def create_user(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> RedirectResponse:
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=400, detail="이미 존재하는 사용자입니다.")
    user = User(username=username, display_name=display_name, role=role, password_hash=hash_password(password), must_change_password=True)
    db.add(user)
    db.flush()
    write_audit_log(db, request=request, user=current_user, action="create_user", target_type="user", target_id=user.id)
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> RedirectResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신은 비활성화할 수 없습니다.")
    user.is_active = False
    write_audit_log(db, request=request, user=current_user, action="deactivate_user", target_type="user", target_id=user.id)
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.admin)),
) -> RedirectResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.must_change_password = True
    write_audit_log(db, request=request, user=current_user, action="reset_password", target_type="user", target_id=user.id)
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)

