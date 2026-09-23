"""Talking to the model vendors hop-core ships AI configurations for.

hop-core stays provider-agnostic at the seam that matters: anything running an
agent accepts a :class:`~hop_core.ai.SupportsGenerate`. This module supplies
one built on a stored AI configuration, so an application that registered the
built-in credential types can run an agent without writing vendor code.

An application that wants its own client keeps injecting its own service; an
application that wants a vendor hop-core does not ship registers a generator::

    AiProviderRegistry.register("bedrock", generate_with_bedrock)
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel

from hop_core.ai import ChatMessage, GenerationRequest

logger = logging.getLogger(__name__)

#: Generation is slower than a connection test and worth waiting for.
GENERATION_TIMEOUT_SECONDS = 120.0

DEFAULT_MAX_TOKENS = 2048

try:  # pragma: no cover - exercised by the absence path only
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class AiProviderError(RuntimeError):
    """A model vendor refused or failed the request.

    Carries the vendor's own words where there are any: when someone is
    testing an agent, "model not found" is the whole answer.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class GenerationResponse(BaseModel):
    """What a provider produced."""

    content: str


#: ``(api_key, model, request) -> response``
ProviderGenerator = Callable[[str, str, GenerationRequest], Awaitable[GenerationResponse]]


class AiProviderRegistry:
    """Which providers hop-core knows how to generate with."""

    _providers: Dict[str, ProviderGenerator] = {}

    @classmethod
    def register(cls, provider: str, generator: ProviderGenerator) -> None:
        cls._providers[provider] = generator

    @classmethod
    def get(cls, provider: str) -> Optional[ProviderGenerator]:
        return cls._providers.get(provider)

    @classmethod
    def is_supported(cls, provider: str) -> bool:
        return provider in cls._providers

    @classmethod
    def clear(cls) -> None:
        cls._providers.clear()


def _client():
    if httpx is None:  # pragma: no cover
        raise AiProviderError(
            "Generating with a built-in provider requires httpx. "
            "Install it with 'pip install httpx'."
        )
    return httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=False)


def _turns(request: GenerationRequest) -> List[ChatMessage]:
    """The conversation to send: the history, or the single prompt."""
    if request.messages:
        return list(request.messages)
    return [ChatMessage(role="user", content=request.user_prompt)]


def _fail(provider: str, response) -> AiProviderError:
    """Turn a vendor's error response into something worth reading."""
    detail = ""
    try:
        body = response.json()
        error = body.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or ""
        elif isinstance(error, str):
            detail = error
    except Exception:
        detail = (response.text or "")[:300]

    suffix = f": {detail}" if detail else "."
    return AiProviderError(
        f"{provider} returned HTTP {response.status_code}{suffix}",
        status_code=response.status_code,
    )


# ── Anthropic ─────────────────────────────────────────────────────────────────

async def generate_with_anthropic(
    api_key: str, model: str, request: GenerationRequest
) -> GenerationResponse:
    body: Dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
        "system": request.system_prompt,
        "messages": [{"role": m.role, "content": m.content} for m in _turns(request)],
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature

    async with _client() as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
        )

    if response.status_code != 200:
        raise _fail("Anthropic", response)

    blocks = response.json().get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return GenerationResponse(content=text)


# ── OpenAI ────────────────────────────────────────────────────────────────────

async def generate_with_openai(
    api_key: str, model: str, request: GenerationRequest
) -> GenerationResponse:
    messages = [{"role": "system", "content": request.system_prompt}]
    messages += [{"role": m.role, "content": m.content} for m in _turns(request)]

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with _client() as client:
        response = await client.post(url, headers=headers, json=body)

        # Older models want max_tokens instead.
        if response.status_code == 400 and "max_completion_tokens" in response.text:
            body["max_tokens"] = body.pop("max_completion_tokens")
            response = await client.post(url, headers=headers, json=body)

    if response.status_code != 200:
        raise _fail("OpenAI", response)

    choices = response.json().get("choices") or [{}]
    return GenerationResponse(content=choices[0].get("message", {}).get("content") or "")


