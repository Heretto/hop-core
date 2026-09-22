"""Built-in connection testers for hop-core's built-in credential types.

Registered automatically by
:func:`hop_core.credentials.register_builtin_types`, so an app that imports a
type gets its Test button working with no further wiring.
"""

import base64
import time
from typing import Any, Dict, Optional

from hop_core.core.security import validate_server_url
from hop_core.credentials.testing import (
    MAX_BODY_CHARS,
    TEST_TIMEOUT_SECONDS,
    CredentialTestExchange,
    CredentialTestResult,
    CredentialTesterRegistry,
)

try:  # pragma: no cover - exercised by the absence path only
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def _require_httpx():
    if httpx is None:
        raise ValueError(
            "Testing credentials requires httpx. Install it with "
            "'pip install httpx' or use the hop-core[dev] extra."
        )
    return httpx


def _client(**kwargs):
    """An HTTP client that never follows redirects.

    A redirect is the simplest way for a host that passed SSRF validation to
    hand the request to one that would not have.
    """
    return _require_httpx().AsyncClient(
        timeout=TEST_TIMEOUT_SECONDS, follow_redirects=False, **kwargs
    )


async def _send(client, method: str, url: str, **kwargs):
    """Make one request and record it, so the result can explain itself."""
    started = time.monotonic()
    response = await getattr(client, method.lower())(url, **kwargs)
    duration_ms = int((time.monotonic() - started) * 1000)

    body = response.text or ""
    truncated = len(body) > MAX_BODY_CHARS

    exchange = CredentialTestExchange(
        method=method,
        url=url,
        status_code=response.status_code,
        response_body=body[:MAX_BODY_CHARS],
        body_truncated=truncated,
        duration_ms=duration_ms,
    )
    return exchange, response


def _failure(message: str, exchange: Optional[CredentialTestExchange] = None) -> CredentialTestResult:
    return CredentialTestResult(success=False, message=message, exchange=exchange)


def _require(payload: Dict[str, Any], *names: str) -> None:
    missing = [name for name in names if not str(payload.get(name) or "").strip()]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")


def _checked_base_url(payload: Dict[str, Any]) -> str:
    """The credential's server URL, validated against SSRF and normalized."""
    return validate_server_url(str(payload["server_url"]).strip()).rstrip("/")


def _redirect_message(response) -> str:
    return (
        f"The server redirected the request (HTTP {response.status_code}). "
        "Check the server URL — redirects are not followed."
    )


# ── Jira ──────────────────────────────────────────────────────────────────────

async def test_jira(payload: Dict[str, Any]) -> CredentialTestResult:
    """Ask Jira who we are. Answers auth and reachability in one call."""
    _require(payload, "server_url", "email", "api_token")
    base_url = _checked_base_url(payload)

    token = base64.b64encode(
        f"{payload['email']}:{payload['api_token']}".encode()
    ).decode("ascii")

    async with _client() as client:
        exchange, response = await _send(
            client, "GET", f"{base_url}/rest/api/3/myself",
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
        )

    if response.is_redirect:
        return _failure(_redirect_message(response), exchange)

    if response.status_code == 200:
        account = response.json()
        name = account.get("displayName") or account.get("emailAddress") or "unknown user"
        return CredentialTestResult(
            success=True,
            message=f"Connected to Jira as {name}.",
            details={"account": name},
            exchange=exchange,
        )

    if response.status_code == 401:
        return _failure(
            "Jira rejected the credentials — check the email and API token.", exchange
        )
    if response.status_code == 403:
        return _failure(
            "Jira accepted the token but denied access — check its permissions.", exchange
        )

    return _failure(f"Jira returned HTTP {response.status_code}.", exchange)


# ── Heretto ───────────────────────────────────────────────────────────────────

