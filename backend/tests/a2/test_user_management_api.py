
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import (
    AuthSession,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


def ensure_platform_owner_role(db):
    role = db.query(Role).filter(
        Role.code == "PLATFORM_OWNER"
    ).first()

    if role is None:
        role = Role(
            name="Platform Owner",
            code="PLATFORM_OWNER",
            description="A2 test Platform Owner role",
            is_system_role=True,
        )
        db.add(role)
        db.flush()

    return role



def make_api_user(db, *, with_permissions=True):
    token = uuid4().hex

    user = User(
        user_code=f"SA{token[:12].upper()}",
        account_category="SYSTEM_ADMIN",
        full_name="A2 API Administrator",
        email=f"{token}@example.com",
        password_hash="test-only-hash",
        status="ACTIVE",
        data_origin="TEST",
    )

    role = Role(
        name=f"API Role {token[:8]}",
        code=f"API_{token[:12].upper()}",
        description="A2 API test role",
        is_system_role=True,
    )

    db.add_all([user, role])
    db.flush()

    # Create exactly one association for the user's custom API role.
    db.add(
        UserRole(
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )

    if with_permissions:
        for code in (
            "user.view",
            "user.create",
            "user.update",
            "user.disable",
            "role.view",
            "role.update",
        ):
            permission = Permission(
                name=code,
                code=code,
                module="users",
                description="A2 API test permission",
            )
            db.add(permission)
            db.flush()

            db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                )
            )

    # Ensure the role definition exists for service-level locking.
    ensure_platform_owner_role(db)

    raw_token = uuid4().hex + uuid4().hex

    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest(),
            last_activity_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )

    db.flush()

    return user, raw_token


def make_platform_owner_api(db):
    actor, token = make_api_user(db)
    owner_role = ensure_platform_owner_role(db)

    db.add(UserRole(
        user_id=actor.id,
        role_id=owner_role.id,
        is_active=True,
    ))
    db.flush()

    return actor, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authorized_api(client, db_session):
    user, token = make_api_user(db_session)
    return client, user, {"Authorization": f"Bearer {token}"}


def test_user_list_requires_authentication(client):
    response = client.get("/api/v1/users")
    assert response.status_code == 403 or response.status_code == 401


