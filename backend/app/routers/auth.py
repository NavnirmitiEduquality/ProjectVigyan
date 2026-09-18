from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.dependencies import require_permission, get_current_user

from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.models import AuthSession, User
from app.database import get_db
from app.models import AuthSession, User
from app.services.auth_service import (
    generate_session_token,
    hash_session_token,
    verify_password,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


SESSION_TIMEOUT_MINUTES = 30
security = HTTPBearer()

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    message: str
    user_id: str
    user_code: str
    full_name: str
    session_token: str


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.email == request.email.lower())
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)

    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        last_activity_at=now,
        expires_at=expires_at,
    )

    user.last_login_at = now

    db.add(auth_session)
    db.commit()

    return LoginResponse(
        message="Login successful.",
        user_id=str(user.id),
        user_code=user.user_code,
        full_name=user.full_name,
        session_token=session_token,
    )

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "user_id": str(current_user.id),
        "user_code": current_user.user_code,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "status": current_user.status,
    }


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    token_hash = hash_session_token(token)

    auth_session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == token_hash)
        .first()
    )

    if auth_session and auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    return {
        "message": "Logout successful."
    }

@router.get("/rbac-test")
def rbac_test(
    current_user: User = Depends(
        require_permission("audit.view")
    ),
):
    return {
        "message": "RBAC authorization successful.",
        "user_code": current_user.user_code,
        "required_permission": "audit.view",
    }

