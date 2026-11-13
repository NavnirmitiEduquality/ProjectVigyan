"""Database-backed tests for A2 user-management service operations."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import AuthSession, AuditEvent, Role, User, UserRole
from app.services.auth_service import verify_password
from app.services.user_management.service import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UserManagementService,
    ValidationError,
)


def make_user(
    db,
    *,
    category="PLATFORM_OWNER",
    name="A2 Test User",
    status="ACTIVE",
):
    token = uuid4().hex
    user = User(
        user_code=f"PO{token[:12].upper()}",
        account_category=category,
        full_name=name,
        email=f"{token}@example.com",
        password_hash="test-only-password-hash",
        status=status,
        data_origin="TEST",
    )
    db.add(user)
    db.flush()
    return user


def make_role(db, code, name=None):
    role = db.query(Role).filter(Role.code == code).first()
    if role:
        return role

    role = Role(
        name=name or code.replace("_", " ").title(),
        code=code,
        description="A2 service test role",
        is_system_role=True,
    )
    db.add(role)
    db.flush()
    return role


def assign_role(db, user, role, *, active=True):
    association = UserRole(
        user_id=user.id,
        role_id=role.id,
        is_active=active,
    )
    db.add(association)
    db.flush()
    return association


@pytest.fixture
def platform_owner(db_session):
    user = make_user(db_session)
    role = make_role(db_session, "PLATFORM_OWNER")
    assign_role(db_session, user, role)
    return user


@pytest.fixture
def service(db_session):
    return UserManagementService(db_session)


def test_create_user_normalizes_fields_and_hashes_password(
    db_session,
    service,
    platform_owner,
):
    password = "A2-Initial-Password-123"

    user = service.create_user(
        actor=platform_owner,
        full_name="  New Data Manager  ",
        email="  NEW.DATA@example.com ",
        initial_password=password,
        account_category="DATA_MANAGER",
    )

    assert user.account_category == "DATA_MANAGER"
    assert user.user_code.startswith("DM")
    assert user.full_name == "New Data Manager"
    assert user.email == "new.data@example.com"
    assert user.status == "ACTIVE"
    assert user.data_origin == "PRODUCTION"
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)

    event = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "USER_CREATED",
            AuditEvent.target_id == user.id,
        )
        .one()
    )
    assert event.outcome == "SUCCESS"
    assert event.metadata_ == {
        "user_code": user.user_code,
        "account_category": "DATA_MANAGER",
    }


@pytest.mark.parametrize(
    ("category", "prefix"),
    [
        ("PLATFORM_OWNER", "PO"),
        ("SYSTEM_ADMIN", "SA"),
        ("DATA_MANAGER", "DM"),
        ("MANAGEMENT", "MG"),
        ("STEM_COORDINATOR", "SC"),
        ("PARA_TEACHER", "PT"),
    ],
)
def test_create_user_uses_category_prefix(
    db_session,
    service,
    platform_owner,
    category,
    prefix,
):
    user = service.create_user(
        actor=platform_owner,
        full_name="Prefix Test",
        email=f"{uuid4().hex}@example.com",
        initial_password="Valid-Initial-Password-123",
        account_category=category,
    )

    assert user.user_code.startswith(prefix)


def test_create_user_rejects_invalid_category(
    service,
    platform_owner,
):
    with pytest.raises(ValidationError, match="Invalid account category"):
        service.create_user(
            actor=platform_owner,
            full_name="Invalid Category",
            email="invalid-category@example.com",
            initial_password="Valid-Initial-Password-123",
            account_category="UNKNOWN",
        )


@pytest.mark.parametrize(
    ("name", "email", "password"),
    [
        ("   ", "blank-name@example.com", "Valid-Initial-Password-123"),
        ("Valid Name", "not-an-email", "Valid-Initial-Password-123"),
        ("Valid Name", "blank-password@example.com", "            "),
        ("Valid Name", "short-password@example.com", "Short123"),
        ("Valid Name", "long-password@example.com", "A" * 129),
    ],
)
def test_create_user_rejects_invalid_fields(
    service,
    platform_owner,
    name,
    email,
    password,
):
    with pytest.raises(ValidationError):
        service.create_user(
            actor=platform_owner,
            full_name=name,
            email=email,
            initial_password=password,
            account_category="DATA_MANAGER",
        )


def test_create_user_rejects_duplicate_email(
    db_session,
    service,
    platform_owner,
):
    existing = make_user(db_session, category="DATA_MANAGER")

    with pytest.raises(ConflictError, match="email already exists"):
        service.create_user(
            actor=platform_owner,
            full_name="Duplicate Email",
            email=existing.email.upper(),
            initial_password="Valid-Initial-Password-123",
            account_category="DATA_MANAGER",
        )


def test_update_profile_changes_name_and_email_and_clears_verification(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")
    target.email_verified_at = datetime.now(timezone.utc)
    db_session.flush()

    updated = service.update_profile(
        actor=platform_owner,
        user_id=target.id,
        full_name="  Updated Name  ",
        email=" UPDATED@example.com ",
    )

    assert updated.full_name == "Updated Name"
    assert updated.email == "updated@example.com"
    assert updated.email_verified_at is None

    event = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "USER_PROFILE_UPDATED",
            AuditEvent.target_id == target.id,
        )
        .one()
    )
    assert event.metadata_ == {"fields": ["email", "full_name"]}


def test_update_profile_preserves_verification_when_email_unchanged(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")
    verified_at = datetime.now(timezone.utc)
    target.email_verified_at = verified_at
    db_session.flush()

    updated = service.update_profile(
        actor=platform_owner,
        user_id=target.id,
        full_name="Name Only Update",
        email=target.email,
    )

    assert updated.full_name == "Name Only Update"
    assert updated.email_verified_at == verified_at


def test_update_profile_rejects_duplicate_email(
    db_session,
    service,
    platform_owner,
):
    first = make_user(db_session, category="DATA_MANAGER")
    second = make_user(db_session, category="MANAGEMENT")

    with pytest.raises(ConflictError, match="email already exists"):
        service.update_profile(
            actor=platform_owner,
            user_id=second.id,
            full_name=None,
            email=first.email,
        )


def test_update_profile_rejects_empty_update(
    service,
    platform_owner,
):
    target_id = uuid4()

    with pytest.raises(NotFoundError):
        service.update_profile(
            actor=platform_owner,
            user_id=target_id,
            full_name=None,
            email=None,
        )


def test_update_profile_rejects_blank_name(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")

    with pytest.raises(ValidationError, match="cannot be blank"):
        service.update_profile(
            actor=platform_owner,
            user_id=target.id,
            full_name="   ",
            email=None,
        )


def test_change_status_disables_user_and_revokes_sessions(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")

    sessions = [
        AuthSession(
            user_id=target.id,
            token_hash=f"test-token-{uuid4().hex}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        for _ in range(2)
    ]
    db_session.add_all(sessions)
    db_session.flush()

    service.change_status(
        actor=platform_owner,
        user_id=target.id,
        new_status="DISABLED",
    )

    assert target.status == "DISABLED"

    for auth_session in sessions:
        db_session.refresh(auth_session)

    assert all(
        auth_session.revoked_at is not None
        for auth_session in sessions
    )

    actions = {
        event.action
        for event in db_session.query(AuditEvent)
        .filter(AuditEvent.target_id == target.id)
        .all()
    }
    assert "USER_DISABLED" in actions
    assert "USER_SESSIONS_REVOKED" in actions


def test_change_status_reactivation_preserves_role_association(
    db_session,
    service,
    platform_owner,
):
    target = make_user(
        db_session,
        category="DATA_MANAGER",
        status="DISABLED",
    )
    role = make_role(db_session, "DATA_MANAGER")
    association = assign_role(db_session, target, role, active=True)

    service.change_status(
        actor=platform_owner,
        user_id=target.id,
        new_status="ACTIVE",
    )

    assert target.status == "ACTIVE"
    assert association.is_active is True


def test_change_status_is_idempotent(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")

    service.change_status(
        actor=platform_owner,
        user_id=target.id,
        new_status="ACTIVE",
    )

    event_count = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.target_id == target.id,
            AuditEvent.action.in_(
                ["USER_DISABLED", "USER_REACTIVATED"]
            ),
        )
        .count()
    )

    assert event_count == 0


def test_change_status_rejects_invalid_status(
    service,
    platform_owner,
):
    with pytest.raises(ValidationError, match="Invalid account status"):
        service.change_status(
            actor=platform_owner,
            user_id=uuid4(),
            new_status="PENDING",
        )


def test_last_platform_owner_cannot_be_disabled(
    db_session,
    service,
    platform_owner,
):
    with pytest.raises(ConflictError, match="last effective Platform Owner"):
        service.change_status(
            actor=platform_owner,
            user_id=platform_owner.id,
            new_status="DISABLED",
        )

    assert platform_owner.status == "ACTIVE"


def test_role_assignment_and_reactivation(
    db_session,
    service,
    platform_owner,
):
    target = make_user(db_session, category="DATA_MANAGER")
    role = make_role(db_session, "SYSTEM_ADMIN")

    association = assign_role(
        db_session,
        target,
        role,
        active=False,
    )

    result = service.assign_role(
        actor=platform_owner,
        user_id=target.id,
        role_id=role.id,
    )

    assert result.id == association.id
    assert result.is_active is True

    with pytest.raises(ConflictError, match="already has this role"):
        service.assign_role(
            actor=platform_owner,
            user_id=target.id,
            role_id=role.id,
        )


def test_system_admin_cannot_grant_platform_owner(
    db_session,
    service,
):
    actor = make_user(db_session, category="SYSTEM_ADMIN")
    system_admin_role = make_role(db_session, "SYSTEM_ADMIN")
    owner_role = make_role(db_session, "PLATFORM_OWNER")
    assign_role(db_session, actor, system_admin_role)

    target = make_user(db_session, category="DATA_MANAGER")

    with pytest.raises(ForbiddenError):
        service.assign_role(
            actor=actor,
            user_id=target.id,
            role_id=owner_role.id,
        )


def test_only_platform_owner_can_remove_roles(
    db_session,
    service,
):
    actor = make_user(db_session, category="SYSTEM_ADMIN")
    system_admin_role = make_role(db_session, "SYSTEM_ADMIN")
    target_role = make_role(db_session, "DATA_MANAGER")
    assign_role(db_session, actor, system_admin_role)

    target = make_user(db_session, category="DATA_MANAGER")
    association = assign_role(db_session, target, target_role)

    with pytest.raises(ForbiddenError):
        service.deactivate_role(
            actor=actor,
            user_id=target.id,
            role_id=target_role.id,
        )

    assert association.is_active is True


def test_last_platform_owner_role_cannot_be_removed(
    db_session,
    service,
    platform_owner,
):
    owner_role = make_role(db_session, "PLATFORM_OWNER")

    with pytest.raises(ConflictError, match="last effective Platform Owner"):
        service.deactivate_role(
            actor=platform_owner,
            user_id=platform_owner.id,
            role_id=owner_role.id,
        )

    association = (
        db_session.query(UserRole)
        .filter(
            UserRole.user_id == platform_owner.id,
            UserRole.role_id == owner_role.id,
        )
        .one()
    )
    assert association.is_active is True