# ── Google Gemini ─────────────────────────────────────────────────────────────

async def generate_with_gemini(
    api_key: str, model: str, request: GenerationRequest
) -> GenerationResponse:
    body: Dict[str, Any] = {
        # Gemini calls the assistant "model" and keeps the system prompt apart.
        "contents": [
            {
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in _turns(request)
        ],
        "generationConfig": {"maxOutputTokens": request.max_tokens or DEFAULT_MAX_TOKENS},
    }
    if request.system_prompt:
        body["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
    if request.temperature is not None:
        body["generationConfig"]["temperature"] = request.temperature

    async with _client() as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=body,
        )

    if response.status_code != 200:
        raise _fail("Google Gemini", response)

    candidates = response.json().get("candidates") or [{}]
    parts = candidates[0].get("content", {}).get("parts") or []
    return GenerationResponse(content="".join(p.get("text", "") for p in parts))


BUILTIN_GENERATORS: Dict[str, ProviderGenerator] = {
    "anthropic": generate_with_anthropic,
    "openai": generate_with_openai,
    "gemini": generate_with_gemini,
}


def register_builtin_generator(provider: str) -> None:
    """Register the built-in generator for a provider, if it has one."""
    generator = BUILTIN_GENERATORS.get(provider)
    if generator is not None:
        AiProviderRegistry.register(provider, generator)


class CredentialAiService:
    """A :class:`~hop_core.ai.SupportsGenerate` backed by an AI configuration.

    Holds the decrypted API key for the life of one request. Build it per
    call rather than caching it, so a rotated key takes effect immediately.
    """

    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self._api_key = api_key

    @classmethod
    def from_credential(cls, credential, api_key: str, model: str) -> "CredentialAiService":
        return cls(provider=credential.type, model=model, api_key=api_key)

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        generator = AiProviderRegistry.get(self.provider)
        if generator is None:
            raise AiProviderError(
                f"No generator is registered for provider {self.provider!r}."
            )
        if not self.model:
            raise AiProviderError(
                "This AI configuration does not name a model. Set one on the credential."
            )

        logger.debug("Generating with %s/%s", self.provider, self.model)
        return await generator(self._api_key, self.model, request)

    async def generate_with_tools(
        self,
        request: GenerationRequest,
        tool_executor: Callable[[str, dict], Awaitable[str]],
    ) -> GenerationResponse:
        """Generate with tool-calling support. Falls back to plain generate if
        the provider has no tool-enabled generator registered."""
        tool_gen = BUILTIN_TOOL_GENERATORS.get(self.provider)
        if tool_gen is None:
            return await self.generate(request)
        if not self.model:
            raise AiProviderError(
                "This AI configuration does not name a model. Set one on the credential."
            )
        logger.debug("Generating with tools on %s/%s", self.provider, self.model)
        return await tool_gen(self._api_key, self.model, request, tool_executor)

    def __repr__(self) -> str:  # pragma: no cover - never leak the key
        return f"CredentialAiService(provider={self.provider!r}, model={self.model!r})"


# ── Tool-enabled generators ───────────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 5

_READ_URL_TOOL_DESC = (
    "Fetch the text content of a permitted reference URL. Use this to look up "
    "documentation, specifications, or other reference material needed for the "
    "task. Only URLs from the permitted list will succeed — others are blocked."
)


async def _generate_with_anthropic_tools(
    api_key: str,
    model: str,
    request: GenerationRequest,
    tool_executor: Callable[[str, dict], Awaitable[str]],
) -> GenerationResponse:
    tool_def = {
        "name": "read_url",
        "description": _READ_URL_TOOL_DESC,
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The URL to fetch."}},
            "required": ["url"],
        },
    }
    messages = [{"role": m.role, "content": m.content} for m in _turns(request)]

    for _ in range(MAX_TOOL_ITERATIONS):
        body: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
            "system": request.system_prompt,
            "messages": messages,
            "tools": [tool_def],
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature

        async with _client() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )

        if response.status_code != 200:
            raise _fail("Anthropic", response)

        data = response.json()
        blocks = data.get("content") or []

        if data.get("stop_reason") == "tool_use":
            messages.append({"role": "assistant", "content": blocks})
            tool_results = []
            for block in blocks:
                if block.get("type") == "tool_use":
                    result = await tool_executor(block["name"], block.get("input") or {})
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block["id"], "content": result}
                    )
            messages.append({"role": "user", "content": tool_results})
        else:
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return GenerationResponse(content=text)

    return GenerationResponse(content="")


