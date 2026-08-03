from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import create_session_token, hash_password, verify_password


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MAX_FAILED_LOGIN = 5


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.is_active:
        write_audit_log(
            db,
            request=request,
            user=None,
            action="login",
            target_type="user",
            target_id=user.id if user else None,
            result="failed",
        )
        db.commit()
        return templates.TemplateResponse("login.html", {"request": request, "error": "로그인 정보를 확인하세요."})

    if user.failed_login_count >= MAX_FAILED_LOGIN:
        write_audit_log(db, request=request, user=user, action="login_locked", target_type="user", target_id=user.id, result="failed")
        db.commit()
        return templates.TemplateResponse("login.html", {"request": request, "error": "로그인 실패가 누적되어 관리자 확인이 필요합니다."})

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        write_audit_log(db, request=request, user=user, action="login", target_type="user", target_id=user.id, result="failed")
        db.commit()
        return templates.TemplateResponse("login.html", {"request": request, "error": "로그인 정보를 확인하세요."})

    user.failed_login_count = 0
    user.last_login_at = datetime.utcnow()
    write_audit_log(db, request=request, user=user, action="login", target_type="user", target_id=user.id)
    db.commit()

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    # 운영에서는 HTTPS 연결에만 세션 쿠키를 보냅니다. 개발은 http://127.0.0.1 이므로 켜지 않습니다.
    response.set_cookie(
        "session",
        create_session_token(user.id),
        httponly=True,
        samesite="strict",
        secure=get_settings().is_production,
    )
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session")
    return response


@router.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("change_password.html", {"request": request, "error": None})


@router.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.dependencies import get_current_user

    user = get_current_user(request, db)
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse("change_password.html", {"request": request, "error": "현재 비밀번호가 맞지 않습니다."})
    if len(new_password) < 10:
        return templates.TemplateResponse("change_password.html", {"request": request, "error": "새 비밀번호는 10자 이상이어야 합니다."})

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    write_audit_log(db, request=request, user=user, action="change_password", target_type="user", target_id=user.id)
    db.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
