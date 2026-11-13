
"""Safely run Project Vigyan reporting tests against vigyan_test."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
COMPOSE_ENV = PROJECT_ROOT / ".env.compose"

TEST_DATABASE = "vigyan_test"
REQUIRED_REVISION = "a2_user_management"

REPORTING_TESTS = [
    "tests/test_reporting_assessment.py",
    "tests/test_reporting_attendance.py",
    "tests/test_reporting_delivery.py",
    "tests/test_reporting_domains.py",
    "tests/test_reporting_engagement.py",
    "tests/test_reporting_exports.py",
    "tests/test_reporting_monthly_management.py",
    "tests/test_reporting_tlm.py",
]


def build_test_database_url() -> URL:
    if not COMPOSE_ENV.is_file():
        raise RuntimeError(".env.compose was not found.")

    values = dotenv_values(COMPOSE_ENV)

    username = values.get("POSTGRES_USER")
    password = values.get("POSTGRES_PASSWORD")
    port = values.get("POSTGRES_HOST_PORT") or "5433"

    if not username or not password:
        raise RuntimeError(
            "POSTGRES_USER or POSTGRES_PASSWORD is missing "
            "from .env.compose."
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=username,
        password=password,
        host="127.0.0.1",
        port=int(port),
        database=TEST_DATABASE,
    )


def verify_database(database_url: URL) -> tuple[str | None, bool, bool]:
    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if database_name != TEST_DATABASE:
                raise RuntimeError(
                    f"Safety check failed: connected to {database_name}; "
                    f"expected {TEST_DATABASE}."
                )

            version_table = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar_one()

            if version_table is None:
                revision = None
            else:
                revisions = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalars().all()

                if len(revisions) > 1:
                    raise RuntimeError(
                        "Multiple Alembic revisions found. "
                        "Manual migration review is required."
                    )

                revision = revisions[0] if revisions else None

            platform_owner_exists = connection.execute(
                text(
                    "SELECT EXISTS "
                    "(SELECT 1 FROM roles WHERE code = :code)"
                ),
                {"code": "PLATFORM_OWNER"},
            ).scalar_one()

            report_permission_exists = connection.execute(
                text(
                    "SELECT EXISTS "
                    "(SELECT 1 FROM permissions WHERE code = :code)"
                ),
                {"code": "report.view"},
            ).scalar_one()

            return (
                revision,
                platform_owner_exists,
                report_permission_exists,
            )
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run reporting tests safely against vigyan_test."
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Not permitted by this runner.",
    )
    args, pytest_args = parser.parse_known_args()

    if args.upgrade:
        print(
            "Refusing --upgrade: this runner never performs migrations.",
            file=sys.stderr,
        )
        return 2

    try:
        database_url = build_test_database_url()
        revision, has_platform_owner, has_report_permission = (
            verify_database(database_url)
        )

        print(f"Verified database: {TEST_DATABASE}")
        print(f"Current Alembic revision: {revision}")
        print(f"Required Alembic revision: {REQUIRED_REVISION}")
        print(f"PLATFORM_OWNER role exists: {has_platform_owner}")
        print(f"report.view permission exists: {has_report_permission}")

        if not has_platform_owner or not has_report_permission:
            print(
                "Reporting test prerequisites are missing. "
                "No seeding will be performed.",
                file=sys.stderr,
            )
            return 2

        if revision != REQUIRED_REVISION:
            print(
                "\nReporting test bootstrap stopped: schema revision mismatch.\n"
                f"Current: {revision}\n"
                f"Required: {REQUIRED_REVISION}\n"
                "This runner will not create databases, migrate schemas, "
                "or seed data. Obtain separate approval before changing "
                "the test database schema.",
                file=sys.stderr,
            )
            return 2

        environment = os.environ.copy()
        database_url_string = database_url.render_as_string(
            hide_password=False
        )

        # Set before importing application modules in the pytest process.
        environment["DATABASE_URL"] = database_url_string
        environment["TEST_DATABASE_URL"] = database_url_string

        command = [
            sys.executable,
            "-m",
            "pytest",
            *REPORTING_TESTS,
            *pytest_args,
        ]

        print("\nRunning reporting tests against verified vigyan_test.")

        result = subprocess.run(
            command,
            cwd=BACKEND_DIR,
            env=environment,
            check=False,
        )

        return result.returncode

    except Exception as error:
        print(
            f"Reporting test bootstrap stopped: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
