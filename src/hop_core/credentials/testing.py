"""Testing a credential: does it actually reach the thing it names?

A *tester* is an async callable taking a decrypted payload and returning a
:class:`CredentialTestResult`. Types register one the same way they register
fields, so the management UI can offer a Test button for exactly the types
that can answer.

Testers talk to third-party services, so two rules apply to every one of them:

- **A user-supplied host is validated before it is called.** Jira and Heretto
  URLs come from whoever filled in the form, so they go through
  :func:`hop_core.core.security.validate_server_url`, and redirects are not
  followed — a redirect is exactly how a validated host reaches an internal
  one.
- **Nothing secret goes into the result.** A result is shown in a browser and
  may be logged; it says what happened, never what was sent.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: How long any single credential test may take.
TEST_TIMEOUT_SECONDS = 20.0

#: How much of a response body to keep. Enough for an API error object,
#: short enough that nobody pastes a megabyte of HTML into a dialog.
MAX_BODY_CHARS = 4000

_REDACTED = "***redacted***"


def redact(text: str, secrets: Iterable[str]) -> str:
    """Blank out any secret value that appears in ``text``.

    A third party's error body can echo the request back — including the key
    it rejected. This runs over everything that reaches a result.
    """
    for secret in secrets:
        value = str(secret or "")
        # Very short values would match far too much to be worth replacing.
        if len(value) >= 8:
            text = text.replace(value, _REDACTED)
    return text


class CredentialTestExchange(BaseModel):
    """What was sent and what came back, for the diagnostics dialog.

    Present only when a request was actually made: a credential rejected by
    URL validation never leaves the building and has no exchange to show.
    """

    method: str
    # The URL called, with no query-string secrets — testers put keys in headers.
    url: str
    status_code: Optional[int] = None
    # Truncated and redacted. Verbatim otherwise, because the whole point is
    # to show what the service actually said.
    response_body: str = ""
    body_truncated: bool = False
    duration_ms: Optional[int] = None


class CredentialTestResult(BaseModel):
    """The outcome of testing one credential."""

    success: bool
    message: str
    # Non-sensitive extras worth showing, such as the account that answered.
    details: Dict[str, Any] = Field(default_factory=dict)
    exchange: Optional[CredentialTestExchange] = None
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


CredentialTester = Callable[[Dict[str, Any]], Awaitable[CredentialTestResult]]


class CredentialTesterRegistry:
    """Which credential types can be tested, and how.

    Host apps register testers for their own types::

        CredentialTesterRegistry.register("zendesk", test_zendesk)
    """

    _testers: Dict[str, CredentialTester] = {}

    @classmethod
    def register(cls, type_key: str, tester: CredentialTester) -> None:
        cls._testers[type_key] = tester

    @classmethod
    def get(cls, type_key: str) -> Optional[CredentialTester]:
        return cls._testers.get(type_key)

    @classmethod
    def is_testable(cls, type_key: str) -> bool:
        return type_key in cls._testers

    @classmethod
    def clear(cls) -> None:
        cls._testers.clear()


async def run_test(type_key: str, payload: Dict[str, Any]) -> CredentialTestResult:
    """Run the tester for ``type_key``, turning any failure into a result.

    A tester that raises is a failed test, not a 500: the whole point of the
    button is to report what went wrong.
    """
    tester = CredentialTesterRegistry.get(type_key)
    if tester is None:
        return CredentialTestResult(
            success=False,
            message=f"Credentials of type {type_key!r} cannot be tested.",
        )

    try:
        result = await tester(payload)
        # Belt and braces: a tester could put a secret in a message by
        # accident, and this is the last place to catch it.
        secrets = [str(v) for v in payload.values() if isinstance(v, str)]
        result.message = redact(result.message, secrets)
        if result.exchange is not None:
            result.exchange.response_body = redact(result.exchange.response_body, secrets)
        return result
    except ValueError as exc:
        # Raised by validate_server_url and by payload checks — the message is
        # written for the person who filled in the form.
        return CredentialTestResult(success=False, message=str(exc))
    except Exception:
        logger.warning("Credential test for type %r failed", type_key, exc_info=True)
        return CredentialTestResult(
            success=False,
            message="The test could not be completed. Check the server logs for details.",
        )
