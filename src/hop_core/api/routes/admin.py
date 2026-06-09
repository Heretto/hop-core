"""Development-only admin routes."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from hop_core.config import get_settings
from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.core.security import get_password_hash
from hop_core.api.dependencies import get_current_superuser

router = APIRouter(prefix="/admin")


@router.get("/users", response_model=List[dict])
async def list_users(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode",
        )

    users = db.query(User).all()
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "note": "Use /admin/reset-password endpoint to reset password",
        }
        for user in users
    ]


@router.post("/reset-password")
async def reset_user_password(
    email: str,
    new_password: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = get_password_hash(new_password)
    db.commit()

    return {"message": f"Password reset successful for {email}", "email": email}


@router.delete("/users/{email}")
async def delete_user(
    email: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()

    return {"message": f"User {email} deleted successfully"}


@router.post("/create-test-user")
async def create_test_user(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode",
        )

    test_email = "admin@example.com"
    test_password = secrets.token_urlsafe(16)

    existing_user = db.query(User).filter(User.email == test_email).first()
    if existing_user:
        existing_user.password_hash = get_password_hash(test_password)
        db.commit()
        return {
            "message": "Test user already exists, password reset",
            "email": test_email,
            "password": test_password,
        }

    new_user = User(
        email=test_email,
        password_hash=get_password_hash(test_password),
        is_active=True,
        is_superuser=True,
    )

    db.add(new_user)
    db.commit()

    return {
        "message": "Test user created successfully",
        "email": test_email,
        "password": test_password,
    }
