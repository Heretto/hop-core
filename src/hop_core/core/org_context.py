"""Which organization a user's access token is for.

Every org-scoped request is answered for the organization in the token's
``org_id`` claim (see ``hop_core.api.dependencies``), so every place that
issues a token must choose it the same way: the user's current organization
(``User.current_organization_id``, set by switching organization or accepting
an invitation) while they are still a member of it, otherwise their first
membership.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hop_core.models.enums import OrganizationRole
from hop_core.models.organization import OrganizationInvitation, OrganizationMember, user_organizations
from hop_core.models.user import User


def token_org_claims(db: Session, user: User) -> Dict[str, Any]:
    """``{"org_id": ..., "org_role": ...}`` for the user's token, or ``{}``
    when they belong to no organization."""
    memberships = db.execute(
        select(user_organizations).where(user_organizations.c.user_id == user.id)
    ).fetchall()
    if not memberships:
        return {}
    chosen = next(
        (m for m in memberships if user.current_organization_id and m.organization_id == user.current_organization_id),
        memberships[0],
    )
    role = chosen.role.value if hasattr(chosen.role, "value") else chosen.role
    return {
        "org_id": str(chosen.organization_id),
        "org_role": role.lower() if isinstance(role, str) else role,
    }


def pending_invitations(db: Session, email: str) -> List[OrganizationInvitation]:
    """Unaccepted, unexpired invitations for this email address, newest first."""
    now = datetime.now(timezone.utc)
    invitations = (
        db.query(OrganizationInvitation)
        .filter(
            func.lower(OrganizationInvitation.email) == email.strip().lower(),
            OrganizationInvitation.accepted_at.is_(None),
        )
        .order_by(OrganizationInvitation.created_at.desc())
        .all()
    )

    def live(invitation: OrganizationInvitation) -> bool:
        expires = invitation.expires_at
        # SQLite hands back naive datetimes.
        return expires > (now.replace(tzinfo=None) if expires.tzinfo is None else now)

    return [i for i in invitations if live(i)]


def join_invited_organizations(db: Session, user: User, invitations: List[OrganizationInvitation]) -> None:
    """Add a new user to the organizations that invited them, instead of
    creating one of their own, and make the newest invitation's organization
    their current one. Only for an email address someone has verified (single
    sign-on): an invitation token is otherwise the proof of the address."""
    accepted_at = datetime.now(timezone.utc)
    for invitation in invitations:
        role = str(invitation.role or "member").upper()
        db.add(OrganizationMember(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role=OrganizationRole(role) if role in OrganizationRole.__members__ else OrganizationRole.MEMBER,
            invited_by=invitation.invited_by,
            joined_at=accepted_at,
        ))
        invitation.accepted_at = accepted_at
    if invitations:
        user.current_organization_id = invitations[0].organization_id
