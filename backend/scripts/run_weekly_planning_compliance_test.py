"""Run the weekly planning job in dry-run mode against vigyan_test only."""

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
JOB_SCRIPT = BACKEND_DIR / "scripts" / "run_weekly_planning_compliance.py"


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


def verify_database(database_url: URL) -> None:
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

            revisions = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all()

            if revisions != [REQUIRED_REVISION]:
                raise RuntimeError(
                    f"Unexpected Alembic revision state: {revisions}; "
                    f"expected [{REQUIRED_REVISION}]."
                )

            print(f"Verified database: {database_name}")
            print(f"Verified Alembic revision: {revisions[0]}")

    finally:
        engine.dispose()


def main() -> int:
    if not JOB_SCRIPT.is_file():
        print("Weekly compliance job script was not found.", file=sys.stderr)
        return 1

    try:
        database_url = build_test_database_url()
        verify_database(database_url)

        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url.render_as_string(
            hide_password=False
        )

        command = [
            sys.executable,
            "-m",
            "scripts.run_weekly_planning_compliance",
            "--date",
            "2026-11-21",
            "--dry-run",
        ]

        print(
            "Starting isolated weekly compliance dry-run "
            "against vigyan_test."
        )

        result = subprocess.run(
            command,
            cwd=BACKEND_DIR,
            env=environment,
            check=False,
        )

        return result.returncode

    except Exception as error:
        print(
            f"Weekly compliance dry-run bootstrap stopped: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
