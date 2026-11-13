
"""Apply A2 migration to vigyan_test only. Never runs tests or seeds data."""

from pathlib import Path
import re
import subprocess
import sys

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine, text


BACKEND = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND.parent / ".env.compose"
DATABASE = "vigyan_test"
EXPECTED_REVISION = "9b0039300e28"
TARGET_REVISION = "a2_user_management"

CATEGORY_RULES = [
    (re.compile(r"^PO[0-9]+$"), "PLATFORM_OWNER"),
    (re.compile(r"^SA[0-9]+$"), "SYSTEM_ADMIN"),
    (re.compile(r"^DM[0-9]+$"), "DATA_MANAGER"),
    (re.compile(r"^MG[0-9]+$"), "MANAGEMENT"),
    (re.compile(r"^SC[0-9]+$"), "STEM_COORDINATOR"),
    (re.compile(r"^PT[0-9]+$"), "PARA_TEACHER"),
    (re.compile(r"^PT-[0-9a-f]{8}$"), "PARA_TEACHER"),
]

SPECIAL_CATEGORIES = {
    "AA-M-57876db19e": "SYSTEM_ADMIN",
    "AA-V-57876db19e": "MANAGEMENT",
    "PV-QA-PARATEACHER-01": "PARA_TEACHER",
}


def category_for(code):
    if code in SPECIAL_CATEGORIES:
        return SPECIAL_CATEGORIES[code]
    for pattern, category in CATEGORY_RULES:
        if pattern.fullmatch(code):
            return category
    return None


def database_url():
    values = dotenv_values(ENV_FILE)
    username = values.get("POSTGRES_USER")
    password = values.get("POSTGRES_PASSWORD")
    port = int(values.get("POSTGRES_HOST_PORT") or "5433")

    if not username or not password:
        raise RuntimeError("Missing PostgreSQL credentials in .env.compose")

    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host="127.0.0.1",
        port=port,
        database=DATABASE,
    )


def inspect_database(url):
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            name = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()
            revisions = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all()

            if name != DATABASE:
                raise RuntimeError(f"Refusing database {name}")
            if revisions != [EXPECTED_REVISION]:
                raise RuntimeError(f"Unexpected revision: {revisions}")

            users = conn.execute(
                text("SELECT user_code FROM users ORDER BY user_code")
            ).scalars().all()

            mapping = {code: category_for(code) for code in users}
            unresolved = [code for code, cat in mapping.items() if cat is None]
            if unresolved:
                raise RuntimeError(f"Unresolved users: {unresolved}")

            counts = {
                "users": conn.execute(
                    text("SELECT count(*) FROM users")
                ).scalar_one(),
                "user_roles": conn.execute(
                    text("SELECT count(*) FROM user_roles")
                ).scalar_one(),
                "user_assignments": conn.execute(
                    text("SELECT count(*) FROM user_assignments")
                ).scalar_one(),
            }

            return counts, mapping
    finally:
        engine.dispose()


def main():
    if not ENV_FILE.is_file():
        raise RuntimeError(".env.compose not found")

    url = database_url()
    before, mapping = inspect_database(url)

    print(f"Target database: {DATABASE}")
    print(f"Current revision: {EXPECTED_REVISION}")
    print(f"Target revision: {TARGET_REVISION}")
    print(f"Pre-migration counts: {before}")
    print(f"Mapped users: {len(mapping)}")

    # The URL is passed explicitly to Alembic; no application .env
    # or default DATABASE_URL can redirect this migration.
    import os
    env = os.environ.copy()
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            TARGET_REVISION,
        ],
        cwd=BACKEND,
        env=env,
        check=True,
    )

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if revision != TARGET_REVISION:
                raise RuntimeError(f"Unexpected resulting revision: {revision}")

            after = {
                "users": conn.execute(
                    text("SELECT count(*) FROM users")
                ).scalar_one(),
                "user_roles": conn.execute(
                    text("SELECT count(*) FROM user_roles")
                ).scalar_one(),
                "user_assignments": conn.execute(
                    text("SELECT count(*) FROM user_assignments")
                ).scalar_one(),
            }

            if before != after:
                raise RuntimeError(
                    f"Existing record counts changed: before={before}, after={after}"
                )

            categories = conn.execute(
                text("""
                    SELECT account_category, count(*)
                    FROM users
                    GROUP BY account_category
                    ORDER BY account_category
                """)
            ).all()

            print("Verified database:", DATABASE)
            print("Verified revision:", revision)
            print("Verified counts:", after)
            print("Account categories:", categories)
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"MIGRATION STOPPED: {exc}", file=sys.stderr)
        raise SystemExit(1)
