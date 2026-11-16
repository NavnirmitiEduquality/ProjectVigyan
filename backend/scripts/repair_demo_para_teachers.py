"""
Safely provision the four Project Vigyan DEMO Para-Teacher accounts.

This script does not create or modify schools, class divisions, students,
Data Managers, or existing user accounts.
"""

import os
import sys
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Role,
    School,
    User,
    UserAssignment,
    UserRole,
)
from app.services.auth_service import hash_password


load_dotenv()

DATA_ORIGIN = "DEMO"
PASSWORD_ENV = "DEMO_USER_PASSWORD"
ASSIGNMENT_START_DATE = date(2026, 1, 1)

PARA_TEACHERS = [
    {
        "user_code": "PT001",
        "full_name": "Anaya Deshmukh",
        "email": "pt001@demo.vigyan.com",
        "school_code": "PVS",
        "school_name": "Pragati Vidya School",
    },
    {
        "user_code": "PT002",
        "full_name": "Rohan Kulkarni",
        "email": "pt002@demo.vigyan.com",
        "school_code": "NLS",
        "school_name": "Navnirmiti Learning School",
    },
    {
        "user_code": "PT003",
        "full_name": "Meera Patil",
        "email": "pt003@demo.vigyan.com",
        "school_code": "SHY",
        "school_name": "Sahyadri",
    },
    {
        "user_code": "PT004",
        "full_name": "Arjun Nair",
        "email": "pt004@demo.vigyan.com",
        "school_code": "UECL",
        "school_name": "Udaan Education Centre for Learning",
    },
]


def get_password() -> str:
    password = os.getenv(PASSWORD_ENV)

    if not password:
        raise RuntimeError(f"{PASSWORD_ENV} is not configured.")

    if len(password) < 12:
        raise RuntimeError(
            f"{PASSWORD_ENV} must contain at least 12 characters."
        )

    return password


def provision() -> None:
    password_hash = hash_password(get_password())
    db = SessionLocal()

    try:
        with db.begin():
            # Verify the expected role exists.
            para_teacher_role = db.scalar(
                select(Role).where(Role.code == "PARA_TEACHER")
            )

            if para_teacher_role is None:
                raise RuntimeError(
                    "PARA_TEACHER role not found. "
                    "Run seed_roles_permissions.py first."
                )

            # Verify all four existing schools. Do not create schools.
            school_codes = {
                item["school_code"] for item in PARA_TEACHERS
            }

            schools_found = db.scalars(
                select(School)
                .where(School.school_code.in_(school_codes))
                .with_for_update()
            ).all()

            schools = {
                school.school_code: school
                for school in schools_found
            }

            for item in PARA_TEACHERS:
                school = schools.get(item["school_code"])

                if school is None:
                    raise RuntimeError(
                        f"Required school {item['school_code']} "
                        "does not exist. No accounts were created."
                    )

                if school.school_name != item["school_name"]:
                    raise RuntimeError(
                        f"School name mismatch for {item['school_code']}: "
                        f"found '{school.school_name}'. "
                        "No accounts were created."
                    )

            # Refuse any existing user-code or email collision.
            user_codes = {item["user_code"] for item in PARA_TEACHERS}
            emails = {item["email"] for item in PARA_TEACHERS}

            existing_users = db.scalars(
                select(User).where(
                    (User.user_code.in_(user_codes))
                    | (User.email.in_(emails))
                )
            ).all()

            if existing_users:
                conflicts = [
                    f"{user.user_code} / {user.email}"
                    for user in existing_users
                ]
                raise RuntimeError(
                    "Existing user conflicts detected. "
                    "No accounts were changed:\n"
                    + "\n".join(conflicts)
                )

            print("Pre-checks passed.")
            print("Existing schools verified: 4")
            print("PARA_TEACHER role verified.")
            print("No user-code or email conflicts found.")
            print()

            for item in PARA_TEACHERS:
                user = User(
                    user_code=item["user_code"],
                    account_category="PARA_TEACHER",
                    full_name=item["full_name"],
                    email=item["email"],
                    password_hash=password_hash,
                    status="ACTIVE",
                    data_origin=DATA_ORIGIN,
                )

                db.add(user)
                db.flush()

                db.add(
                    UserRole(
                        user_id=user.id,
                        role_id=para_teacher_role.id,
                        is_active=True,
                    )
                )

                db.add(
                    UserAssignment(
                        user_id=user.id,
                        scope_type="SCHOOL",
                        school_id=schools[item["school_code"]].id,
                        start_date=ASSIGNMENT_START_DATE,
                        end_date=None,
                        is_active=True,
                    )
                )

                print(
                    f"Prepared {item['user_code']}: "
                    f"{item['email']} -> {item['school_code']}"
                )

        print()
        print("SUCCESS: Four DEMO Para Teacher accounts provisioned.")
        print("Four active PARA_TEACHER roles created.")
        print("Four active SCHOOL assignments created.")
        print("All changes committed in one transaction.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    try:
        provision()
    except Exception as exc:
        print()
        print("ERROR:")
        print(exc)
        sys.exit(1)
