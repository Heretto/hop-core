"""Agent configuration Pydantic schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from hop_core.agents.urls import InvalidPermittedUrl, normalize_urls
from hop_core.ai import ChatMessage


class AiConfigurationSummary(BaseModel):
    """An AI configuration as the agent UI shows it — never the API key."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    # The credential's type is the provider ("anthropic", "openai", ...).
    provider: str
    provider_label: str
    model: str = ""


class AgentContextFileBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = ""
    position: Optional[int] = None


class AgentContextFileCreate(AgentContextFileBase):
    pass


class AgentContextFileResponse(AgentContextFileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class _PermittedUrlsMixin(BaseModel):
    @field_validator("permitted_urls", check_fields=False)
    @classmethod
    def _validate_permitted_urls(cls, value):
        if value is None:
            return value
        try:
            return normalize_urls(value)
        except InvalidPermittedUrl as exc:
            raise ValueError(str(exc)) from exc


class AgentCreate(_PermittedUrlsMixin):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    # The AI configuration to run on — a credential of an AI-registered type.
    ai_configuration_id: Optional[UUID] = None
    context_files: List[AgentContextFileCreate] = Field(default_factory=list)
    permitted_urls: List[str] = Field(default_factory=list)
    feedback_memory: str = ""
    is_active: bool = True


class AgentUpdate(_PermittedUrlsMixin):
    """Partial update. Omitted fields are left alone.

    ``context_files`` is a full replacement when present — the list sent is the
    list the agent ends up with, so removing an entry means sending the others.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    ai_configuration_id: Optional[UUID] = None
    context_files: Optional[List[AgentContextFileCreate]] = None
    permitted_urls: Optional[List[str]] = None
    feedback_memory: Optional[str] = None
    is_active: Optional[bool] = None


class AgentSummaryResponse(BaseModel):
    """List-view shape: everything but the context-file bodies."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    ai_configuration_id: Optional[UUID] = None
    # Resolved for display; null when unset or when the credential was deleted.
    ai_configuration: Optional[AiConfigurationSummary] = None
    permitted_urls: List[str] = Field(default_factory=list)
    context_file_count: int = 0
    has_feedback_memory: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class AgentResponse(AgentSummaryResponse):
    context_files: List[AgentContextFileResponse] = Field(default_factory=list)
    feedback_memory: str = ""


class AgentFeedbackUpdate(BaseModel):
    """Replace the agent's feedback memory wholesale."""

    feedback_memory: str


class AgentChatRequest(BaseModel):
    """A conversation with an agent, for testing how it behaves.

    The whole conversation is sent each time: hop-core stores no chat
    history, so a test session lives entirely in the browser and leaves
    nothing behind.
    """

    messages: List[ChatMessage] = Field(min_length=1)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=200_000)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class AgentChatResponse(BaseModel):
    """The agent's reply, plus what produced it."""

    message: ChatMessage
    provider: str
    model: str
    ai_configuration_name: str
    # The composed system prompt, so the tester can see what the agent is
    # actually being told — the point of testing is to inspect this.
    system_prompt: str


class AgentFeedbackAppend(BaseModel):
    """Add one piece of feedback to what the agent already remembers."""

    feedback: str = Field(min_length=1)
    heading: Optional[str] = Field(default=None, max_length=255)
