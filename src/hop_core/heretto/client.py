"""A small, read-only client for the Heretto CCMS REST API.

Covers what agent references need: a file's record, its content, its
dependencies (how a map's links resolve to files), and turning a pasted
identifier — a file ID, a Heretto URL containing one, or a repository path —
into a file ID.

The endpoints are the ones the Heretto skills use against live instances.
Two things about the API shape the design:

- Only ``/rest/branches/{branch}/repositories/{repo}/documents/`` is
  path-addressable; everything below it is reached by folder ID, so a
  repository path is resolved by walking folders.
- Full-text search (``/ezdnxtgen/api/search``) does not answer API-token
  requests, so nothing here searches.

Every request goes to the credential's server URL after the same SSRF check
the connection tester uses, and redirects are never followed — a redirect is
the simplest way for a host that passed the check to hand the request to one
that would not have.
"""

import base64
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

from hop_core.core.security import validate_server_url

REQUEST_TIMEOUT = 20.0  # seconds
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
# Folder walking is one request per level; a path deeper than this is a typo.
MAX_PATH_DEPTH = 16


class HerettoError(Exception):
    """A Heretto request failed, or its answer could not be understood.

    ``message`` is written for the person configuring the agent.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class HerettoFile:
    """A file's record: what the agent editor shows and what the content
    layer needs to decide how to read it."""

    id: str
    name: str
    title: Optional[str] = None
    mime_type: Optional[str] = None
    path: Optional[str] = None
    last_modified: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def is_map(self) -> bool:
        name = (self.name or "").lower()
        content_type = (self.metadata.get("content-type") or "").lower()
        return name.endswith((".ditamap", ".bookmap")) or content_type in ("map", "bookmap")

    @property
    def display_title(self) -> str:
        return self.title or self.name or self.id


@dataclass
class HerettoFolder:
    id: str
    name: Optional[str]
    folders: List[Tuple[str, str]]     # (name, id)
    resources: List[Tuple[str, str]]   # (name, id)


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_xml(raw: bytes, what: str) -> ET.Element:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise HerettoError(f"Heretto returned a {what} that could not be read: {exc}") from exc


def parse_file(raw: bytes) -> HerettoFile:
    root = _parse_xml(raw, "file record")
    if _local(root.tag) != "resource":
        raise HerettoError("That identifier names a folder, not a file.")

    def text(tag: str) -> Optional[str]:
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else None

    metadata = {
        m.get("name"): (m.text or "").strip()
        for m in root.iter("meta")
        if m.get("name")
    }
    return HerettoFile(
        id=root.get("id") or "",
        name=text("name") or "",
        title=metadata.get("title") or None,
        mime_type=text("mime-type"),
        path=text("xmldb-uri"),
        last_modified=root.get("last-modified"),
        metadata=metadata,
    )


def parse_folder(raw: bytes) -> HerettoFolder:
    root = _parse_xml(raw, "folder listing")
    name_el = root.find("name")
    children = root.find("children")
    folders, resources = [], []
    for child in (children if children is not None else []):
        entry = (child.get("name") or "", child.get("id") or "")
        if _local(child.tag) == "folder":
            folders.append(entry)
        elif _local(child.tag) == "resource":
            resources.append(entry)
    return HerettoFolder(
        id=root.get("id") or "",
        name=name_el.text if name_el is not None else None,
        folders=folders,
        resources=resources,
    )


def parse_dependencies(raw: bytes) -> Dict[str, str]:
    """``relative-uri -> file id`` for every dependency, also indexed by bare
    file name for hrefs written relative to a different folder."""
    root = _parse_xml(raw, "dependency list")
    out: Dict[str, str] = {}
    for res in root:
        rid, uri = res.get("id"), res.get("relative-uri")
        if not rid or not uri:
            continue
        out.setdefault(uri, rid)
        out.setdefault(uri.rsplit("/", 1)[-1], rid)
    return out


class HerettoClient:
    """Read-only access to one Heretto instance, as one credential's account.

    Built from the decrypted credential payload (``server_url``, ``username``,
    ``token``). Use as an async context manager so one connection pool serves
    a whole map expansion.
    """

    def __init__(self, server_url: str, username: str, token: str,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        if not server_url or not username or not token:
            raise HerettoError("The Heretto connection is missing its server URL, username or API token.")
        try:
            self.base_url = validate_server_url(server_url.strip()).rstrip("/")
        except ValueError as exc:
            raise HerettoError(f"The Heretto server URL is not allowed: {exc}") from exc
        basic = base64.b64encode(f"{username}:{token}".encode()).decode()
        # The file API takes HTTP Basic with the API token as the password;
        # Bearer is the fallback for instances that only accept that.
        self._auth_headers = [f"Basic {basic}", f"Bearer {token}"]
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def from_payload(cls, payload: dict, **kwargs) -> "HerettoClient":
        return cls(
            str(payload.get("server_url") or ""),
            str(payload.get("username") or ""),
            str(payload.get("token") or ""),
            **kwargs,
        )

    async def __aenter__(self) -> "HerettoClient":
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=False, transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── transport ─────────────────────────────────────────────────────────

    async def _get(self, path: str, accept: str = "application/xml") -> bytes:
        if self._client is None:
            raise RuntimeError("Use HerettoClient as an async context manager")
        response = None
        for auth in list(self._auth_headers):
            try:
                response = await self._client.get(
                    self.base_url + path, headers={"Authorization": auth, "Accept": accept},
                )
            except httpx.HTTPError as exc:
                raise HerettoError(f"Could not reach Heretto: {exc}") from exc
            if response.status_code != 401:
                # Remember the scheme that worked, so later calls go straight to it.
                self._auth_headers = [auth]
                break
        assert response is not None
        if response.is_redirect:
            raise HerettoError(
                f"Heretto redirected the request (HTTP {response.status_code}). "
                "Check the connection's server URL — redirects are not followed.",
                response.status_code,
            )
        if response.status_code in (401, 403):
            raise HerettoError(
                "Heretto rejected the connection's credentials — check the username and API token.",
                response.status_code,
            )
        if response.status_code == 404:
            raise HerettoError("Heretto has no file or folder with that identifier.", 404)
        if response.status_code >= 400:
            raise HerettoError(f"Heretto returned HTTP {response.status_code}.", response.status_code)
        return response.content

    # ── read operations ───────────────────────────────────────────────────

    async def get_file(self, file_id: str) -> HerettoFile:
        return parse_file(await self._get(f"/rest/all-files/{file_id}"))

    async def get_content(self, file_id: str) -> bytes:
        return await self._get(f"/rest/all-files/{file_id}/content")

    async def get_dependencies(self, file_id: str) -> Dict[str, str]:
        return parse_dependencies(await self._get(f"/rest/all-files/{file_id}/links/dependencies"))

    async def get_folder(self, folder_id: str) -> HerettoFolder:
        return parse_folder(await self._get(f"/rest/all-files/{folder_id}"))

    async def _repo_root(self, branch: str, repo: str) -> HerettoFolder:
        return parse_folder(await self._get(f"/rest/branches/{branch}/repositories/{repo}/documents/"))

    # ── identifiers ───────────────────────────────────────────────────────

    async def resolve(self, identifier: str) -> HerettoFile:
        """The file a pasted identifier names.

        Accepts a file ID, any Heretto URL containing one, or a repository
        path such as ``master/product/documents/guides/style.dita`` (the
        ``documents`` segment may be left out).
        """
        ident = (identifier or "").strip()
        if not ident:
            raise HerettoError("Enter a Heretto file ID, URL or repository path.")
        found = UUID_RE.search(ident)
        if found:
            return await self.get_file(found.group(0).lower())
        if "/" in ident:
            return await self.get_file(await self._resolve_path(ident))
        raise HerettoError(
            "Not a Heretto identifier. Paste a file ID, a Heretto URL containing one, "
            "or a repository path like master/product/documents/guides/style.dita."
        )

    async def _resolve_path(self, path: str) -> str:
        parts = [p for p in path.strip().strip("/").split("/") if p]
        if len(parts) < 3:
            raise HerettoError(
                "A repository path needs a branch, a repository and a file, "
                "e.g. master/product/documents/guides/style.dita."
            )
        branch, repo, segments = parts[0], parts[1], parts[2:]
        if segments[0] == "documents":
            segments = segments[1:]
        if not segments:
            raise HerettoError("That path names a repository, not a file.")
        if len(segments) > MAX_PATH_DEPTH:
            raise HerettoError("That repository path is deeper than any Heretto folder tree should be.")

        current = await self._repo_root(branch, repo)
        trail = f"{branch}/{repo}/documents"
        for index, segment in enumerate(segments):
            target = segment.lower()
            if index == len(segments) - 1:
                for name, rid in current.resources:
                    if name.lower() == target:
                        return rid
                raise HerettoError(
                    f"No file named {segment!r} in {trail}/. "
                    f"It contains: {self._listing(current)}"
                )
            folder_id = next((fid for name, fid in current.folders if name.lower() == target), None)
            if folder_id is None:
                raise HerettoError(
                    f"No folder named {segment!r} in {trail}/. "
                    f"It contains: {self._listing(current)}"
                )
            current = await self.get_folder(folder_id)
            trail += "/" + segment
        raise HerettoError(f"Could not resolve {path!r}.")  # pragma: no cover

    @staticmethod
    def _listing(folder: HerettoFolder) -> str:
        names = sorted([n + "/" for n, _ in folder.folders] + [n for n, _ in folder.resources])
        return ", ".join(names[:15]) + (" …" if len(names) > 15 else "") if names else "(nothing)"
