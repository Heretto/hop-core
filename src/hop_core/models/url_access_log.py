"""Per-call log of every URL an agent tool reads.

Rows are hard-deleted when ``expires_at`` passes; the writer sets that
column and prunes stale rows in the same transaction so no background
job is required.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from hop_core.db import Base


class UrlAccessLog(Base):
    __tablename__ = "url_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized so logs survive agent deletion.
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_name = Column(String(255), nullable=False)

    url = Column(Text, nullable=False)
    # "success" | "blocked" | "error"
    status = Column(String(50), nullable=False)
    blocked_reason = Column(Text, nullable=True)

    http_status = Column(Integer, nullable=True)
    content_type = Column(String(255), nullable=True)
    response_bytes = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    accessed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Rows are deleted when expires_at < now().
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
