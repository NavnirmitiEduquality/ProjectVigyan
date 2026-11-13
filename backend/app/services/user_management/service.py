import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import joinedload
from pydantic import (
    EmailStr,
    TypeAdapter,
    ValidationError as PydanticValidationError,
)
from app.models import AuthSession, Role, User, UserRole
from app.services.audit import AuditService
from app.services.auth_service import hash_password


ACCOUNT_PREFIXES = {
    "PLATFORM_OWNER": "PO",
    "SYSTEM_ADMIN": "SA",
    "DATA_MANAGER": "DM",
    "MANAGEMENT": "MG",
    "STEM_COORDINATOR": "SC",
    "PARA_TEACHER": "PT",
}

EMAIL_ADAPTER = TypeAdapter(EmailStr)

class UserManagementError(Exception):
    pass


class NotFoundError(UserManagementError):
    pass


class ConflictError(UserManagementError):
    pass


class ForbiddenError(UserManagementError):
    pass


class ValidationError(UserManagementError):
    pass


class UserManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def _normalize_full_name(full_name: str) -> str:
        normalized = full_name.strip()

        if not normalized:
            raise ValidationError("Full name cannot be blank.")

        if len(normalized) > 150:
            raise ValidationError(
                "Full name cannot exceed 150 characters."
            )

        return normalized

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()

        if not normalized:
            raise ValidationError("Email address cannot be blank.")

        if len(normalized) > 255:
            raise ValidationError(
                "Email address cannot exceed 255 characters."
            )

        try:
            normalized = str(EMAIL_ADAPTER.validate_python(normalized))
        except PydanticValidationError as error:
            raise ValidationError("Invalid email address.") from error

        return normalized.lower()

    def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: str | None = None,
        role_code: str | None = None,
        data_origin: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        if page < 1:
            raise ValidationError("Page must be at least 1.")

        if not 1 <= page_size <= 100:
            raise ValidationError("Page size must be between 1 and 100.")

        if status is not None and status not in {"ACTIVE", "DISABLED"}:
            raise ValidationError("Invalid account status filter.")

        if data_origin is not None and data_origin not in {
            "PRODUCTION", "DEMO", "TEST"
        }:
            raise ValidationError("Invalid data origin filter.")

        if sort_order not in {"asc", "desc"}:
            raise ValidationError("Sort order must be asc or desc.")

        sort_columns = {
            "created_at": User.created_at,
            "full_name": User.full_name,
            "user_code": User.user_code,
            "email": User.email,
            "status": User.status,
            "account_category": User.account_category,
        }

        if sort_by not in sort_columns:
            raise ValidationError("Unsupported user sort field.")

        query = self.db.query(User)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                User.user_code.ilike(term)
                | User.full_name.ilike(term)
                | User.email.ilike(term)
            )

        if status:
            query = query.filter(User.status == status)

        if data_origin:
            query = query.filter(User.data_origin == data_origin)

        if role_code:
            query = (
                query.join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(
                    UserRole.is_active.is_(True),
                    Role.code == role_code,
                )
            )

        total = query.with_entities(
            func.count(func.distinct(User.id))
        ).scalar() or 0

        sort_column = sort_columns[sort_by]
        ordering = asc(sort_column) if sort_order == "asc" else desc(sort_column)

        users = (
            query
            .options(
                joinedload(User.user_roles).joinedload(UserRole.role)
            )
            .distinct()
            .order_by(ordering, User.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "data": users,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (
                    (total + page_size - 1) // page_size
                ),
            },
        }

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundError("User not found.")
        return user

    def _get_user_for_update(self, user_id: uuid.UUID) -> User:
        user = (
            self.db.query(User)
            .filter(User.id == user_id)
            .with_for_update()
            .first()
        )
        if not user:
            raise NotFoundError("User not found.")
        return user

    def list_roles(self) -> list[Role]:
        return self.db.query(Role).order_by(Role.name).all()

    def create_user(
        self,
        *,
        actor: User,
        full_name: str,
        email: str,
        initial_password: str,
        account_category: str,
    ) -> User:
        if account_category not in ACCOUNT_PREFIXES:
            raise ValidationError("Invalid account category.")

        full_name = self._normalize_full_name(full_name)
        normalized_email = self._normalize_email(email)
        if not initial_password.strip():
            raise ValidationError("Initial password cannot be blank.")
        if len(initial_password) < 12 or len(initial_password) > 128:
            raise ValidationError(
                "Initial password must be between 12 and 128 characters."
            )
        if self.db.query(User).filter(User.email == normalized_email).first():
            raise ConflictError("A user with this email already exists.")

        user = User(
            user_code=self._allocate_user_code(ACCOUNT_PREFIXES[account_category]),
            account_category=account_category,
            full_name=full_name,
            email=normalized_email,
            password_hash=hash_password(initial_password),
            status="ACTIVE",
            data_origin="PRODUCTION",
        )
        self.db.add(user)
        self.db.flush()
        self.audit.record(
            actor_id=actor.id,
            action="USER_CREATED",
            target_type="USER",
            target_id=user.id,
            metadata={"user_code": user.user_code, "account_category": account_category},
        )
        return user

    def update_profile(
        self,
        *,
        actor: User,
        user_id: uuid.UUID,
        full_name: str | None,
        email: str | None,
    ) -> User:
        user = self.get_user(user_id)
        changes = {}

        if full_name is not None:
            full_name = self._normalize_full_name(full_name)

        if email is not None:
            email = self._normalize_email(email)
        if full_name is not None:
            user.full_name = full_name
            changes["full_name"] = full_name
        if email is not None:
            existing = (
                self.db.query(User)
                .filter(User.email == email, User.id != user.id)
                .first()
            )
            if existing:
                raise ConflictError("A user with this email already exists.")

            if user.email != email:
                user.email = email
                user.email_verified_at = None
                changes["email"] = email
        if not changes:
            raise ValidationError("No fields provided for update.")
        self.db.flush()
        self.audit.record(
            actor_id=actor.id,
            action="USER_PROFILE_UPDATED",
            target_type="USER",
            target_id=user.id,
            metadata={"fields": sorted(changes)},
        )
        return user

    def change_status(
        self,
        *,
        actor: User,
        user_id: uuid.UUID,
        new_status: str,
    ) -> User:
        if new_status not in {"ACTIVE", "DISABLED"}:
            raise ValidationError("Invalid account status.")

        # Lock order: Platform Owner Role -> User.
        self._lock_platform_owner_role()
        user = self._get_user_for_update(user_id)

        if user.status == new_status:
            return user

        if new_status == "DISABLED":
            self._protect_last_platform_owner(user.id)

        user.status = new_status
        self.db.flush()

        action = (
            "USER_DISABLED"
            if new_status == "DISABLED"
            else "USER_REACTIVATED"
        )

        self.audit.record(
            actor_id=actor.id,
            action=action,
            target_type="USER",
            target_id=user.id,
            metadata={"status": new_status},
        )

        if new_status == "DISABLED":
            now = datetime.now(timezone.utc)
            revoked = (
                self.db.query(AuthSession)
                .filter(
                    AuthSession.user_id == user.id,
                    AuthSession.revoked_at.is_(None),
                )
                .update(
                    {"revoked_at": now},
                    synchronize_session=False,
                )
            )

            if revoked:
                self.db.flush()
                self.audit.record(
                    actor_id=actor.id,
                    action="USER_SESSIONS_REVOKED",
                    target_type="USER",
                    target_id=user.id,
                    metadata={"session_count": revoked},
                )

        return user

    def assign_role(
        self,
        *,
        actor: User,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> UserRole:
        role = self.db.get(Role, role_id)
        if not role:
            raise NotFoundError("Role not found.")
        self._check_role_grant(actor, role.code)
        if role.code == "PLATFORM_OWNER":
            self._lock_platform_owner_role()

        user = self._get_user_for_update(user_id)
        user_role = (
            self.db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
            .first()
        )
        if user_role:
            if user_role.is_active:
                raise ConflictError("The user already has this role.")
            user_role.is_active = True
        else:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            self.db.add(user_role)
        self.db.flush()
        self.audit.record(
            actor_id=actor.id,
            action="USER_ROLE_ASSIGNED",
            target_type="USER_ROLE",
            target_id=user_role.id,
            metadata={"user_id": str(user.id), "role_code": role.code},
        )
        return user_role

    def deactivate_role(
        self,
        *,
        actor: User,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> UserRole:
        self._check_platform_owner(actor)

        role = self.db.get(Role, role_id)
        if not role:
            raise NotFoundError("Role not found.")

        # Lock order: Platform Owner Role -> User -> UserRole.
        if role.code == "PLATFORM_OWNER":
            self._lock_platform_owner_role()

        self._get_user_for_update(user_id)

        user_role = (
            self.db.query(UserRole)
            .filter(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
            .with_for_update()
            .first()
        )

        if not user_role:
            raise NotFoundError("Role association not found.")

        if not user_role.is_active:
            return user_role

        if role.code == "PLATFORM_OWNER":
            self._protect_last_platform_owner(user_id)

        user_role.is_active = False
        self.db.flush()

        self.audit.record(
            actor_id=actor.id,
            action="USER_ROLE_DEACTIVATED",
            target_type="USER_ROLE",
            target_id=user_role.id,
            metadata={
                "user_id": str(user_id),
                "role_code": role.code,
            },
        )

        return user_role

    def _allocate_user_code(self, prefix: str) -> str:
        row = self.db.execute(
            text(
                """
                INSERT INTO user_code_counters (prefix, next_number)
                VALUES (:prefix, 2)
                ON CONFLICT (prefix)
                DO UPDATE SET next_number = user_code_counters.next_number + 1
                RETURNING next_number - 1 AS allocated_number
                """
            ),
            {"prefix": prefix},
        ).one()
        allocated_number = row.allocated_number
        user_code = f"{prefix}{allocated_number:04d}"

        if len(user_code) > 30:
            raise ValidationError(
                "User-code sequence has reached its maximum length."
            )

        return user_code

    def allocate_user_code(self, prefix: str) -> str:
        if prefix not in ACCOUNT_PREFIXES.values():
            raise ValidationError("Invalid user-code prefix.")
        return self._allocate_user_code(prefix)

    def _lock_platform_owner_role(self) -> Role:
        role = (
            self.db.query(Role)
            .filter(Role.code == "PLATFORM_OWNER")
            .with_for_update()
            .first()
        )
        if not role:
            raise ValidationError("Platform Owner role is not configured.")
        return role

    def _protect_last_platform_owner(
        self,
        target_user_id: uuid.UUID,
    ) -> None:
        target_is_owner = (
            self.db.query(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                UserRole.user_id == target_user_id,
                UserRole.is_active.is_(True),
                Role.code == "PLATFORM_OWNER",
            )
            .first()
            is not None
        )

        if not target_is_owner:
            return

        effective = (
            self.db.query(UserRole.id)
            .join(User, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                Role.code == "PLATFORM_OWNER",
                UserRole.is_active.is_(True),
                User.status == "ACTIVE",
            )
            .count()
        )

        if effective <= 1:
            raise ConflictError(
                "The last effective Platform Owner cannot be removed."
            )

    def _check_platform_owner(self, actor: User) -> None:
        if "PLATFORM_OWNER" not in self._active_role_codes(actor):
            raise ForbiddenError("Only a Platform Owner may remove roles.")

    def _has_active_platform_owner_role(
        self,
        user_id: uuid.UUID,
    ) -> bool:
        return (
            self.db.query(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                UserRole.user_id == user_id,
                UserRole.is_active.is_(True),
                Role.code == "PLATFORM_OWNER",
            )
            .first()
            is not None
        )

    def _check_role_grant(self, actor: User, role_code: str) -> None:
        roles = self._active_role_codes(actor)
        if "PLATFORM_OWNER" in roles:
            return
        if "SYSTEM_ADMIN" in roles and role_code != "PLATFORM_OWNER":
            return
        raise ForbiddenError("You cannot grant this role.")

    def _active_role_codes(self, user: User) -> set[str]:
        return {
            association.role.code
            for association in user.user_roles
            if association.is_active and association.role is not None
        }
