"""Organization, member, and invitation Pydantic schemas."""

from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class OrganizationRoleEnum(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class OrganizationBase(BaseModel):
    name: str
    slug: Optional[str] = None
    settings: Optional[Dict[str, Any]] = {}


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class OrganizationResponse(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    member_count: Optional[int] = None

    class Config:
        from_attributes = True


class OrganizationMemberBase(BaseModel):
    role: OrganizationRoleEnum


class OrganizationMemberCreate(OrganizationMemberBase):
    user_email: EmailStr


class OrganizationMemberUpdate(BaseModel):
    role: OrganizationRoleEnum


class OrganizationMemberResponse(OrganizationMemberBase):
    id: UUID
    user_id: UUID
    user_email: str
    user_name: Optional[str] = None
    joined_at: datetime
    invited_by: Optional[UUID] = None

    class Config:
        from_attributes = True


class OrganizationInvitationCreate(BaseModel):
    email: EmailStr
    role: OrganizationRoleEnum = OrganizationRoleEnum.MEMBER


class OrganizationInvitationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    email: str
    role: OrganizationRoleEnum
    token: str
    invited_by_email: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