async def test_heretto(payload: Dict[str, Any]) -> CredentialTestResult:
    """Call a Heretto endpoint that requires authentication but changes nothing."""
    _require(payload, "server_url", "username", "token")
    base_url = _checked_base_url(payload)

    async with _client() as client:
        exchange, response = await _send(
            client, "GET", f"{base_url}/api/v1/user",
            headers={
                "Authorization": f"Bearer {payload['token']}",
                "Accept": "application/json",
            },
        )

    if response.is_redirect:
        return _failure(_redirect_message(response), exchange)

    if response.status_code == 200:
        return CredentialTestResult(
            success=True,
            message=f"Connected to Heretto as {payload['username']}.",
            details={"account": payload["username"]},
            exchange=exchange,
        )

    if response.status_code in (401, 403):
        return _failure(
            "Heretto rejected the credentials — check the username and API token.", exchange
        )

    return _failure(f"Heretto returned HTTP {response.status_code}.", exchange)


# ── AI providers ──────────────────────────────────────────────────────────────
#
# Each sends the smallest possible completion request: it proves the key works
# *and* that the named model is reachable, which listing models does not.

_TEST_PROMPT = "Reply with the single word: ok"


def _model_error(payload, provider: str, response, exchange) -> CredentialTestResult:
    model = payload.get("model")
    if response.status_code == 404 and model:
        return _failure(f"{provider} does not recognise the model {model!r}.", exchange)
    if response.status_code in (401, 403):
        return _failure(f"{provider} rejected the API key.", exchange)
    if response.status_code == 429:
        return _failure(
            f"{provider} rate-limited the request — try again shortly.", exchange
        )
    return _failure(f"{provider} returned HTTP {response.status_code}.", exchange)


def _ok(provider: str, model: str, exchange) -> CredentialTestResult:
    return CredentialTestResult(
        success=True,
        message=f"{provider} answered using {model}.",
        details={"model": model},
        exchange=exchange,
    )


async def test_anthropic(payload: Dict[str, Any]) -> CredentialTestResult:
    _require(payload, "api_key")
    model = str(payload.get("model") or "").strip() or "claude-sonnet-5"

    async with _client() as client:
        exchange, response = await _send(
            client, "POST", "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": payload["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": _TEST_PROMPT}],
            },
        )

    if response.status_code == 200:
        return _ok("Anthropic", model, exchange)
    return _model_error(payload, "Anthropic", response, exchange)


async def test_openai(payload: Dict[str, Any]) -> CredentialTestResult:
    _require(payload, "api_key")
    model = str(payload.get("model") or "").strip() or "gpt-5"

    body = {
        "model": model,
        "messages": [{"role": "user", "content": _TEST_PROMPT}],
        "max_completion_tokens": 16,
    }

    async with _client() as client:
        headers = {
            "Authorization": f"Bearer {payload['api_key']}",
            "Content-Type": "application/json",
        }
        url = "https://api.openai.com/v1/chat/completions"
        exchange, response = await _send(client, "POST", url, headers=headers, json=body)

        # Older models reject max_completion_tokens and want max_tokens.
        if response.status_code == 400 and "max_completion_tokens" in response.text:
            body["max_tokens"] = body.pop("max_completion_tokens")
            exchange, response = await _send(client, "POST", url, headers=headers, json=body)

    if response.status_code == 200:
        return _ok("OpenAI", model, exchange)
    if response.status_code == 404:
        return _failure(f"OpenAI does not recognise the model {model!r}.", exchange)
    return _model_error(payload, "OpenAI", response, exchange)


async def test_gemini(payload: Dict[str, Any]) -> CredentialTestResult:
    _require(payload, "api_key")
    model = str(payload.get("model") or "").strip() or "gemini-2.5-pro"

    async with _client() as client:
        exchange, response = await _send(
            client, "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            # The key goes in a header, not the query string, so it stays out
            # of any intermediary's request log — and out of this exchange.
            headers={"x-goog-api-key": payload["api_key"], "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": _TEST_PROMPT}]}],
                "generationConfig": {"maxOutputTokens": 16},
            },
        )

    if response.status_code == 200:
        return _ok("Google Gemini", model, exchange)
    return _model_error(payload, "Google Gemini", response, exchange)


BUILTIN_TESTERS = {
    "jira": test_jira,
    "heretto": test_heretto,
    "anthropic": test_anthropic,
    "openai": test_openai,
    "gemini": test_gemini,
}


def register_builtin_tester(type_key: str) -> None:
    """Register the built-in tester for a type, if it has one."""
    tester = BUILTIN_TESTERS.get(type_key)
    if tester is not None:
        CredentialTesterRegistry.register(type_key, tester)
