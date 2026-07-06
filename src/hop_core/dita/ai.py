"""Minimal AI-service interface for DITA correction.

DitaCorrectionService is provider-agnostic: it only needs an object with an
``async generate(request) -> result`` method whose result exposes ``.content``.
Any concrete AI service (Anthropic, OpenAI, Gemini, ...) satisfies
SupportsGenerate structurally — no inheritance required.
"""

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel


class GenerationRequest(BaseModel):
    """The request shape DitaCorrectionService sends to the AI service."""

    system_prompt: str
    user_prompt: str
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.7


class GenerationResult(Protocol):
    """Anything with the generated text on a ``content`` attribute."""

    content: str


@runtime_checkable
class SupportsGenerate(Protocol):
    """Structural interface for AI services used by DitaCorrectionService."""

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
