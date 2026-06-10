"""Organization management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func as sa_func
from typing import List
from uuid import UUID
from datetime import datetime, timedelta, timezone
import secrets
import re

from hop_core.db import get_db
from hop_core.config import get_settings
from hop_core.models.user import User
from hop_core.models.organization import Organization, OrganizationMember, OrganizationInvitation, user_organizations
from hop_core.models.enums import OrganizationRole
from hop_core.schemas.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    OrganizationMemberUpdate, OrganizationMemberResponse,
    OrganizationInvitationCreate, OrganizationInvitationResponse,
)
from hop_core.api.dependencies import (
    get_current_active_user,
    get_current_active_user_with_org,
    require_org_admin,
    CurrentUserContext,
)
from hop_core.core.security import create_access_token, create_refresh_token, set_auth_cookies

router = APIRouter(prefix="/organizations")


def create_slug(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
    return slug.strip('-')


def _normalize_role(role) -> str:
    val = role.value if hasattr(role, 'value') else role
    return val.lower() if isinstance(val, str) else val


def _count_members(db: Session, org_id) -> int:
    return db.execute(
        select(sa_func.count()).select_from(user_organizations).where(
            user_organizations.c.organization_id == org_id
        )
    ).scalar() or 0


def _build_org_response(org, member_count: int) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        settings=getattr(org, 'settings', None) or {},
        created_at=org.created_at,
        updated_at=org.updated_at,
        member_count=member_count,
    )


@router.get("", response_model=List[OrganizationResponse])
async def list_user_organizations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    memberships = db.execute(
        select(user_organizations).where(user_organizations.c.user_id == current_user.id)
    ).all()

    organizations = []
    for membership in memberships:
        org = db.query(Organization).filter(Organization.id == membership.organization_id).first()
        if org:
            member_count = _count_members(db, org.id)
            organizations.append(_build_org_response(org, member_count))

    return organizations


@router.post("/switch/{org_id}")
async def switch_organization(
    org_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    membership = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == current_user.id,
            user_organizations.c.organization_id == org_id,
        )
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    current_user.current_organization_id = org_id
    db.commit()

    role_val = _normalize_role(membership.role)
    token_data = {
        "sub": str(current_user.id),
        "email": current_user.email,
        "org_id": str(org_id),
        "org_role": role_val,
    }

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": str(current_user.id)})
    expires_at = int((datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)).timestamp())

    set_auth_cookies(response, access_token, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    org = context.organization
    member_count = _count_members(db, org.id)
    return _build_org_response(org, member_count)


@router.post("", response_model=OrganizationResponse)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    existing_org = db.query(Organization).filter(Organization.name == org_data.name).first()
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name already exists",
        )

    base_slug = create_slug(org_data.name) if not org_data.slug else org_data.slug
    slug = base_slug
    counter = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    new_org = Organization(name=org_data.name, slug=slug)
    db.add(new_org)
    db.flush()

    db.execute(
        user_organizations.insert().values(
            user_id=current_user.id,
            organization_id=new_org.id,
            role=OrganizationRole.ADMIN.value,
        )
    )

    db.commit()
    db.refresh(new_org)

    return _build_org_response(new_org, 1)


@router.patch("/current", response_model=OrganizationResponse)
async def update_organization(
    org_data: OrganizationUpdate,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    org = context.organization

    if org_data.name:
        existing_org = db.query(Organization).filter(
            Organization.name == org_data.name, Organization.id != org.id,
        ).first()
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization name already exists",
            )
        org.name = org_data.name

    if org_data.settings is not None and hasattr(org, 'settings'):
        org.settings = org_data.settings

    db.commit()
    db.refresh(org)

    member_count = _count_members(db, org.id)
    return _build_org_response(org, member_count)


@router.get("/current/members", response_model=List[OrganizationMemberResponse])
async def list_organization_members(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    memberships = db.execute(
        select(user_organizations).where(
            user_organizations.c.organization_id == context.organization_id
        )
    ).all()

    member_responses = []
    for m in memberships:
        user = db.query(User).filter(User.id == m.user_id).first()
        if user:
            role_val = _normalize_role(m.role)
            member_responses.append(OrganizationMemberResponse(
                id=m.user_id,
                user_id=m.user_id,
                user_email=user.email,
                user_name=None,
                role=role_val,
                joined_at=m.joined_at,
                invited_by=None,
            ))

    return member_responses


@router.patch("/members/{member_id}", response_model=OrganizationMemberResponse)
async def update_member_role(
    member_id: UUID,
    member_data: OrganizationMemberUpdate,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    membership = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == member_id,
            user_organizations.c.organization_id == context.organization_id,
        )
    ).first()

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    current_role = _normalize_role(membership.role)
    new_role = _normalize_role(member_data.role)

    if current_role == "admin" and new_role != "admin":
        admin_count = db.execute(
            select(sa_func.count()).select_from(user_organizations).where(
                user_organizations.c.organization_id == context.organization_id,
                user_organizations.c.role == OrganizationRole.ADMIN.value,
            )
        ).scalar() or 0

        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin",
            )

    db.execute(
        user_organizations.update().where(
            user_organizations.c.user_id == member_id,
            user_organizations.c.organization_id == context.organization_id,
        ).values(role=new_role.upper())
    )
    db.commit()

    user = db.query(User).filter(User.id == member_id).first()

    return OrganizationMemberResponse(
        id=member_id,
        user_id=member_id,
        user_email=user.email if user else "",
        user_name=None,
        role=new_role,
        joined_at=membership.joined_at,
        invited_by=None,
    )


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: UUID,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    membership = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == member_id,
            user_organizations.c.organization_id == context.organization_id,
        )
    ).first()

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    current_role = _normalize_role(membership.role)

    if current_role == "admin":
        admin_count = db.execute(
            select(sa_func.count()).select_from(user_organizations).where(
                user_organizations.c.organization_id == context.organization_id,
                user_organizations.c.role == OrganizationRole.ADMIN.value,
            )
        ).scalar() or 0

        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin",
            )

    db.execute(
        user_organizations.delete().where(
            user_organizations.c.user_id == member_id,
            user_organizations.c.organization_id == context.organization_id,
        )
    )

    user = db.query(User).filter(User.id == member_id).first()
    if user and user.current_organization_id == context.organization_id:
        user.current_organization_id = None

    db.commit()

    return {"message": "Member removed successfully"}


@router.post("/invitations", response_model=OrganizationInvitationResponse)
async def create_invitation(
    invitation_data: OrganizationInvitationCreate,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter(User.email == invitation_data.email).first()

    if existing_user:
        existing_member = db.execute(
            select(user_organizations).where(
                user_organizations.c.user_id == existing_user.id,
                user_organizations.c.organization_id == context.organization_id,
            )
        ).first()

        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this organization",
            )

    existing_invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.email == invitation_data.email,
        OrganizationInvitation.organization_id == context.organization_id,
        OrganizationInvitation.accepted_at.is_(None),
    ).first()

    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already sent to this email",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    role_val = _normalize_role(invitation_data.role).upper()
    invitation = OrganizationInvitation(
        organization_id=context.organization_id,
        email=invitation_data.email,
        role=role_val,
        token=token,
        invited_by=context.user.id,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    inv_role = _normalize_role(invitation.role)
    return OrganizationInvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        organization_name=context.organization.name,
        email=invitation.email,
        role=inv_role,
        token=invitation.token,
        invited_by_email=context.user.email,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.get("/invitations", response_model=List[OrganizationInvitationResponse])
async def list_invitations(
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    invitations = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.organization_id == context.organization_id,
        OrganizationInvitation.accepted_at.is_(None),
        OrganizationInvitation.expires_at > datetime.now(timezone.utc),
    ).all()

    invitation_responses = []
    for invitation in invitations:
        inviter = db.query(User).filter(User.id == invitation.invited_by).first()

        inv_role = _normalize_role(invitation.role)
        invitation_responses.append(OrganizationInvitationResponse(
            id=invitation.id,
            organization_id=invitation.organization_id,
            organization_name=context.organization.name,
            email=invitation.email,
            role=inv_role,
            token=invitation.token,
            invited_by_email=inviter.email if inviter else "",
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        ))

    return invitation_responses


@router.delete("/invitations/{invitation_id}")
async def cancel_invitation(
    invitation_id: UUID,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    invitation = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.id == invitation_id,
        OrganizationInvitation.organization_id == context.organization_id,
    ).first()

    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    db.delete(invitation)
    db.commit()

    return {"message": "Invitation cancelled successfully"}


@router.post("/invitations/accept/{token}")
async def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_active_user),
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

    inv_expires = invitation.expires_at
    inv_now = datetime.now(timezone.utc)
    if inv_expires.tzinfo is None:
        inv_now = inv_now.replace(tzinfo=None)
    if inv_expires < inv_now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if current_user.email != invitation.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is for a different email address",
        )

    existing_member = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == current_user.id,
            user_organizations.c.organization_id == invitation.organization_id,
        )
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this organization",
        )

    role_for_db = _normalize_role(invitation.role).upper()
    db.execute(
        user_organizations.insert().values(
            user_id=current_user.id,
            organization_id=invitation.organization_id,
            role=role_for_db,
        )
    )

    invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Successfully joined the organization"}