def test_user_list_returns_paginated_envelope(authorized_api):
    client, actor, headers = authorized_api

    response = client.get(
        "/api/v1/users?page=1&page_size=10&status=ACTIVE",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "pagination"}
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 10
    assert body["pagination"]["total"] >= 1

    actor_record = next(
        item for item in body["data"]
        if item["id"] == str(actor.id)
    )
    assert actor_record["data_origin"] == "TEST"
    assert "created_at" in actor_record
    assert "updated_at" in actor_record


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users/not-a-uuid",
        "/api/v1/users/not-a-uuid/status",
        "/api/v1/users/not-a-uuid/roles",
    ],
)
def test_malformed_user_path_uuid_returns_400(authorized_api, path):
    client, _, headers = authorized_api

    if path.endswith("/roles"):
        response = client.post(
            path,
            headers=headers,
            json={"role_id": str(uuid4())},
        )
    elif path.endswith("/status"):
        response = client.patch(
            path,
            headers=headers,
            json={"status": "DISABLED"},
        )
    else:
        response = client.get(path, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_UUID"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"full_name": None},
        {"email": None},
    ],
)
def test_profile_patch_rejects_empty_or_null_fields(
    authorized_api,
    payload,
):
    client, actor, headers = authorized_api

    response = client.patch(
        f"/api/v1/users/{actor.id}",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


def test_user_list_rejects_invalid_pagination(authorized_api):
    client, _, headers = authorized_api

    response = client.get(
        "/api/v1/users?page=0",
        headers=headers,
    )

    assert response.status_code == 422


def test_user_list_requires_user_view_permission(client, db_session):
    user, token = make_api_user(db_session, with_permissions=False)

    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_create_user_api_returns_safe_response(authorized_api, db_session):
    client, actor, headers = authorized_api
    email = f"{uuid4().hex}@example.com"

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "full_name": "New A2 User",
            "email": email,
            "initial_password": "Secure-Initial-Password-123",
            "account_category": "DATA_MANAGER",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "New A2 User"
    assert body["email"] == email
    assert body["account_category"] == "DATA_MANAGER"
    assert body["user_code"].startswith("DM")
    assert body["status"] == "ACTIVE"
    assert body["data_origin"] == "PRODUCTION"
    assert "password" not in body
    assert "password_hash" not in body

    created = db_session.query(User).filter(User.email == email).one()
    assert created.password_hash != "Secure-Initial-Password-123"


def test_profile_update_api_updates_user(authorized_api):
    client, actor, headers = authorized_api
    email = f"{uuid4().hex}@example.com"

    response = client.patch(
        f"/api/v1/users/{actor.id}",
        headers=headers,
        json={
            "full_name": "Updated API User",
            "email": email,
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated API User"
    assert response.json()["email"] == email


def test_disable_and_reactivate_api_preserves_roles_and_revokes_sessions(
    authorized_api,
    db_session,
):
    client, _, headers = authorized_api
    target, _ = make_api_user(db_session, with_permissions=False)

    original_role_ids = {
        association.role_id
        for association in target.user_roles
        if association.is_active
    }

    disabled = client.patch(
        f"/api/v1/users/{target.id}/status",
        headers=headers,
        json={"status": "DISABLED"},
    )

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"

    sessions = (
        db_session.query(AuthSession)
        .filter(AuthSession.user_id == target.id)
        .all()
    )
    assert sessions
    assert all(session.revoked_at is not None for session in sessions)

    reactivated = client.patch(
        f"/api/v1/users/{target.id}/status",
        headers=headers,
        json={"status": "ACTIVE"},
    )

    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "ACTIVE"

    db_session.refresh(target)
    assert {
        association.role_id
        for association in target.user_roles
        if association.is_active
    } == original_role_ids


def test_role_assignment_api_creates_and_reactivates_association(
    client,
    db_session,
):
    actor, headers = make_platform_owner_api(db_session)
    target, _ = make_api_user(db_session, with_permissions=False)

    role = Role(
        name="A2 Assignment Target",
        code=f"TARGET_{uuid4().hex[:12].upper()}",
        description="A2 role assignment API test",
        is_system_role=False,
    )
    db_session.add(role)
    db_session.flush()

    path = f"/api/v1/users/{target.id}/roles"
    payload = {"role_id": str(role.id)}

    created = client.post(path, headers=headers, json=payload)
    assert created.status_code == 201
    assert created.json()["role_id"] == str(role.id)
    assert created.json()["is_active"] is True

    association = (
        db_session.query(UserRole)
        .filter(
            UserRole.user_id == target.id,
            UserRole.role_id == role.id,
        )
        .one()
    )
    association.is_active = False
    db_session.flush()

    reactivated = client.post(path, headers=headers, json=payload)
    assert reactivated.status_code == 200
    assert reactivated.json()["id"] == str(association.id)
    assert reactivated.json()["is_active"] is True


def test_role_removal_api_deactivates_association(client, db_session):
    actor, headers = make_platform_owner_api(db_session)
    target, _ = make_api_user(db_session, with_permissions=False)

    role = Role(
        name="A2 Removal Target",
        code=f"REMOVE_{uuid4().hex[:12].upper()}",
        description="A2 role removal API test",
        is_system_role=False,
    )
    db_session.add(role)
    db_session.flush()

    association = UserRole(
        user_id=target.id,
        role_id=role.id,
        is_active=True,
    )
    db_session.add(association)
    db_session.flush()

    response = client.delete(
        f"/api/v1/users/{target.id}/roles/{role.id}",
        headers=headers,
    )

    assert response.status_code == 204
    db_session.refresh(association)
    assert association.is_active is False


def test_role_removal_api_rejects_malformed_uuids(authorized_api):
    client, actor, headers = authorized_api

    response = client.delete(
        f"/api/v1/users/{actor.id}/roles/not-a-uuid",
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_UUID"
