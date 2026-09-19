import hashlib
from datetime import datetime, timedelta, timezone, date

from sqlalchemy import select

from app.models import (
    Role,
    RolePermission,
    UserRole,
    Permission,
    UserAssignment,
)

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, User, UserAssignment


security = HTTPBearer()

SESSION_TIMEOUT_MINUTES = 30

PROJECT_WIDE_ROLES = {
    "PLATFORM_OWNER",
    "SYSTEM_ADMIN",
    "DATA_MANAGER",
    "MANAGEMENT",
    "STEM_COORDINATOR",
}


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

def get_user_role_codes(
    current_user: User,
    db: Session,
) -> set[str]:
    """
    Return all active role codes assigned to the current user.
    """
    roles = (
        db.query(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(
            UserRole.user_id == current_user.id,
            UserRole.is_active.is_(True),
        )
        .all()
    )

    return {role_code for (role_code,) in roles}


def get_authorized_school_ids(
    current_user: User,
    db: Session,
) -> set | None:
    """
    Determine the schools the current user is allowed to access.

    Returns:
        None -> project-wide access
        set[UUID] -> restricted to these schools
    """

    role_codes = get_user_role_codes(current_user, db)

    # Project-wide roles can access all schools.
    if role_codes.intersection(PROJECT_WIDE_ROLES):
        return None

    today = date.today()

    assignments = (
        db.query(UserAssignment)
        .filter(
            UserAssignment.user_id == current_user.id,
            UserAssignment.is_active.is_(True),
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.school_id.is_not(None),
            UserAssignment.start_date <= today,
            (
                UserAssignment.end_date.is_(None)
                | (UserAssignment.end_date >= today)
            ),
        )
        .all()
    )

    return {
        assignment.school_id
        for assignment in assignments
    }


def require_school_access(
    school_id,
    current_user: User,
    db: Session,
):
    """
    Verify that the current user can access a specific school.

    Project-wide users can access any school.
    School-scoped users can access only assigned schools.
    """

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    if authorized_school_ids is None:
        return

    if school_id not in authorized_school_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this school.",
        )
    