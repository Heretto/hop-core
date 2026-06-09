"""User account management routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.api.dependencies import (
    get_current_active_user,
    get_current_user_context,
    CurrentUserContext,
)
from hop_core.core.security import get_password_hash, verify_password

router = APIRouter(prefix="/account")


class AccountUpdate(BaseModel):
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class AccountResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: str
    organization_role: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    oauth_provider: Optional[str] = None
    has_password: bool = True


@router.get("/me", response_model=AccountResponse)
async def get_account_info(
    context: CurrentUserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    current_user = context.user
    response = AccountResponse(
        id=str(current_user.id),
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at.isoformat(),
        oauth_provider=current_user.oauth_provider,
        has_password=current_user.password_hash is not None,
    )

    if context.organization_id and context.organization:
        role_val = context.organization_role.value if hasattr(context.organization_role, 'value') else context.organization_role
        response.organization_role = role_val.lower() if isinstance(role_val, str) else role_val
        response.organization_id = str(context.organization_id)
        response.organization_name = context.organization.name

    return response


@router.put("/me")
async def update_account(
    account_data: AccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if account_data.new_password:
        if current_user.password_hash:
            if not account_data.current_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is required to set a new password",
                )

            if not verify_password(account_data.current_password, current_user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect",
                )

        if len(account_data.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long",
            )

        current_user.password_hash = get_password_hash(account_data.new_password)

    if account_data.email and account_data.email != current_user.email:
        existing_user = db.query(User).filter(
            User.email == account_data.email,
            User.id != current_user.id,
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        current_user.email = account_data.email

    db.commit()
    db.refresh(current_user)

    return {"message": "Account updated successfully", "email": current_user.email}


class DeleteAccountRequest(BaseModel):
    confirm: bool = False


@router.delete("/me")
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please confirm account deletion by setting confirm=true",
        )

    db.delete(current_user)
    db.commit()

    return {"message": "Account deleted successfully"}
