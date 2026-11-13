"""Concurrency tests for the last-effective-Platform-Owner invariant."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select, text

from app.database import SessionLocal, engine
from app.models import Role, User, UserRole
from app.models.audit_event import AuditEvent
from app.services.user_management.service import (
    ConflictError,
    UserManagementService,
)


EXPECTED_DATABASE = "vigyan_a2_test"


@pytest.fixture
def two_platform_owners():
    """Create exactly two effective Platform Owners in the isolated DB."""

    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    if database != EXPECTED_DATABASE:
        pytest.fail(
            f"Unsafe concurrency test database: {database}. "
            f"Expected {EXPECTED_DATABASE}."
        )

    session = SessionLocal()
    owner_ids = []
    association_ids = []
    role_created = False
    role_id = None

    try:
        role = (
            session.query(Role)
            .filter(Role.code == "PLATFORM_OWNER")
            .first()
        )

        if role is None:
            role = Role(
                name="Platform Owner",
                code="PLATFORM_OWNER",
                description="A2 concurrency test role",
                is_system_role=True,
            )
            session.add(role)
            session.flush()
            role_created = True

        role_id = role.id

        test_token = uuid4().hex

        owners = [
            User(
                user_code=f"PO{uuid4().hex[:12].upper()}",
                account_category="PLATFORM_OWNER",
                full_name=f"A2 Concurrency Owner {index}",
                email=f"a2-owner-{index}-{test_token}@example.test",
                password_hash="test-only-not-a-real-password-hash",
                status="ACTIVE",
                data_origin="TEST",
            )
            for index in (1, 2)
        ]

        session.add_all(owners)
        session.flush()

        associations = [
            UserRole(
                user_id=owner.id,
                role_id=role.id,
                is_active=True,
            )
            for owner in owners
        ]

        session.add_all(associations)
        session.flush()

        owner_ids = [owner.id for owner in owners]
        association_ids = [association.id for association in associations]

        session.commit()

        yield {
            "owner_ids": owner_ids,
            "association_ids": association_ids,
            "role_id": role_id,
        }

    finally:
        session.rollback()

        if owner_ids:
            session.execute(
                delete(AuditEvent).where(
                    or_(
                        AuditEvent.actor_id.in_(owner_ids),
                        AuditEvent.target_id.in_(
                            owner_ids + association_ids
                        ),
                    )
                )
            )

            session.execute(
                delete(UserRole).where(
                    UserRole.user_id.in_(owner_ids)
                )
            )

            session.execute(
                delete(User).where(User.id.in_(owner_ids))
            )

        if role_created and role_id is not None:
            session.execute(
                delete(Role).where(Role.id == role_id)
            )

        session.commit()
        session.close()


def _run_competing_operations(context, scenario):
    """Run two service operations using independent DB sessions."""

    owner_a, owner_b = context["owner_ids"]
    role_id = context["role_id"]

    barrier = Barrier(2)

    def worker(operation, target_user_id):
        session = SessionLocal()

        try:
            actor = session.get(User, owner_a)
            if actor is None:
                raise AssertionError("Test actor was not found.")

            # Load the actor's role associations before the race.
            # This keeps the test focused on the owner-count invariant.
            for association in actor.user_roles:
                if association.role is not None:
                    _ = association.role.code

            barrier.wait(timeout=15)

            service = UserManagementService(session)

            try:
                if operation == "disable":
                    service.change_status(
                        actor=actor,
                        user_id=target_user_id,
                        new_status="DISABLED",
                    )

                elif operation == "remove_role":
                    service.deactivate_role(
                        actor=actor,
                        user_id=target_user_id,
                        role_id=role_id,
                    )

                else:
                    raise AssertionError(
                        f"Unknown test operation: {operation}"
                    )

                session.commit()
                return "success"

            except ConflictError:
                session.rollback()
                return "conflict"

        finally:
            session.close()

    if scenario == "disable_vs_disable":
        operations = [
            ("disable", owner_a),
            ("disable", owner_b),
        ]
    elif scenario == "remove_vs_remove":
        operations = [
            ("remove_role", owner_a),
            ("remove_role", owner_b),
        ]
    elif scenario == "disable_vs_remove":
        operations = [
            ("disable", owner_a),
            ("remove_role", owner_b),
        ]
    else:
        raise AssertionError(f"Unknown scenario: {scenario}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker, operation, target_id)
            for operation, target_id in operations
        ]

        outcomes = [future.result(timeout=30) for future in futures]

    return outcomes


def _count_effective_platform_owners():
    session = SessionLocal()

    try:
        return (
            session.query(UserRole.id)
            .join(User, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                Role.code == "PLATFORM_OWNER",
                UserRole.is_active.is_(True),
                User.status == "ACTIVE",
            )
            .count()
        )
    finally:
        session.close()


@pytest.mark.parametrize(
    "scenario",
    [
        "disable_vs_disable",
        "remove_vs_remove",
        "disable_vs_remove",
    ],
)
def test_concurrent_owner_removal_preserves_last_owner(
    two_platform_owners,
    scenario,
):
    outcomes = _run_competing_operations(
        two_platform_owners,
        scenario,
    )

    assert sorted(outcomes) == ["conflict", "success"]
    assert _count_effective_platform_owners() == 1
