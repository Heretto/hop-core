"""Normalization and matching for an agent's permitted-URL list.

An entry in the list is a *prefix pattern*, not an exact URL: listing
``https://docs.example.com/guide`` permits every page beneath ``/guide``.
The host may carry a leading ``*.`` to cover subdomains.
"""

from typing import Iterable, List
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": "80", "https": "443"}
ALLOWED_SCHEMES = ("http", "https")


class InvalidPermittedUrl(ValueError):
    """Raised when a permitted-URL entry cannot be understood."""


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url``, or raise :class:`InvalidPermittedUrl`.

    Lowercases the scheme and host, drops a default port and any fragment, and
    removes a trailing slash from the path so ``/guide`` and ``/guide/`` are the
    same entry.
    """
    raw = (url or "").strip()
    if not raw:
        raise InvalidPermittedUrl("URL must not be empty")

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidPermittedUrl(
            f"{raw!r}: URL must start with http:// or https://"
        )

    host = (parts.hostname or "").lower()
    if not host:
        raise InvalidPermittedUrl(f"{raw!r}: URL is missing a host")

    netloc = host
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidPermittedUrl(f"{raw!r}: {exc}") from exc
    if port is not None and str(port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if path == "/":
        path = ""

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def normalize_urls(urls: Iterable[str]) -> List[str]:
    """Normalize a list of entries, dropping duplicates and keeping order."""
    seen: List[str] = []
    for url in urls or []:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _host_matches(candidate_host: str, entry_host: str) -> bool:
    if entry_host.startswith("*."):
        domain = entry_host[2:]
        return candidate_host == domain or candidate_host.endswith("." + domain)
    return candidate_host == entry_host


def is_url_permitted(url: str, permitted_urls: Iterable[str]) -> bool:
    """Whether ``url`` falls under any entry in ``permitted_urls``.

    A candidate matches when the scheme and host match and the entry's path is
    the candidate's path or one of its parent segments. Entries that carry a
    query string must be matched exactly; entries without one ignore the
    candidate's query. A malformed candidate or entry never matches.
    """
    try:
        candidate = urlsplit(normalize_url(url))
    except InvalidPermittedUrl:
        return False

    for entry_url in permitted_urls or []:
        try:
            entry = urlsplit(normalize_url(entry_url))
        except InvalidPermittedUrl:
            continue

        if candidate.scheme != entry.scheme:
            continue
        if not _host_matches(candidate.netloc, entry.netloc):
            continue
        if entry.query and candidate.query != entry.query:
            continue
        if entry.path and not (
            candidate.path == entry.path or candidate.path.startswith(entry.path + "/")
        ):
            continue
        return True

    return False
