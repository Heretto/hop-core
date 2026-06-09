"""User and authentication Pydantic schemas."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    organization_name: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserOrganizationInfo(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    organizations: Optional[List[UserOrganizationInfo]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
