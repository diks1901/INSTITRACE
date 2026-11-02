"""Demo authentication and role authorization.

WARNING: This is a LOCAL DEMO security layer, not production security.
Passwords are salted+hashed with PBKDF2 (stdlib) and kept out of source code
(they are set at seed time). Tokens are HMAC-signed expiring payloads. Do not
use this to authenticate real AICTE officials.
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import now
from .config import get_settings
from .database import get_db
from .models import DemoUser, UserRole


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return digest.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, expected_hash)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_token(username: str, role: str) -> str:
    settings = get_settings()
    expires = now() + timedelta(hours=settings.demo_token_ttl_hours)
    payload = _b64(json.dumps({"sub": username, "role": role, "exp": expires.isoformat()}).encode())
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload, sig = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
    data = json.loads(_unb64(payload))
    exp = data.get("exp")
    from datetime import datetime

    if exp and datetime.fromisoformat(exp) < now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return data


def get_current_user(request: Request, db: Session = Depends(get_db)) -> DemoUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    claims = decode_token(auth[len("Bearer "):])
    user = db.scalar(select(DemoUser).where(DemoUser.username == claims["sub"], DemoUser.active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


def require_roles(*roles):
    """Dependency factory enforcing role-based access on the backend itself.

    Accepts UserRole members or strings. Bare `require_roles()` means any
    authenticated demo user."""

    coerced = tuple(UserRole(r) for r in roles)

    def checker(user: DemoUser = Depends(get_current_user)) -> DemoUser:
        if coerced and user.role not in coerced:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role.value} is not permitted to perform this action",
            )
        return user

    return checker


any_authenticated = require_roles


READ_ROLES = (UserRole.ADMIN, UserRole.BUREAU_OFFICER, UserRole.REVIEWER, UserRole.READ_ONLY_MANAGER)
CASE_WRITER_ROLES = (UserRole.ADMIN, UserRole.BUREAU_OFFICER)
REVIEWER_ROLES = (UserRole.ADMIN, UserRole.REVIEWER)
ALERT_HANDLER_ROLES = (UserRole.ADMIN, UserRole.BUREAU_OFFICER, UserRole.REVIEWER)
ADMIN_ONLY = (UserRole.ADMIN,)
