"""Agent configuration Pydantic schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Literal, Optional
from datetime import datetime
from uuid import UUID

from hop_core.agents.definition import REFERENCE_TYPES
from hop_core.agents.urls import InvalidPermittedUrl, normalize_url, normalize_urls
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


ReferenceType = Literal["general", "style_guide", "information_model", "terminology"]
assert set(ReferenceType.__args__) == set(REFERENCE_TYPES)  # keep the two lists in step

_FILE_ID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class AgentReferenceIn(BaseModel):
    """A reference as the editor sends it.

    ``kind="url"`` needs ``url``. ``kind="heretto"`` needs ``file_id`` and a
    ``credential_id`` naming a Heretto connection in the organization; a null
    ``credential_id`` is accepted only so a reference whose connection was
    deleted can be saved back unchanged — it stays unavailable. ``title``,
    ``path`` and ``is_map`` are what the resolve endpoint returned, kept for
    display. Every reference may carry ``guidance`` on how to use it.
    """

    kind: Literal["url", "heretto"]
    guidance: str = Field(default="", max_length=4000)
    url: Optional[str] = None
    credential_id: Optional[UUID] = None
    file_id: Optional[str] = Field(default=None, pattern=_FILE_ID)
    title: Optional[str] = Field(default=None, max_length=500)
    path: Optional[str] = None
    is_map: bool = False
    reference_type: Optional[ReferenceType] = None

    @model_validator(mode="after")
    def _check_kind(self) -> "AgentReferenceIn":
        self.guidance = (self.guidance or "").strip()
        if self.kind == "url":
            if not self.url:
                raise ValueError("A URL reference needs a url")
            try:
                self.url = normalize_url(self.url)
            except InvalidPermittedUrl as exc:
                raise ValueError(str(exc)) from exc
            self.credential_id = self.file_id = self.reference_type = None
            self.title = self.path = None
            self.is_map = False
        else:
            if not self.file_id:
                raise ValueError("A Heretto reference needs a file_id")
            self.file_id = self.file_id.lower()
            self.reference_type = self.reference_type or "general"
            self.url = None
        return self


class AgentReferenceResponse(AgentReferenceIn):
    # Null for URLs carried over from an agent saved before references existed.
    id: Optional[UUID] = None
    # The Heretto connection's name, for display; null when it was deleted,
    # which leaves the reference unavailable until it is pointed elsewhere.
    credential_name: Optional[str] = None
    available: bool = True

    @model_validator(mode="after")
    def _check_kind(self) -> "AgentReferenceResponse":
        # Stored references are reported as they are, including ones whose
        # connection was deleted (credential_id is then null).
        return self


class HerettoConnection(BaseModel):
    """A Heretto credential an agent can read references through."""

    id: UUID
    name: str
    server_url: str = ""


class HerettoResolveRequest(BaseModel):
    credential_id: UUID
    identifier: str = Field(min_length=1, max_length=2000)


class HerettoResolveResponse(BaseModel):
    file_id: str
    title: str
    name: str
    path: Optional[str] = None
    is_map: bool = False


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
    # Older clients send permitted_urls; newer ones send references, which
    # wins when both are present.
    permitted_urls: List[str] = Field(default_factory=list)
    references: Optional[List[AgentReferenceIn]] = None
    # The DTD set this agent validates DITA against; null follows the
    # organization default.
    dtd_set_id: Optional[str] = Field(default=None, max_length=64)
    feedback_memory: str = ""
    is_active: bool = True


class AgentUpdate(_PermittedUrlsMixin):
    """Partial update. Omitted fields are left alone.

    ``context_files`` and ``references`` are full replacements when present —
    the list sent is the list the agent ends up with, so removing an entry
    means sending the others. ``permitted_urls`` alone (older clients) replaces
    only the URL references.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    ai_configuration_id: Optional[UUID] = None
    context_files: Optional[List[AgentContextFileCreate]] = None
    permitted_urls: Optional[List[str]] = None
    references: Optional[List[AgentReferenceIn]] = None
    # Sent as null to go back to following the organization default.
    dtd_set_id: Optional[str] = Field(default=None, max_length=64)
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
    dtd_set_id: Optional[str] = None
    context_file_count: int = 0
    has_feedback_memory: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class AgentResponse(AgentSummaryResponse):
    context_files: List[AgentContextFileResponse] = Field(default_factory=list)
    references: List[AgentReferenceResponse] = Field(default_factory=list)
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
