"""Superuser administration endpoints for managing all organizations.

Domain-specific stats (e.g. job counts) can be injected via
register_org_stats_hook().
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, select
from typing import Callable, Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import secrets

from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.models.organization import Organization, OrganizationInvitation, user_organizations
from hop_core.core.security import get_password_hash
from hop_core.api.dependencies import get_current_superuser

router = APIRouter(prefix="/superadmin")

# Hook for domain-specific stats (e.g. job counts, last activity)
_org_stats_hook: Optional[Callable] = None


def register_org_stats_hook(fn: Callable[[Session, UUID], Dict[str, Any]]) -> None:
    """Register a function that returns domain-specific stats for an org.

    The function receives (db_session, org_id) and should return a dict
    with keys like 'job_count', 'last_activity', etc.
    """
    global _org_stats_hook
    _org_stats_hook = fn


def _get_org_stats(db: Session, org_id: UUID) -> Dict[str, Any]:
    if _org_stats_hook:
        return _org_stats_hook(db, org_id)
    return {}


class SuperadminOrgListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    member_count: int
    created_by_email: Optional[str] = None
    last_activity: Optional[datetime] = None
    job_count: Optional[int] = None

    class Config:
        from_attributes = True


class SuperadminOrgMember(BaseModel):
    user_id: UUID
    email: str
    role: str
    is_active: bool
    joined_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SuperadminOrgDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    member_count: int
    job_count: int = 0
    created_by_email: Optional[str] = None
    last_activity: Optional[datetime] = None
    members: List[SuperadminOrgMember] = []

    class Config:
        from_attributes = True


@router.get("/organizations", response_model=List[SuperadminOrgListItem])
async def list_all_organizations(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    orgs = db.query(Organization).order_by(desc(Organization.created_at)).all()

    results = []
    for org in orgs:
        member_count = db.execute(
            select(func.count()).select_from(user_organizations).where(
                user_organizations.c.organization_id == org.id
            )
        ).scalar() or 0

        first_member = db.execute(
            select(user_organizations).where(
                user_organizations.c.organization_id == org.id
            ).order_by(user_organizations.c.joined_at.asc())
        ).first()

        created_by_email = None
        if first_member:
            creator = db.query(User).filter(User.id == first_member.user_id).first()
            if creator:
                created_by_email = creator.email

        stats = _get_org_stats(db, org.id)

        results.append(SuperadminOrgListItem(
            id=org.id,
            name=org.name,
            slug=org.slug,
            is_active=org.is_active,
            created_at=org.created_at,
            member_count=member_count,
            created_by_email=created_by_email,
            last_activity=stats.get("last_activity"),
            job_count=stats.get("job_count"),
        ))

    return results


@router.get("/organizations/{org_id}", response_model=SuperadminOrgDetail)
async def get_organization_detail(
    org_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    memberships = db.execute(
        select(user_organizations).where(
            user_organizations.c.organization_id == org.id
        )
    ).all()

    members = []
    for m in memberships:
        user = db.query(User).filter(User.id == m.user_id).first()
        if user:
            members.append(SuperadminOrgMember(
                user_id=user.id,
                email=user.email,
                role=m.role or 'member',
                is_active=user.is_active,
                joined_at=m.joined_at,
            ))

    first_member = db.execute(
        select(user_organizations).where(
            user_organizations.c.organization_id == org.id
        ).order_by(user_organizations.c.joined_at.asc())
    ).first()

    created_by_email = None
    if first_member:
        creator = db.query(User).filter(User.id == first_member.user_id).first()
        if creator:
            created_by_email = creator.email

    stats = _get_org_stats(db, org.id)

    return SuperadminOrgDetail(
        id=org.id,
        name=org.name,
        slug=org.slug,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
        member_count=len(members),
        job_count=stats.get("job_count", 0),
        created_by_email=created_by_email,
        last_activity=stats.get("last_activity"),
        members=members,
    )


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    db.query(User).filter(
        User.current_organization_id == org.id,
    ).update({User.current_organization_id: None})

    db.delete(org)
    db.commit()

    return {"message": f"Organization '{org.name}' deleted successfully"}


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: str = "member"


@router.post("/organizations/{org_id}/members")
async def add_existing_user_to_org(
    org_id: UUID,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"No user found with email '{request.email}'")

    existing = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user.id,
            user_organizations.c.organization_id == org.id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this organization")

    db.execute(
        user_organizations.insert().values(
            user_id=user.id,
            organization_id=org.id,
            role=request.role.upper() if isinstance(request.role, str) else request.role,
        )
    )

    if not user.current_organization_id:
        user.current_organization_id = org.id

    db.commit()
    return {"message": f"User '{request.email}' added to '{org.name}' as {request.role}"}


@router.delete("/organizations/{org_id}/members/{user_id}")
async def remove_member_from_org(
    org_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.organization_id == org_id,
        )
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="User is not a member of this organization")

    db.execute(
        user_organizations.delete().where(
            user_organizations.c.user_id == user_id,
            user_organizations.c.organization_id == org_id,
        )
    )

    user = db.query(User).filter(User.id == user_id).first()
    if user and user.current_organization_id == org_id:
        user.current_organization_id = None

    db.commit()
    return {"message": "User removed from organization"}


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str = "member"


class SuperadminInvitationResponse(BaseModel):
    id: UUID
    email: str
    role: str
    token: str
    expires_at: datetime

    class Config:
        from_attributes = True


@router.post("/organizations/{org_id}/invitations", response_model=SuperadminInvitationResponse)
async def invite_user_to_org(
    org_id: UUID,
    request: InviteUserRequest,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        existing_member = db.execute(
            select(user_organizations).where(
                user_organizations.c.user_id == existing_user.id,
                user_organizations.c.organization_id == org_id,
            )
        ).first()
        if existing_member:
            raise HTTPException(status_code=400, detail="User is already a member of this organization")

    existing_invite = db.query(OrganizationInvitation).filter(
        OrganizationInvitation.email == request.email,
        OrganizationInvitation.organization_id == org_id,
        OrganizationInvitation.accepted_at.is_(None),
    ).first()
    if existing_invite:
        raise HTTPException(status_code=400, detail="An invitation has already been sent to this email")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invitation = OrganizationInvitation(
        organization_id=org_id,
        email=request.email,
        role=request.role,
        token=token,
        invited_by=current_user.id,
        expires_at=expires_at,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return SuperadminInvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        token=invitation.token,
        expires_at=invitation.expires_at,
    )
