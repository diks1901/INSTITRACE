"""Demo authentication endpoints (local demo mode - not production security)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DemoUser
from ..schemas import CurrentUser, LoginRequest, LoginResponse
from ..security import create_token, get_current_user, verify_password
from fastapi import HTTPException

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_NOTICE = (
    "Local demo mode: synthetic users and demo-grade token signing. "
    "This is NOT production security and does not authenticate real AICTE officials."
)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(DemoUser).where(DemoUser.username == payload.username))
    if user is None or not user.active or not verify_password(
        payload.password, user.password_salt, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return LoginResponse(
        token=create_token(user.username, user.role.value),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        demo_notice=DEMO_NOTICE,
    )


@router.get("/me", response_model=CurrentUser)
def me(user: DemoUser = Depends(get_current_user)):
    return CurrentUser(username=user.username, display_name=user.display_name, role=user.role)
