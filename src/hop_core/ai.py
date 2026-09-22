"""Provider-agnostic AI-service interface.

hop-core never talks to a model vendor directly. Anything that needs text
generation — DITA correction, agent runs — accepts an object with an
``async generate(request) -> result`` method whose result exposes ``.content``.
Any concrete AI service (Anthropic, OpenAI, Gemini, ...) satisfies
:class:`SupportsGenerate` structurally, so no inheritance is required.
"""

from typing import List, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """One turn in a conversation."""

    role: Literal["user", "assistant"]
    content: str


class GenerationRequest(BaseModel):
    """The request shape hop-core sends to an AI service.

    Single-turn callers set ``user_prompt`` and leave ``messages`` empty.
    Multi-turn callers set both: ``messages`` carries the whole conversation,
    and ``user_prompt`` repeats its last user turn so a service written before
    conversations existed still does something sensible — it answers the
    latest question, just without the history.
    """

    system_prompt: str
    user_prompt: str
    messages: List[ChatMessage] = Field(default_factory=list)
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.7


class GenerationResult(Protocol):
    """Anything with the generated text on a ``content`` attribute."""

    content: str


@runtime_checkable
class SupportsGenerate(Protocol):
    """Structural interface for AI services used by hop-core."""

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
