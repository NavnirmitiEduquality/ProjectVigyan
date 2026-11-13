from uuid import UUID
from pydantic import model_validator
from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import User, UserRole
from app.services.user_management.service import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UserManagementError,
    UserManagementService,
    ValidationError,
)


router = APIRouter(prefix="/api/v1/users", tags=["Users"])


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    initial_password: str = Field(min_length=12, max_length=128)
    account_category: str


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_update_fields(cls, values):
        if not isinstance(values, dict):
            return values

        if not values:
            raise ValueError("At least one profile field must be provided.")

        for field in ("full_name", "email"):
            if field in values and values[field] is None:
                raise ValueError(f"{field} cannot be null.")

        return values


class UserStatusUpdate(BaseModel):
    status: str = Field(pattern="^(ACTIVE|DISABLED)$")


class RoleAssignment(BaseModel):
    role_id: UUID


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    description: str | None


class UserRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role_id: UUID
    is_active: bool
    role: RoleResponse


class UserResponse(BaseModel):
    id: UUID
    user_code: str
    account_category: str
    full_name: str
    email: EmailStr
    status: str
    data_origin: str
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user_roles: list[UserRoleResponse]

    model_config = ConfigDict(from_attributes=True)

class PaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class UserListResponse(BaseModel):
    data: list[UserResponse]
    pagination: PaginationResponse


def _error(error: UserManagementError) -> HTTPException:
    message = str(error)


    if isinstance(error, NotFoundError):
        http_status = status.HTTP_404_NOT_FOUND
        message_lower = message.lower()

        if "association" in message_lower:
            code = "ROLE_NOT_ASSIGNED"
        elif "role" in message_lower:
            code = "ROLE_NOT_FOUND"
        else:
            code = "USER_NOT_FOUND"
    elif isinstance(error, ConflictError):
        http_status = status.HTTP_409_CONFLICT
        if "last effective Platform Owner" in message:
            code = "LAST_PLATFORM_OWNER_PROTECTED"
        elif "already has this role" in message:
            code = "ROLE_ALREADY_ASSIGNED"
        elif "email" in message.lower():
            code = "USER_EMAIL_ALREADY_EXISTS"
        else:
            code = "USER_CONFLICT"
    elif isinstance(error, ForbiddenError):
        http_status = status.HTTP_403_FORBIDDEN
        code = (
            "ROLE_REMOVAL_NOT_AUTHORIZED"
            if "remove roles" in message.lower()
            else "ROLE_ASSIGNMENT_NOT_AUTHORIZED"
        )
    else:
        http_status = status.HTTP_400_BAD_REQUEST
        code = "USER_VALIDATION_ERROR"

    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "USER_OPERATION_CONFLICT",
                "message": (
                    "The requested user operation conflicts "
                    "with existing data."
                ),
            },
        ) from error


def _user_response(user: User) -> dict:
    return {
        "id": user.id,
        "user_code": user.user_code,
        "account_category": user.account_category,
        "full_name": user.full_name,
        "email": user.email,
        "status": user.status,
        "data_origin": user.data_origin,
        "email_verified_at": user.email_verified_at,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "user_roles": [
            association
            for association in user.user_roles
            if association.is_active
        ],
    }


def _parse_path_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_UUID",
                "message": f"Invalid {field_name}.",
            },
        ) from error


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    _: User = Depends(require_permission("role.view")),
    db: Session = Depends(get_db),
):
    return UserManagementService(db).list_roles()


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status"),
    role_code: str | None = Query(default=None, max_length=50),
    data_origin: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    _: User = Depends(require_permission("user.view")),
    db: Session = Depends(get_db),
):
    try:
        result = UserManagementService(db).list_users(
            page=page,
            page_size=page_size,
            search=search,
            status=status_filter,
            role_code=role_code,
            data_origin=data_origin,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {
            "data": [
                _user_response(user)
                for user in result["data"]
            ],
            "pagination": result["pagination"],
        }
    except UserManagementError as error:
        raise _error(error)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    _: User = Depends(require_permission("user.view")),
    db: Session = Depends(get_db),
):
    user_id = _parse_path_uuid(user_id, "user ID")
    try:
        return _user_response(UserManagementService(db).get_user(user_id))
    except UserManagementError as error:
        raise _error(error)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_permission("user.create")),
    db: Session = Depends(get_db),
):
    try:
        user = UserManagementService(db).create_user(
            actor=actor,
            full_name=payload.full_name,
            email=str(payload.email),
            initial_password=payload.initial_password,
            account_category=payload.account_category,
        )
        _commit(db)
        return _user_response(user)
    except UserManagementError as error:
        db.rollback()
        raise _error(error)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserProfileUpdate,
    actor: User = Depends(require_permission("user.update")),
    db: Session = Depends(get_db),
):
    user_id = _parse_path_uuid(user_id, "user ID")
    try:
        user = UserManagementService(db).update_profile(
            actor=actor,
            user_id=user_id,
            full_name=payload.full_name,
            email=str(payload.email) if payload.email is not None else None,
        )
        _commit(db)
        return _user_response(user)
    except UserManagementError as error:
        db.rollback()
        raise _error(error)


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_status(
    user_id: str,
    payload: UserStatusUpdate,
    actor: User = Depends(require_permission("user.disable")),
    db: Session = Depends(get_db),
):
    user_id = _parse_path_uuid(user_id, "user ID")
    try:
        user = UserManagementService(db).change_status(
            actor=actor,
            user_id=user_id,
            new_status=payload.status,
        )
        _commit(db)
        return _user_response(user)
    except UserManagementError as error:
        db.rollback()
        raise _error(error)



@router.post(
    "/{user_id}/roles",
    response_model=UserRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_role(
    user_id: str,
    payload: RoleAssignment,
    response: Response,
    actor: User = Depends(require_permission("role.update")),
    db: Session = Depends(get_db),
):
    user_id = _parse_path_uuid(user_id, "user ID")

    try:
        existing = (
            db.query(UserRole)
            .filter(
                UserRole.user_id == user_id,
                UserRole.role_id == payload.role_id,
            )
            .first()
        )
        is_reactivation = existing is not None and not existing.is_active

        association = UserManagementService(db).assign_role(
            actor=actor,
            user_id=user_id,
            role_id=payload.role_id,
        )

        if is_reactivation:
            response.status_code = status.HTTP_200_OK

        _commit(db)
        return association

    except UserManagementError as error:
        db.rollback()
        raise _error(error)


@router.delete(
    "/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_role(
    user_id: str,
    role_id: str,
    actor: User = Depends(require_permission("role.update")),
    db: Session = Depends(get_db),
):
    user_id = _parse_path_uuid(user_id, "user ID")
    role_id = _parse_path_uuid(role_id, "role ID")

    try:
        UserManagementService(db).deactivate_role(
            actor=actor,
            user_id=user_id,
            role_id=role_id,
        )
        _commit(db)
    except UserManagementError as error:
        db.rollback()
        raise _error(error)
