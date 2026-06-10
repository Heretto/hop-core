"""Invitation acceptance routes for unauthenticated users."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from hop_core.db import get_db


def _is_expired(expires_at: datetime) -> bool:
    """Compare invitation expiry against now, handling naive (SQLite) datetimes."""
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now
from hop_core.models.user import User
from hop_core.models.organization import Organization, OrganizationMember, OrganizationInvitation
from hop_core.core.security import get_password_hash, verify_password
from hop_core.core.rate_limit import limiter

router = APIRouter(prefix="/invitations")


class InvitationInfoResponse(BaseModel):
    email: str
    organization_name: str
    role: str
    invited_by_email: str
    expires_at: datetime
    is_existing_user: bool


class AcceptInvitationRequest(BaseModel):
    password: str
    confirm_password: str


class AcceptInvitationResponse(BaseModel):
    message: str
    email: str
    organization_name: str


@router.get("/info/{token}", response_model=InvitationInfoResponse)
@limiter.limit("10/minute")
async def get_invitation_info(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.token == token,
        OrganizationInvitation.accepted_at.is_(None),
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation",
        )

    if _is_expired(invitation.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    organization = db.query(Organization).filter(
        Organization.id == invitation.organization_id,
    ).first()

    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    inviter = db.query(User).filter(User.id == invitation.invited_by).first()

    return InvitationInfoResponse(
        email=invitation.email,
        organization_name=organization.name,
        role=str(invitation.role.value if hasattr(invitation.role, 'value') else invitation.role).lower(),
        invited_by_email=inviter.email if inviter else "Unknown",
        expires_at=invitation.expires_at,
        is_existing_user=False,
    )


@router.post("/accept/{token}", response_model=AcceptInvitationResponse)
@limiter.limit("20/minute")
async def accept_invitation_new_user(
    request: Request,
    token: str,
    body: AcceptInvitationRequest,
    db: Session = Depends(get_db),
):
    if body.password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )

    invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.token == token,
        OrganizationInvitation.accepted_at.is_(None),
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation",
        )

    if _is_expired(invitation.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    organization = db.query(Organization).filter(
        Organization.id == invitation.organization_id,
    ).first()

    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    user = db.query(User).filter(User.email == invitation.email).first()

    if not user:
        user = User(
            email=invitation.email,
            password_hash=get_password_hash(body.password),
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please use the existing user flow to verify your identity.",
        )

    existing_member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.organization_id == invitation.organization_id,
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization",
        )

    member = OrganizationMember(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
        invited_by=invitation.invited_by,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    if not user.current_organization_id:
        user.current_organization_id = invitation.organization_id

    invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()

    return AcceptInvitationResponse(
        message="Invitation accepted successfully. You can now log in with your email and password.",
        email=user.email,
        organization_name=organization.name,
    )


class ExistingUserAcceptRequest(BaseModel):
    password: str


@router.post("/accept-existing/{token}")
@limiter.limit("20/minute")
async def accept_invitation_existing_user(
    request: Request,
    token: str,
    body: ExistingUserAcceptRequest,
    db: Session = Depends(get_db),
):
    invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.token == token,
        OrganizationInvitation.accepted_at.is_(None),
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation",
        )

    if _is_expired(invitation.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    user = db.query(User).filter(User.email == invitation.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please use the new user registration flow",
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    existing_member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.organization_id == invitation.organization_id,
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this organization",
        )

    member = OrganizationMember(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
        invited_by=invitation.invited_by,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    if not user.current_organization_id:
        user.current_organization_id = invitation.organization_id

    invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()

    organization = db.query(Organization).filter(
        Organization.id == invitation.organization_id,
    ).first()

    return AcceptInvitationResponse(
        message="Invitation accepted successfully. You have been added to the organization.",
        email=user.email,
        organization_name=organization.name if organization else "Unknown",
    )