async def _generate_with_openai_tools(
    api_key: str,
    model: str,
    request: GenerationRequest,
    tool_executor: Callable[[str, dict], Awaitable[str]],
) -> GenerationResponse:
    import json as _json

    tool_def = {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": _READ_URL_TOOL_DESC,
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The URL to fetch."}},
                "required": ["url"],
            },
        },
    }

    messages = [{"role": "system", "content": request.system_prompt}]
    messages += [{"role": m.role, "content": m.content} for m in _turns(request)]
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for _ in range(MAX_TOOL_ITERATIONS):
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
            "tools": [tool_def],
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature

        async with _client() as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code == 400 and "max_completion_tokens" in response.text:
                body["max_tokens"] = body.pop("max_completion_tokens")
                response = await client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            raise _fail("OpenAI", response)

        choice = (response.json().get("choices") or [{}])[0]
        message = choice.get("message", {})

        if choice.get("finish_reason") == "tool_calls":
            messages.append(message)
            for tc in message.get("tool_calls") or []:
                args = {}
                try:
                    args = _json.loads(tc.get("function", {}).get("arguments") or "{}")
                except Exception:
                    pass
                result = await tool_executor(tc["function"]["name"], args)
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result}
                )
        else:
            return GenerationResponse(content=message.get("content") or "")

    return GenerationResponse(content="")


async def _generate_with_gemini_tools(
    api_key: str,
    model: str,
    request: GenerationRequest,
    tool_executor: Callable[[str, dict], Awaitable[str]],
) -> GenerationResponse:
    tool_def = {
        "functionDeclarations": [
            {
                "name": "read_url",
                "description": _READ_URL_TOOL_DESC,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to fetch."}
                    },
                    "required": ["url"],
                },
            }
        ]
    }

    contents = [
        {
            "role": "model" if m.role == "assistant" else "user",
            "parts": [{"text": m.content}],
        }
        for m in _turns(request)
    ]
    gemini_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    for _ in range(MAX_TOOL_ITERATIONS):
        body: Dict[str, Any] = {
            "contents": contents,
            "tools": [tool_def],
            "generationConfig": {"maxOutputTokens": request.max_tokens or DEFAULT_MAX_TOKENS},
        }
        if request.system_prompt:
            body["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        if request.temperature is not None:
            body["generationConfig"]["temperature"] = request.temperature

        async with _client() as client:
            response = await client.post(gemini_url, headers=headers, json=body)

        if response.status_code != 200:
            raise _fail("Google Gemini", response)

        candidates = response.json().get("candidates") or [{}]
        content = candidates[0].get("content", {})
        parts = content.get("parts") or []

        if any("functionCall" in p for p in parts):
            contents.append({"role": "model", "parts": parts})
            fn_responses = []
            for part in parts:
                fc = part.get("functionCall")
                if fc:
                    result = await tool_executor(fc["name"], fc.get("args") or {})
                    fn_responses.append(
                        {"functionResponse": {"name": fc["name"], "response": {"result": result}}}
                    )
            contents.append({"role": "user", "parts": fn_responses})
        else:
            return GenerationResponse(content="".join(p.get("text", "") for p in parts))

    return GenerationResponse(content="")


#: Tool-aware generator type.
ToolProviderGenerator = Callable[
    [str, str, GenerationRequest, Callable[[str, dict], Awaitable[str]]],
    Awaitable[GenerationResponse],
]

BUILTIN_TOOL_GENERATORS: Dict[str, ToolProviderGenerator] = {
    "anthropic": _generate_with_anthropic_tools,
    "openai": _generate_with_openai_tools,
    "gemini": _generate_with_gemini_tools,
}
