"""User model."""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from hop_core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    oauth_provider = Column(String(50), nullable=True)
    oauth_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    current_organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )

    # Core relationships only; domain relationships are added by the host app.
    memberships = relationship(
        "OrganizationMember",
        foreign_keys="OrganizationMember.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    current_organization = relationship("Organization", foreign_keys=[current_organization_id])
    credentials = relationship("Credential", back_populates="user", cascade="all, delete-orphan")
