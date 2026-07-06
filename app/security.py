from datetime import datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="endoscopy-session")


def create_session_token(user_id: int) -> str:
    expires_at = (datetime.utcnow() + timedelta(minutes=get_settings().session_minutes)).isoformat()
    return _serializer().dumps({"user_id": user_id, "expires_at": expires_at})


def read_session_token(token: str) -> dict[str, Any] | None:
    try:
        return _serializer().loads(token, max_age=get_settings().session_minutes * 60)
    except (BadSignature, SignatureExpired):
        return None


def mask_name(name: str) -> str:
    """목록 화면에서 이름을 과도하게 노출하지 않도록 일부를 가립니다."""

    if not name:
        return ""
    if len(name) == 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def mask_chart_number(chart_number: str) -> str:
    if len(chart_number) <= 4:
        return chart_number
    return chart_number[:2] + "*" * (len(chart_number) - 4) + chart_number[-2:]

