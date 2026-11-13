from unittest.mock import Mock

import pytest
from app.main import app
from app.models import User
from app.services.audit import AuditService
from app.services.user_management.service import (
    UserManagementService,
    ValidationError,
)


def test_user_management_routes_match_a2_contract():
    routes = {
        (path, method.upper())
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/api/v1/users")
        for method in methods
    }

    assert {
        ("/api/v1/users", "GET"),
        ("/api/v1/users", "POST"),
        ("/api/v1/users/{user_id}", "GET"),
        ("/api/v1/users/{user_id}", "PATCH"),
        ("/api/v1/users/{user_id}/status", "PATCH"),
        ("/api/v1/users/roles", "GET"),
        ("/api/v1/users/{user_id}/roles", "POST"),
        ("/api/v1/users/{user_id}/roles/{role_id}", "DELETE"),
    } <= routes


def test_audit_service_rejects_secret_metadata():
    db = Mock()
    with pytest.raises(ValueError, match="prohibited secret"):
        AuditService(db).record(
            actor_id=None,
            action="USER_CREATED",
            target_type="USER",
            target_id=None,
            metadata={"password": "must-not-be-recorded"},
        )
    db.add.assert_not_called()


def test_create_user_rejects_invalid_initial_password_before_database_work():
    service = UserManagementService(Mock())
    actor = User()

    with pytest.raises(ValidationError, match="between 12 and 128"):
        service.create_user(
            actor=actor,
            full_name="Test User",
            email="test@example.com",
            initial_password="short",
            account_category="DATA_MANAGER",
        )

    with pytest.raises(ValidationError, match="cannot be blank"):
        service.create_user(
            actor=actor,
            full_name="Test User",
            email="test@example.com",
            initial_password="            ",
            account_category="DATA_MANAGER",
        )
