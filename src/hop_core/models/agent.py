"""Agent configuration models.

An agent is a reusable, organization-scoped configuration: a name, the AI
configuration it runs on, markdown context files, the URLs it is allowed to
read, and a separate body of feedback it has accumulated. Agents do nothing on
their own — a job or workflow supplies input and instructions and receives
output back.

The model configuration is established separately, as a credential of a type
registered with ``is_ai_configuration=True``, and the agent points at one. That
keeps API keys and model choice in a single place that several agents share.
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from hop_core.db import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # The AI configuration this agent runs on — a credential row carrying the
    # provider (its type), the model, and the API key. SET NULL rather than
    # CASCADE: deleting a credential must not delete the agents using it, it
    # must leave them visibly unconfigured.
    ai_configuration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="SET NULL"),
        nullable=True,
    )

    # List of URL prefixes the agent may read for reference material.
    permitted_urls = Column(JSON, nullable=False, default=list)

    # Accumulated feedback, kept deliberately separate from context files:
    # context is what the agent was given, memory is what it has learned.
    feedback_memory = Column(Text, nullable=False, default="")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(255), nullable=True)

    organization = relationship("Organization", back_populates="agents")
    creator = relationship("User", foreign_keys=[user_id])
    ai_configuration = relationship("Credential", foreign_keys=[ai_configuration_id])
    context_files = relationship(
        "AgentContextFile",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentContextFile.position",
    )


class AgentContextFile(Base):
    __tablename__ = "agent_context_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False, default="")
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    agent = relationship("Agent", back_populates="context_files")
