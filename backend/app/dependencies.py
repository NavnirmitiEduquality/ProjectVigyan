import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Role, RolePermission, UserRole, Permission
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, User


security = HTTPBearer()

SESSION_TIMEOUT_MINUTES = 30


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    auth_session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == token_hash)
        .first()
    )

    if not auth_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    now = datetime.now(timezone.utc)

    if auth_session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked.",
        )

    if now >= auth_session.expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired due to inactivity.",
        )

    user = (
        db.query(User)
        .filter(User.id == auth_session.user_id)
        .first()
    )

    if not user or user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not active.",
        )

    # Refresh the inactivity timeout.
    auth_session.last_activity_at = now
    auth_session.expires_at = (
        now + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    )

    db.commit()

    return user

def require_permission(permission_code: str):
    """
    Require the current user to have a specific permission.

    Platform Owner has unrestricted platform access.
    All other roles must have the requested permission
    through role_permissions.
    """

    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:

        # Platform Owner has full platform access.
        platform_owner = (
            db.query(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                UserRole.user_id == current_user.id,
                UserRole.is_active.is_(True),
                Role.code == "PLATFORM_OWNER",
            )
            .first()
        )

        if platform_owner:
            return current_user

        # All other roles must have the requested permission.
        has_permission = (
            db.query(RolePermission)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .filter(
                UserRole.user_id == current_user.id,
                UserRole.is_active.is_(True),
                Permission.code == permission_code,
            )
            .first()
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return permission_checker