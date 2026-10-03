"""Accounts still waiting for their owner to confirm the email address.

A row exists only while verification is outstanding; verifying deletes it.
Storing the pending state rather than a ``users`` column means turning
REQUIRE_EMAIL_VERIFICATION on needs no migration (``create_all`` adds the
table) and leaves every existing account verified.
"""

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from hop_core.db import Base


class PendingEmailVerification(Base):
    __tablename__ = "pending_email_verifications"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
