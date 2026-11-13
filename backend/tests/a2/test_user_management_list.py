
from uuid import uuid4

import pytest

from app.models import Role, User, UserRole
from app.services.user_management.service import (
    UserManagementService,
    ValidationError,
)


def make_list_user(
    db,
    *,
    name,
    status="ACTIVE",
    origin="PRODUCTION",
):
    token = uuid4().hex
    user = User(
        user_code=f"DM{token[:12].upper()}",
        account_category="DATA_MANAGER",
        full_name=name,
        email=f"{token}@example.com",
        password_hash="test-only-hash",
        status=status,
        data_origin=origin,
    )
    db.add(user)
    db.flush()
    return user


def test_list_users_paginates_and_reports_total(db_session):
    for index in range(5):
        make_list_user(db_session, name=f"List User {index}")

    result = UserManagementService(db_session).list_users(
        page=2,
        page_size=2,
        sort_by="user_code",
        sort_order="asc",
    )

    assert len(result["data"]) == 2
    assert result["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 5,
        "total_pages": 3,
    }


def test_list_users_searches_name_email_and_code(db_session):
    user = make_list_user(db_session, name="Unique Search Name")
    service = UserManagementService(db_session)

    assert service.list_users(
        search="unique search"
    )["pagination"]["total"] == 1

    assert service.list_users(
        search=user.email[:12]
    )["pagination"]["total"] == 1

    assert service.list_users(
        search=user.user_code
    )["pagination"]["total"] == 1


def test_list_users_filters_status_and_origin(db_session):
    make_list_user(db_session, name="Active Production")
    disabled = make_list_user(
        db_session,
        name="Disabled Demo",
        status="DISABLED",
        origin="DEMO",
    )

    result = UserManagementService(db_session).list_users(
        status="DISABLED",
        data_origin="DEMO",
    )

    assert result["pagination"]["total"] == 1
    assert result["data"][0].id == disabled.id


def test_list_users_filters_only_active_role_associations(db_session):
    role = Role(name="List Role", code="LIST_ROLE")
    db_session.add(role)
    db_session.flush()

    active_user = make_list_user(db_session, name="Active Role User")
    inactive_user = make_list_user(db_session, name="Inactive Role User")

    db_session.add_all([
        UserRole(
            user_id=active_user.id,
            role_id=role.id,
            is_active=True,
        ),
        UserRole(
            user_id=inactive_user.id,
            role_id=role.id,
            is_active=False,
        ),
    ])
    db_session.flush()

    result = UserManagementService(db_session).list_users(
        role_code="LIST_ROLE",
    )

    assert [user.id for user in result["data"]] == [active_user.id]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"status": "UNKNOWN"},
        {"data_origin": "UNKNOWN"},
        {"sort_by": "password_hash"},
        {"sort_order": "sideways"},
    ],
)
def test_list_users_rejects_invalid_parameters(db_session, kwargs):
    with pytest.raises(ValidationError):
        UserManagementService(db_session).list_users(**kwargs)
