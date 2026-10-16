"""DTD sets: an organization's own DITA grammar, uploaded as zips.

A set has versions; each upload is one :class:`DtdSetVersion`, processed in
the background (see :mod:`hop_core.dtd_sets`). ``current_version_id`` names
the version apps validate against, and only moves once a new version is
ready — a failed or still-processing upload never displaces a working one.

The bundled OASIS DITA 1.3 grammar is not a row: it is the built-in set every
organization has, under the ID ``oasis-dita-1.3``.

All tables here are new, so ``create_all`` adds them on startup.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import deferred, relationship
from sqlalchemy.sql import func

from hop_core.db import Base

# The bundled OASIS DITA 1.3 grammar, which every organization has.
BUILTIN_DTD_SET_ID = "oasis-dita-1.3"


class DtdSet(Base):
    __tablename__ = "dtd_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    # The version apps validate against: the most recent one that processed
    # successfully, or one an admin restored. No FK — it points into this
    # set's own versions, which cascade with the set.
    current_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions = relationship(
        "DtdSetVersion", back_populates="dtd_set", cascade="all, delete-orphan",
        order_by="DtdSetVersion.created_at.desc()",
    )


class DtdSetVersion(Base):
    __tablename__ = "dtd_set_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dtd_set_id = Column(
        UUID(as_uuid=True), ForeignKey("dtd_sets.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    label = Column(String(64), nullable=False)          # "v2.3"
    filename = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    # The uploaded zip. Deferred: lists and detail pages never need the bytes.
    archive = deferred(Column(LargeBinary, nullable=False))

    # "processing" | "ready" | "failed"
    status = Column(String(20), nullable=False, default="processing")
    step = Column(Integer, nullable=False, default=0)    # index into hop_core.dita.packages.STEPS
    step_details = Column(JSON, nullable=False, default=list)   # one detail string per step reached
    error = Column(Text, nullable=True)
    # PackageReport.to_dict(): document types, issues, catalog, counts.
    report = Column(JSON, nullable=True)

    uploaded_by = Column(String(255), nullable=True)
    # Set in Python, not by the database: versions are ordered by it, and a
    # server default's whole-second precision would tie two quick uploads.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)

    dtd_set = relationship("DtdSet", back_populates="versions")


class AgentDtdSet(Base):
    """An agent's own choice of DTD set; no row means "the organization default".

    A table of its own so the agents table needs no migration. ``dtd_set_id``
    is a string so it can also name the built-in set.
    """

    __tablename__ = "agent_dtd_sets"

    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True,
    )
    dtd_set_id = Column(String(64), nullable=False, index=True)
