"""Organization, membership, and invitation models."""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLEnum
import uuid

from hop_core.db import Base
from hop_core.models.enums import OrganizationRole


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(
        SQLEnum(OrganizationRole, name="organizationrole", create_type=False),
        nullable=False,
        default=OrganizationRole.MEMBER,
    )
    invited_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], back_populates="memberships")
    organization = relationship(
        "Organization", foreign_keys=[organization_id], back_populates="members"
    )
    inviter = relationship("User", foreign_keys=[invited_by])


# Backward-compatible alias
user_organizations = OrganizationMember.__table__


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    settings = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Core relationships only; domain relationships are added by the host app.
    members = relationship(
        "OrganizationMember",
        foreign_keys="OrganizationMember.organization_id",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    credentials = relationship(
        "Credential", back_populates="organization", cascade="all, delete-orphan"
    )
    invitations = relationship(
        "OrganizationInvitation", back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email = Column(String(255), nullable=False)
    role = Column(String(50), default="member")
    token = Column(String(255), unique=True, nullable=False)
    invited_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="invitations")
    inviter = relationship("User", foreign_keys=[invited_by])
