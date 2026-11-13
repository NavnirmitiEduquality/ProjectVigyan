
"""Safely run A2 tests against the dedicated vigyan_a2_test database."""

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
TEST_DATABASE = "vigyan_a2_test"
REQUIRED_REVISION = "a2_user_management"


def build_test_database_url() -> URL:
    if not COMPOSE_ENV.is_file():
        raise RuntimeError("Project .env.compose file was not found.")

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


def verify_database(database_url: URL) -> str | None:
    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if database_name != TEST_DATABASE:
                raise RuntimeError(
                    f"Safety check failed: connected to {database_name}, "
                    f"expected {TEST_DATABASE}."
                )

            version_table = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar_one()

            if version_table is None:
                return None

            revisions = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all()

            if len(revisions) > 1:
                raise RuntimeError(
                    "Test database has multiple Alembic revisions. "
                    "Manual migration review is required."
                )

            return revisions[0] if revisions else None

    finally:
        engine.dispose()



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Project Vigyan A2 tests safely."
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Explicitly upgrade only vigyan_a2_test to Alembic head.",
    )
    args, pytest_args = parser.parse_known_args()

    try:
        database_url = build_test_database_url()
        database_url_string = database_url.render_as_string(
            hide_password=False
        )

        environment = os.environ.copy()

        # Set before importing any application modules in the child process.
        environment["DATABASE_URL"] = database_url_string
        environment["TEST_DATABASE_URL"] = database_url_string

        current_revision = verify_database(database_url)

        print(f"Verified database: {TEST_DATABASE}")

        if args.upgrade:
            print("Explicit test-database migration requested.")

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "upgrade",
                    "head",
                ],
                cwd=BACKEND_DIR,
                env=environment,
                check=True,
            )

            current_revision = verify_database(database_url)

        if current_revision != REQUIRED_REVISION:
            print(
                "A2 test database is not at the required revision.\n"
                f"Current revision: {current_revision}\n"
                f"Required revision: {REQUIRED_REVISION}\n"
                "Review the migration, then explicitly run this script "
                "with --upgrade."
            )
            return 2

        command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/a2",
            *pytest_args,
        ]

        print("Running A2 tests against the verified test database.")

        result = subprocess.run(
            command,
            cwd=BACKEND_DIR,
            env=environment,
            check=False,
        )

        return result.returncode

    except Exception as error:
        print(f"A2 test bootstrap stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
