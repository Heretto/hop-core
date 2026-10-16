"""Rules shared by every route that creates or accepts an invitation.

The organization admin's route and the superadmin's route must agree with
each other and with the pending-invitations list, which shows only unexpired,
unaccepted invitations. When they disagreed, an expired invitation vanished
from the list yet still blocked re-inviting its address, with an error that
read as though mail had been sent.

Emails are stored lowercased and compared case-insensitively: ``Ada@x.com``
and ``ada@x.com`` are one person to any mail server, so they are one person
here too. Comparisons lower both sides so rows written before normalization
still match.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from hop_core.models.organization import OrganizationInvitation
from hop_core.models.user import User

PENDING_INVITATION_DETAIL = (
    "This address already has a pending invitation. Cancel it first, "
    "or copy its link from the pending list."
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_expired(expires_at: datetime) -> bool:
    """Compare against now, handling the naive datetimes SQLite returns."""
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now


def find_user_by_email(db: Session, email: str):
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


def clear_way_for_invitation(db: Session, organization_id, email: str) -> None:
    """Make room for a new invitation to ``email``, or refuse.

    A live invitation is refused — the admin can cancel it or reuse its link.
    Expired ones are deleted rather than ignored: leaving them would only set
    the same trap again the next time an invitation expires.
    """
    unaccepted = db.query(OrganizationInvitation).filter(
        func.lower(OrganizationInvitation.email) == normalize_email(email),
        OrganizationInvitation.organization_id == organization_id,
        OrganizationInvitation.accepted_at.is_(None),
    ).all()

    if any(not is_expired(invitation.expires_at) for invitation in unaccepted):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PENDING_INVITATION_DETAIL)

    for invitation in unaccepted:
        db.delete(invitation)
