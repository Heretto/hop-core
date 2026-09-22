"""Safe, read-only URL fetcher for agent reference material.

Guards against SSRF by resolving hostnames before connecting.
Only fetches URLs the agent's operator explicitly permitted.
"""

import asyncio
import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from html import unescape
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from hop_core.agents.urls import is_url_permitted

# Fetch up to 200 KB of raw HTML; extracted text is capped separately below.
MAX_RAW_BYTES = 200_000
MAX_TEXT_CHARS = 50_000
FETCH_TIMEOUT = 10.0          # seconds
MAX_REDIRECTS = 5

_PRIVATE_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",   # link-local IPv4
        "0.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "fe80::/10",        # link-local IPv6
    )
]


@dataclass
class FetchResult:
    url: str
    content: str = ""
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    response_bytes: int = 0
    duration_ms: int = 0
    blocked_reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.blocked_reason is None

    @property
    def status(self) -> str:
        if self.blocked_reason:
            return "blocked"
        if self.http_status and self.http_status >= 400:
            return "error"
        return "success"


# Matches entire non-visible blocks: content between opening and closing tag.
_BLOCK_RE = re.compile(
    r"<(script|style|head|svg|canvas|noscript|template)(?:\s[^>]*)?>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t]+")


def _is_private(hostname: str) -> bool:
    """Return True if hostname resolves to a private or loopback address."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        raw = info[4][0].split("%")[0]  # strip IPv6 scope id
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return True
        if any(addr in net for net in _PRIVATE_NETWORKS):
            return True
    return False


def _to_text(body: bytes, content_type: str) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    if "html" in content_type:
        text = _BLOCK_RE.sub(" ", text)       # drop non-visible blocks
        text = _TAG_RE.sub(" ", text)          # strip remaining tags
        text = unescape(text)                  # &amp; → & etc.
        lines = []
        for line in text.splitlines():
            line = _SPACE_RE.sub(" ", line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)
    return text


async def fetch_url(url: str, permitted_urls: List[str]) -> FetchResult:
    """Fetch *url* if it is permitted and resolves to a public address."""
    start = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - start) * 1000)

    def blocked(reason: str) -> FetchResult:
        return FetchResult(url=url, blocked_reason=reason, duration_ms=elapsed())

    if not is_url_permitted(url, permitted_urls):
        return blocked("not in permitted URLs")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return blocked("scheme not allowed")

    hostname = parsed.hostname or ""
    if not hostname:
        return blocked("no hostname")

    try:
        private = await asyncio.get_event_loop().run_in_executor(None, _is_private, hostname)
    except Exception:
        private = True

    if private:
        return blocked("resolves to private address")

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": "hop-agent/1.0 (reference reader)"},
        ) as client:
            response = await client.get(url)

        raw_ct = response.headers.get("content-type", "")
        ct = raw_ct.split(";")[0].strip().lower()
        allowed_ct = (
            ct.startswith("text/")
            or ct in ("application/json", "application/xml", "application/xhtml+xml")
        )
        if ct and not allowed_ct:
            return FetchResult(
                url=str(response.url),
                http_status=response.status_code,
                content_type=raw_ct,
                blocked_reason=f"content-type not allowed: {ct}",
                duration_ms=elapsed(),
            )

        raw_body = response.content[:MAX_RAW_BYTES]
        return FetchResult(
            url=str(response.url),
            content=_to_text(raw_body, ct)[:MAX_TEXT_CHARS],
            http_status=response.status_code,
            content_type=raw_ct,
            response_bytes=len(raw_body),
            duration_ms=elapsed(),
        )

    except httpx.TimeoutException:
        return blocked("request timed out")
    except Exception as exc:
        return blocked(f"fetch error: {exc}")
