from getpass import getpass

from app.database import SessionLocal
from app.models import Role, User, UserRole
from app.services.auth_service import hash_password


def create_platform_owner():
    db = SessionLocal()

    try:
        print("\n=== Project Vigyan — Create Platform Owner ===\n")

        full_name = input("Full name: ").strip()
        email = input("Email: ").strip().lower()

        if not full_name:
            raise ValueError("Full name is required.")

        if not email:
            raise ValueError("Email is required.")

        password = getpass("Password: ")
        confirm_password = getpass("Confirm password: ")

        if not password:
            raise ValueError("Password is required.")

        if password != confirm_password:
            raise ValueError("Passwords do not match.")

        # Check whether the email already exists.
        existing_user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_user:
            raise ValueError(
                f"A user with email '{email}' already exists."
            )

        # Find the seeded Platform Owner role.
        platform_owner_role = (
            db.query(Role)
            .filter(Role.code == "PLATFORM_OWNER")
            .first()
        )

        if not platform_owner_role:
            raise ValueError(
                "PLATFORM_OWNER role was not found. "
                "Run the role/permission seed first."
            )

        # Generate the human-readable user code.
        existing_codes = (
            db.query(User.user_code)
            .filter(User.user_code.like("PO%"))
            .all()
        )

        next_number = len(existing_codes) + 1
        user_code = f"PO{next_number:04d}"

        # Create the user.
        user = User(
            user_code=user_code,
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            status="ACTIVE",
        )

        db.add(user)
        db.flush()

        # Assign Platform Owner role.
        user_role = UserRole(
            user_id=user.id,
            role_id=platform_owner_role.id,
            is_active=True,
        )

        db.add(user_role)

        db.commit()

        print("\nPlatform Owner created successfully.")
        print(f"User code: {user.user_code}")
        print(f"Email: {user.email}")
        print(f"Role: {platform_owner_role.name}\n")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    create_platform_owner()
