"""Credential model with extensible type system."""

from sqlalchemy import Column, String, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from hop_core.db import Base


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    encrypted_data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(255), nullable=True)

    user = relationship("User", back_populates="credentials")
    organization = relationship("Organization", back_populates="credentials")
