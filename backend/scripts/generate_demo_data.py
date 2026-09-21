"""
Generate deterministic synthetic demo data for Project Vigyan.

This script creates only:
- Schools
- Class divisions
- Students
- Para-Teacher users
- User roles
- School assignments

It does NOT create:
- Sessions
- Attendance
- Assessments
- TLM records
- Feedback
- Evidence

Usage:
    python -m scripts.generate_demo_data

Reset demo data:
    python -m scripts.generate_demo_data --reset

The generator is intentionally synthetic and must never be populated
with real student data.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.database import SessionLocal
from app.models import (
    ClassDivision,
    Role,
    School,
    Student,
    User,
    UserAssignment,
    UserRole,
)
from app.services.auth_service import hash_password


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

RANDOM_SEED = 20260919

DATA_ORIGIN = "DEMO"

EXPECTED_SCHOOL_COUNT = 4
EXPECTED_CLASS_DIVISION_COUNT = 12
EXPECTED_STUDENT_COUNT = 580
EXPECTED_PARA_TEACHER_COUNT = 4
EXPECTED_DATA_MANAGER_COUNT = 1

EXPECTED_SCHOOL_ASSIGNMENT_COUNT = 4
EXPECTED_PROJECT_ASSIGNMENT_COUNT = 1
EXPECTED_ASSIGNMENT_COUNT = 5

DEMO_USER_PASSWORD_ENV = "DEMO_USER_PASSWORD"


# ---------------------------------------------------------------------------
# Synthetic school configuration
# ---------------------------------------------------------------------------

SCHOOLS = [
    {
        "code": "PVS",
        "name": "Pragati Vidya School",
        "total_students": 255,
    },
    {
        "code": "NLS",
        "name": "Navnirmiti Learning School",
        "total_students": 76,
    },
    {
        "code": "SHY",
        "name": "Sahyadri",
        "total_students": 194,
    },
    {
        "code": "UECL",
        "name": "Udaan Education Centre for Learning",
        "total_students": 55,
    },
]


# school_code, class_level, division, student_count
CLASS_DISTRIBUTION = [
    ("PVS", 5, "A", 78),
    ("PVS", 6, "C", 92),
    ("PVS", 7, "B", 85),
    ("NLS", 5, "B", 31),
    ("NLS", 6, "A", 25),
    ("NLS", 7, "C", 20),
    ("SHY", 5, "C", 64),
    ("SHY", 6, "B", 71),
    ("SHY", 7, "A", 59),
    ("UECL", 5, "A", 24),
    ("UECL", 6, "C", 12),
    ("UECL", 7, "B", 19),
]


PARA_TEACHERS = [
    {
        "user_code": "PT001",
        "full_name": "Anaya Deshmukh",
        "email": "pt001@demo.vigyan.com",
        "school_code": "PVS",
    },
    {
        "user_code": "PT002",
        "full_name": "Rohan Kulkarni",
        "email": "pt002@demo.vigyan.com",
        "school_code": "NLS",
    },
    {
        "user_code": "PT003",
        "full_name": "Meera Patil",
        "email": "pt003@demo.vigyan.com",
        "school_code": "SHY",
    },
    {
        "user_code": "PT004",
        "full_name": "Arjun Nair",
        "email": "pt004@demo.vigyan.com",
        "school_code": "UECL",
    },
]

DATA_MANAGERS = [
    {
        "user_code": "DM001",
        "full_name": "Demo Data Manager",
        "email": "dm001@demo.vigyan.com",
    },
]
# ---------------------------------------------------------------------------
# Synthetic name pools
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Aarav",
    "Aditi",
    "Advik",
    "Aisha",
    "Akash",
    "Anaya",
    "Anika",
    "Arjun",
    "Aryan",
    "Avni",
    "Dev",
    "Diya",
    "Eshan",
    "Ishaan",
    "Ishita",
    "Kabir",
    "Kavya",
    "Kiara",
    "Krish",
    "Mahi",
    "Meera",
    "Myra",
    "Nakul",
    "Nandini",
    "Neel",
    "Nihar",
    "Nisha",
    "Pranav",
    "Riya",
    "Rohan",
    "Saanvi",
    "Sahil",
    "Samarth",
    "Sara",
    "Shreya",
    "Siddharth",
    "Tanvi",
    "Varun",
    "Ved",
    "Vihaan",
]

SURNAMES = [
    "Deshmukh",
    "Kulkarni",
    "Patil",
    "Nair",
    "Sharma",
    "Joshi",
    "Mehta",
    "Iyer",
    "Pawar",
    "Jadhav",
    "Reddy",
    "Menon",
    "Bhosale",
    "Chavan",
    "Naik",
    "Kadam",
    "More",
    "Shinde",
    "Shetty",
    "Verma",
]

FATHER_NAMES = [
    "Rajesh",
    "Suresh",
    "Mahesh",
    "Prakash",
    "Vijay",
    "Amit",
    "Sunil",
    "Ramesh",
    "Nitin",
    "Deepak",
    "Anil",
    "Sanjay",
    "Manoj",
    "Kiran",
]

MOTHER_NAMES = [
    "Sunita",
    "Priya",
    "Kavita",
    "Neha",
    "Pooja",
    "Anita",
    "Rekha",
    "Swati",
    "Meena",
    "Shalini",
    "Ritu",
    "Seema",
]

MIDDLE_NAMES = [
    "Raj",
    "Dev",
    "Kiran",
    "Sai",
    "Vikram",
    "Arun",
    "Mohan",
    "Ravi",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Project Vigyan demo data."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete only DEMO-origin records before exiting.",
    )
    return parser.parse_args()


def get_demo_password() -> str:
    password = os.getenv(DEMO_USER_PASSWORD_ENV)

    if not password:
        raise RuntimeError(
            f"{DEMO_USER_PASSWORD_ENV} is not set. "
            "Set a local demo password before generating users."
        )

    if len(password) < 12:
        raise RuntimeError(
            f"{DEMO_USER_PASSWORD_ENV} must contain at least 12 characters."
        )

    return password


def generate_student_name(rng: random.Random) -> str:
    """
    Generate varied but deterministic synthetic student names.

    Different patterns intentionally produce different name structures.
    """
    first = rng.choice(FIRST_NAMES)
    surname = rng.choice(SURNAMES)
    father = rng.choice(FATHER_NAMES)
    mother = rng.choice(MOTHER_NAMES)
    middle = rng.choice(MIDDLE_NAMES)

    pattern = rng.randint(1, 6)

    if pattern == 1:
        return f"{first} {surname}"

    if pattern == 2:
        return f"{first} {father}"

    if pattern == 3:
        return f"{first} {surname} {father}"

    if pattern == 4:
        return f"{first} {father} {mother}"

    if pattern == 5:
        return f"{first} {middle} {surname}"

    return f"{first} {surname} {father} {mother}"


def generate_gender(rng: random.Random) -> str:
    """
    Synthetic gender distribution.

    This vocabulary is intentionally kept simple until the project's
    final gender master-data vocabulary is formally defined.
    """
    return rng.choices(
        ["Male", "Female", "Other"],
        weights=[48, 48, 4],
        k=1,
    )[0]


def get_role(db: Session, role_code: str) -> Role:
    role = db.scalar(
        select(Role).where(Role.code == role_code)
    )

    if role is None:
        raise RuntimeError(
            f"Required role '{role_code}' was not found. "
            "Run seed_roles_permissions.py first."
        )

    return role


def get_existing_demo_count(
    db: Session,
    model,
) -> int:
    return db.scalar(
        select(func.count())
        .select_from(model)
        .where(model.data_origin == DATA_ORIGIN)
    ) or 0


def demo_data_exists(db: Session) -> bool:
    counts = {
        "schools": get_existing_demo_count(db, School),
        "class_divisions": get_existing_demo_count(db, ClassDivision),
        "students": get_existing_demo_count(db, Student),
        "users": get_existing_demo_count(db, User),
    }

    return any(count > 0 for count in counts.values())


def delete_demo_data(db: Session) -> None:
    """
    Delete only DEMO-origin data.

    Dependency order:
        students
        class divisions
        user assignments
        user roles
        users
        schools
    """

    student_count = get_existing_demo_count(db, Student)
    class_count = get_existing_demo_count(db, ClassDivision)
    assignment_count = db.scalar(
        select(func.count())
        .select_from(UserAssignment)
        .join(User, User.id == UserAssignment.user_id)
        .where(User.data_origin == DATA_ORIGIN)
    ) or 0
    user_role_count = db.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(User, User.id == UserRole.user_id)
        .where(User.data_origin == DATA_ORIGIN)
    ) or 0
    user_count = get_existing_demo_count(db, User)
    school_count = get_existing_demo_count(db, School)

    print("Existing DEMO data:")
    print(f"  Students          : {student_count}")
    print(f"  Class divisions   : {class_count}")
    print(f"  Assignments       : {assignment_count}")
    print(f"  User roles        : {user_role_count}")
    print(f"  Users             : {user_count}")
    print(f"  Schools           : {school_count}")

    db.execute(
        delete(Student).where(
            Student.data_origin == DATA_ORIGIN
        )
    )

    db.execute(
        delete(ClassDivision).where(
            ClassDivision.data_origin == DATA_ORIGIN
        )
    )

    db.execute(
        delete(UserAssignment).where(
            UserAssignment.user_id.in_(
                select(User.id).where(
                    User.data_origin == DATA_ORIGIN
                )
            )
        )
    )

    db.execute(
        delete(UserRole).where(
            UserRole.user_id.in_(
                select(User.id).where(
                    User.data_origin == DATA_ORIGIN
                )
            )
        )
    )

    db.execute(
        delete(User).where(
            User.data_origin == DATA_ORIGIN
        )
    )

    db.execute(
        delete(School).where(
            School.data_origin == DATA_ORIGIN
        )
    )

    print("DEMO data deleted successfully.")


def validate_configuration() -> None:
    if len(SCHOOLS) != EXPECTED_SCHOOL_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_SCHOOL_COUNT} schools, "
            f"configured {len(SCHOOLS)}."
        )

    if len(CLASS_DISTRIBUTION) != EXPECTED_CLASS_DIVISION_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_CLASS_DIVISION_COUNT} class divisions, "
            f"configured {len(CLASS_DISTRIBUTION)}."
        )

    if len(PARA_TEACHERS) != EXPECTED_PARA_TEACHER_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_PARA_TEACHER_COUNT} Para-Teachers, "
            f"configured {len(PARA_TEACHERS)}."
        )

    school_codes = {school["code"] for school in SCHOOLS}

    distribution_codes = {
        item[0] for item in CLASS_DISTRIBUTION
    }

    if school_codes != distribution_codes:
        raise RuntimeError(
            "School codes in SCHOOLS and CLASS_DISTRIBUTION do not match."
        )

    teacher_codes = {
        teacher["school_code"] for teacher in PARA_TEACHERS
    }

    if teacher_codes != school_codes:
        raise RuntimeError(
            "Every demo school must have exactly one Para-Teacher."
        )

    total_students = sum(
        item[3] for item in CLASS_DISTRIBUTION
    )

    if total_students != EXPECTED_STUDENT_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_STUDENT_COUNT} students, "
            f"configured {total_students}."
        )

    for school in SCHOOLS:
        school_total = sum(
            count
            for code, _, _, count in CLASS_DISTRIBUTION
            if code == school["code"]
        )

        if school_total != school["total_students"]:
            raise RuntimeError(
                f"Student total mismatch for {school['code']}: "
                f"expected {school['total_students']}, "
                f"configured {school_total}."
            )


def create_schools(db: Session) -> dict[str, School]:
    schools: dict[str, School] = {}

    for item in SCHOOLS:
        school = School(
            school_code=item["code"],
            school_name=item["name"],
            status="ACTIVE",
            data_origin=DATA_ORIGIN,
        )

        db.add(school)
        schools[item["code"]] = school

    db.flush()

    return schools


def create_class_divisions(
    db: Session,
    schools: dict[str, School],
) -> dict[tuple[str, int, str], ClassDivision]:
    divisions: dict[tuple[str, int, str], ClassDivision] = {}

    for school_code, class_level, division, _ in CLASS_DISTRIBUTION:
        class_division = ClassDivision(
            school_id=schools[school_code].id,
            class_level=class_level,
            division=division,
            status="ACTIVE",
            data_origin=DATA_ORIGIN,
        )

        db.add(class_division)

        key = (school_code, class_level, division)
        divisions[key] = class_division

    db.flush()

    return divisions


def create_students(
    db: Session,
    divisions: dict[tuple[str, int, str], ClassDivision],
    rng: random.Random,
) -> int:
    student_count = 0

    for school_code, class_level, division, count in CLASS_DISTRIBUTION:
        class_division = divisions[
            (school_code, class_level, division)
        ]

        for roll_no in range(1, count + 1):
            student_code = (
                f"{school_code}"
                f"{class_level}"
                f"{division}"
                f"{roll_no:03d}"
            )

            student = Student(
                student_code=student_code,
                full_name=generate_student_name(rng),
                gender=generate_gender(rng),
                roll_no=roll_no,
                class_division_id=class_division.id,
                status="ACTIVE",
                data_origin=DATA_ORIGIN,
            )

            db.add(student)
            student_count += 1

    db.flush()

    return student_count


def create_para_teachers(
    db: Session,
    schools: dict[str, School],
    password_hash: str,
) -> tuple[int, int]:
    para_teacher_role = get_role(db, "PARA_TEACHER")

    user_count = 0
    assignment_count = 0

    for item in PARA_TEACHERS:
        school = schools[item["school_code"]]

        user = User(
            user_code=item["user_code"],
            full_name=item["full_name"],
            email=item["email"],
            password_hash=password_hash,
            status="ACTIVE",
            data_origin=DATA_ORIGIN,
        )

        db.add(user)
        db.flush()

        user_role = UserRole(
            user_id=user.id,
            role_id=para_teacher_role.id,
            is_active=True,
        )

        assignment = UserAssignment(
            user_id=user.id,
            scope_type="SCHOOL",
            school_id=school.id,
            start_date=date.today(),
            end_date=None,
            is_active=True,
        )

        db.add(user_role)
        db.add(assignment)

        user_count += 1
        assignment_count += 1

    db.flush()

    return user_count, assignment_count

def create_data_managers(
    db: Session,
    password_hash: str,
) -> int:
    data_manager_role = get_role(db, "DATA_MANAGER")

    user_count = 0

    for item in DATA_MANAGERS:
        user = User(
            user_code=item["user_code"],
            full_name=item["full_name"],
            email=item["email"],
            password_hash=password_hash,
            status="ACTIVE",
            data_origin=DATA_ORIGIN,
        )

        db.add(user)
        db.flush()

        user_role = UserRole(
            user_id=user.id,
            role_id=data_manager_role.id,
            is_active=True,
        )

        assignment = UserAssignment(
            user_id=user.id,
            scope_type="PROJECT",
            school_id=None,
            start_date=date.today(),
            end_date=None,
            is_active=True,
        )

        db.add(user_role)
        db.add(assignment)

        user_count += 1

    db.flush()

    return user_count

def validate_database(
    db: Session,
) -> None:
    school_count = get_existing_demo_count(db, School)
    class_count = get_existing_demo_count(db, ClassDivision)
    student_count = get_existing_demo_count(db, Student)

    para_teacher_count = db.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            Role.code == "PARA_TEACHER",
            UserRole.is_active.is_(True),
        )
    ) or 0

    data_manager_count = db.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            Role.code == "DATA_MANAGER",
            UserRole.is_active.is_(True),
        )
    ) or 0

    school_assignment_count = db.scalar(
        select(func.count())
        .select_from(UserAssignment)
        .join(User, User.id == UserAssignment.user_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.is_active.is_(True),
        )
    ) or 0

    project_assignment_count = db.scalar(
        select(func.count())
        .select_from(UserAssignment)
        .join(User, User.id == UserAssignment.user_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            UserAssignment.scope_type == "PROJECT",
            UserAssignment.is_active.is_(True),
        )
    ) or 0

    assignment_count = (
        school_assignment_count
        + project_assignment_count
    )

    if school_count != EXPECTED_SCHOOL_COUNT:
        raise RuntimeError(
            f"Validation failed: expected {EXPECTED_SCHOOL_COUNT} "
            f"schools, found {school_count}."
        )

    if class_count != EXPECTED_CLASS_DIVISION_COUNT:
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_CLASS_DIVISION_COUNT} class divisions, "
            f"found {class_count}."
        )

    if student_count != EXPECTED_STUDENT_COUNT:
        raise RuntimeError(
            f"Validation failed: expected {EXPECTED_STUDENT_COUNT} "
            f"students, found {student_count}."
        )

    if para_teacher_count != EXPECTED_PARA_TEACHER_COUNT:
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_PARA_TEACHER_COUNT} Para-Teachers, "
            f"found {para_teacher_count}."
        )

    if data_manager_count != EXPECTED_DATA_MANAGER_COUNT:
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_DATA_MANAGER_COUNT} Data Manager, "
            f"found {data_manager_count}."
        )

    if (
        school_assignment_count
        != EXPECTED_SCHOOL_ASSIGNMENT_COUNT
    ):
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_SCHOOL_ASSIGNMENT_COUNT} school assignments, "
            f"found {school_assignment_count}."
        )

    if (
        project_assignment_count
        != EXPECTED_PROJECT_ASSIGNMENT_COUNT
    ):
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_PROJECT_ASSIGNMENT_COUNT} project assignments, "
            f"found {project_assignment_count}."
        )

    if assignment_count != EXPECTED_ASSIGNMENT_COUNT:
        raise RuntimeError(
            f"Validation failed: expected "
            f"{EXPECTED_ASSIGNMENT_COUNT} assignments, "
            f"found {assignment_count}."
        )

def print_summary(db: Session) -> None:
    print()
    print("=" * 48)
    print("Project Vigyan Demo Data")
    print("=" * 48)

    school_count = get_existing_demo_count(db, School)
    class_count = get_existing_demo_count(db, ClassDivision)
    student_count = get_existing_demo_count(db, Student)

    para_teacher_count = db.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            Role.code == "PARA_TEACHER",
            UserRole.is_active.is_(True),
        )
    ) or 0

    data_manager_count = db.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            Role.code == "DATA_MANAGER",
            UserRole.is_active.is_(True),
        )
    ) or 0

    school_assignment_count = db.scalar(
        select(func.count())
        .select_from(UserAssignment)
        .join(User, User.id == UserAssignment.user_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.is_active.is_(True),
        )
    ) or 0

    project_assignment_count = db.scalar(
        select(func.count())
        .select_from(UserAssignment)
        .join(User, User.id == UserAssignment.user_id)
        .where(
            User.data_origin == DATA_ORIGIN,
            UserAssignment.scope_type == "PROJECT",
            UserAssignment.is_active.is_(True),
        )
    ) or 0

    assignment_count = (
        school_assignment_count
        + project_assignment_count
    )

    print(f"Schools created          : {school_count}")
    print(f"Class divisions          : {class_count}")
    print(f"Students created         : {student_count}")
    print(f"Para-teachers created    : {para_teacher_count}")
    print(f"Data Managers created    : {data_manager_count}")
    print(f"School assignments       : {school_assignment_count}")
    print(f"Project assignments      : {project_assignment_count}")
    print(f"Total assignments        : {assignment_count}")

    print()
    print("School distribution:")

    for school in SCHOOLS:
        count = db.scalar(
            select(func.count())
            .select_from(Student)
            .join(
                ClassDivision,
                Student.class_division_id == ClassDivision.id,
            )
            .join(
                School,
                ClassDivision.school_id == School.id,
            )
            .where(
                School.school_code == school["code"],
                Student.data_origin == DATA_ORIGIN,
            )
        ) or 0

        print(
            f"  {school['code']:<4} "
            f"- {school['name']:<42} "
            f"{count}"
        )

    print()
    print("Validation:")
    print(f"  ✓ School count = {school_count}")
    print(f"  ✓ Class/division count = {class_count}")
    print(f"  ✓ Student count = {student_count}")
    print(f"  ✓ Para-teacher count = {para_teacher_count}")
    print(f"  ✓ Data Manager count = {data_manager_count}")
    print(
        f"  ✓ School assignment count = "
        f"{school_assignment_count}"
    )
    print(
        f"  ✓ Project assignment count = "
        f"{project_assignment_count}"
    )
    print(f"  ✓ Total assignment count = {assignment_count}")
    print("  ✓ All generated records marked DEMO")
    print()
    print("Demo data generated successfully.")
    print("=" * 48)

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def generate_demo_data() -> None:
    validate_configuration()

    demo_password = get_demo_password()
    password_hash = hash_password(demo_password)

    rng = random.Random(RANDOM_SEED)

    db = SessionLocal()

    try:
        print("Checking for existing DEMO data...")

        if demo_data_exists(db):
            db.rollback()

            raise RuntimeError(
                "DEMO data already exists.\n\n"
                "Run:\n"
                "    python -m scripts.generate_demo_data --reset\n\n"
                "before generating again."
            )

        db.rollback()

        print("Generating Project Vigyan synthetic demo data...")
        print(f"Random seed: {RANDOM_SEED}")

        with db.begin():
            schools = create_schools(db)

            divisions = create_class_divisions(
                db,
                schools,
            )

            student_count = create_students(
                db,
                divisions,
                rng,
            )

            user_count, assignment_count = create_para_teachers(
                db,
                schools,
                password_hash,
            )

            data_manager_count = create_data_managers(
                db,
                password_hash,
            )

            if student_count != EXPECTED_STUDENT_COUNT:
                raise RuntimeError(
                    f"Expected {EXPECTED_STUDENT_COUNT} students, "
                    f"generated {student_count}."
                )

            if user_count != EXPECTED_PARA_TEACHER_COUNT:
                raise RuntimeError(
                    f"Expected {EXPECTED_PARA_TEACHER_COUNT} "
                    f"Para-Teachers, generated {user_count}."
                )

            if assignment_count != EXPECTED_SCHOOL_ASSIGNMENT_COUNT:
                raise RuntimeError(
                    f"Expected {EXPECTED_SCHOOL_ASSIGNMENT_COUNT} "
                    f"school assignments, generated {assignment_count}."
                )

            if data_manager_count != EXPECTED_DATA_MANAGER_COUNT:
                raise RuntimeError(
                    f"Expected {EXPECTED_DATA_MANAGER_COUNT} "
                    f"Data Manager, generated {data_manager_count}."
                )

            validate_database(db)

        print_summary(db)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

def reset_demo_data() -> None:
    db = SessionLocal()

    try:
        with db.begin():
            if not demo_data_exists(db):
                print("No DEMO data found. Nothing to reset.")
                return

            delete_demo_data(db)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def main() -> None:
    args = parse_args()

    try:
        if args.reset:
            reset_demo_data()
        else:
            generate_demo_data()

    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(130)

    except Exception as exc:
        print()
        print("ERROR:")
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
