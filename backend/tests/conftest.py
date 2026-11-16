import pytest
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app


@pytest.fixture
def reporting_db():
    """
    Keep all reporting-test database activity inside one outer transaction.

    Session commits and rollbacks use savepoints. The outer transaction
    is always rolled back when the fixture finishes.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()

    db = Session(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    missing = object()
    previous_override = app.dependency_overrides.get(get_db, missing)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield db
    finally:
        if previous_override is missing:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

        db.close()

        if outer_transaction.is_active:
            outer_transaction.rollback()

        connection.close()


from tests.test_reporting_attendance import reporting_fixture

__all__ = ["reporting_fixture", "reporting_db"]
