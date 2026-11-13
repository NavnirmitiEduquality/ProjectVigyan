
"""Database fixtures for isolated Project Vigyan A2 tests."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.database import engine, get_db
from app.main import app


EXPECTED_DATABASE = "vigyan_a2_test"


@pytest.fixture(scope="session", autouse=True)
def verify_a2_test_database():
    """Refuse to run A2 tests against any other database."""

    configured_url = os.environ.get("TEST_DATABASE_URL")
    if not configured_url:
        pytest.exit(
            "TEST_DATABASE_URL is required. "
            "Use scripts/run_a2_tests.py.",
            returncode=2,
        )
    configured_engine_url = make_url(configured_url)

    if (
        configured_engine_url.drivername != engine.url.drivername
        or configured_engine_url.username != engine.url.username
        or configured_engine_url.host != engine.url.host
        or configured_engine_url.port != engine.url.port
        or configured_engine_url.database != engine.url.database
    ):
        pytest.exit(
            "TEST_DATABASE_URL does not match the application DATABASE_URL.",
            returncode=2,
        )

    if engine.url.database != EXPECTED_DATABASE:
        pytest.exit(
            f"Unsafe database configuration: expected "
            f"{EXPECTED_DATABASE}, got {engine.url.database}.",
            returncode=2,
        )

    if engine.url.database in {"vigyan_compose", "vigyan_test"}:
        pytest.exit(
            "Refusing to run A2 tests against an existing application "
            "or shared test database.",
            returncode=2,
        )

    with engine.connect() as connection:
        actual_database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if actual_database != EXPECTED_DATABASE:
            pytest.exit(
                f"Connected to unexpected database: {actual_database}.",
                returncode=2,
            )


@pytest.fixture
def db_connection(verify_a2_test_database):
    """Provide a connection protected by an outer rollback transaction."""

    connection = engine.connect()
    transaction = connection.begin()

    try:
        yield connection
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def db_session(db_connection):
    """Provide a session whose changes are rolled back after each test."""

    session = Session(
        bind=db_connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """Provide a TestClient using the isolated test transaction."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
