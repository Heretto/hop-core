"""SINGLE_ORG_MODE: every new account joins one organization, named by slug.

On a fresh database that organization does not exist yet, so it is created on
the first sign-up, and whoever joins an organization with no members becomes
its admin — otherwise nobody could ever invite or manage anyone.
"""

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hop_core.config import get_settings
from hop_core.models.enums import OrganizationRole
from hop_core.models.organization import Organization, OrganizationMember
from hop_core.models.user import User

logger = logging.getLogger(__name__)


def _default_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part) or slug


def get_or_create_single_org(db: Session) -> Organization:
    """Return the SINGLE_ORG_SLUG organization, creating it if it does not exist.

    Creation commits on its own, so call this before adding anything else to
    the session. Two first sign-ups racing each other both try to create it;
    the loser's insert hits the unique slug, rolls back, and reads the winner's.
    """
    settings = get_settings()
    slug = settings.single_org_slug
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if org:
        return org

    org = Organization(id=uuid.uuid4(), name=settings.single_org_name or _default_name(slug), slug=slug)
    db.add(org)
    try:
        db.commit()
        logger.info("SINGLE_ORG_MODE: created organization %r (%s)", org.name, slug)
    except IntegrityError:
        db.rollback()
        org = db.query(Organization).filter(Organization.slug == slug).one()
    return org


def join_single_org(db: Session, user: User, org: Organization) -> OrganizationRole:
    """Make a newly created user a member of the single organization.

    The first member becomes ADMIN; everyone after joins as MEMBER.
    """
    has_members = db.query(OrganizationMember.id).filter(
        OrganizationMember.organization_id == org.id,
    ).first() is not None
    role = OrganizationRole.MEMBER if has_members else OrganizationRole.ADMIN

    user.current_organization_id = org.id
    db.add(OrganizationMember(user_id=user.id, organization_id=org.id, role=role))
    return role
