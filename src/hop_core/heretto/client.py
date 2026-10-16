"""A small, read-only client for the Heretto CCMS REST API.

Covers what agent references and the file browser need: a file's record, its
content, its dependencies (how a map's links resolve to files), folder
listings, the repositories, finding files by name, and turning a pasted
identifier — a file ID, a Heretto URL containing one, or a repository path —
into a file ID.

The endpoints are the ones the Heretto skills use against live instances.
Two things about the API shape the design:

- Only ``/rest/branches/{branch}/repositories/{repo}/documents/`` is
  path-addressable; everything below it is reached by folder ID, so a
  repository path is resolved by walking folders.
- Full-text search (``/ezdnxtgen/api/search``) does not answer API-token
  requests, so ``find_by_name`` searches by walking folders instead.

Every request goes to the credential's server URL after the same SSRF check
the connection tester uses, and redirects are never followed — a redirect is
the simplest way for a host that passed the check to hand the request to one
that would not have.
"""

import asyncio
import base64
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from hop_core.core.security import validate_server_url

REQUEST_TIMEOUT = 20.0  # seconds
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
# Folder walking is one request per level; a path deeper than this is a typo.
MAX_PATH_DEPTH = 16

# Finding by name is one request per folder, so it is bounded; hitting any
# limit is reported as ``truncated``, never applied silently.
SEARCH_MAX_FOLDERS = 300
SEARCH_MAX_DEPTH = 12
SEARCH_MAX_MATCHES = 200
SEARCH_CONCURRENCY = 6
SEARCH_TIME_LIMIT = 20.0  # seconds

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff")
MAP_TYPES = {"map", "bookmap", "sitemap"}


def file_kind(name: str, mime_type: Optional[str] = None, heretto_type: Optional[str] = None) -> str:
    """``map``, ``topic``, ``image`` or ``other`` — what a picker filters on.

    ``heretto_type`` is the ``type`` a folder listing gives each file (Topic,
    Map, SiteMap, …); the extension decides when it is missing.
    """
    lower = (name or "").lower()
    mime = (mime_type or "").lower()
    if lower.endswith((".ditamap", ".bookmap")) or (heretto_type or "").lower() in MAP_TYPES:
        return "map"
    if mime.startswith("image/") or lower.endswith(IMAGE_EXTENSIONS):
        return "image"
    if lower.endswith((".dita", ".xml")):
        return "topic"
    return "other"


class HerettoError(Exception):
    """A Heretto request failed, or its answer could not be understood.

    ``message`` is written for the person configuring the agent.
    ``folder_id`` is set when a typed path went wrong inside a folder — the
    deepest one it reached — so a UI can offer to browse it.
    """

    def __init__(self, message: str, status_code: Optional[int] = None,
                 folder_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.folder_id = folder_id


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
    folder_id: Optional[str] = None

    @property
    def is_map(self) -> bool:
        name = (self.name or "").lower()
        content_type = (self.metadata.get("content-type") or "").lower()
        return name.endswith((".ditamap", ".bookmap")) or content_type in ("map", "bookmap")

    @property
    def kind(self) -> str:
        return "map" if self.is_map else file_kind(self.name, self.mime_type)

    @property
    def display_title(self) -> str:
        return self.title or self.name or self.id


@dataclass
class HerettoEntry:
    """One child in a folder listing."""

    id: str
    name: str
    is_folder: bool
    heretto_type: Optional[str] = None
    mime_type: Optional[str] = None

    @property
    def kind(self) -> str:
        return "folder" if self.is_folder else file_kind(self.name, self.mime_type, self.heretto_type)


@dataclass
class HerettoFolder:
    id: str
    name: Optional[str]
    folders: List[Tuple[str, str]]     # (name, id)
    resources: List[Tuple[str, str]]   # (name, id)
    path: Optional[str] = None
    parent_id: Optional[str] = None
    entries: List[HerettoEntry] = field(default_factory=list)

    @property
    def is_documents_root(self) -> bool:
        """The ``documents`` folder of a repository: the top of what can be browsed."""
        if (self.name or "").lower() != "documents":
            return False
        parts = [p for p in (self.path or "").split("/") if p]
        return len(parts) <= 3 or parts[-3] == "repositories"

    @property
    def repository(self) -> Optional[Tuple[str, str]]:
        """``(branch, repository)`` read from a ``branch/repo/documents/…`` path."""
        parts = [p for p in (self.path or "").split("/") if p]
        if len(parts) >= 3 and parts[2] == "documents":
            return parts[0], parts[1]
        return None


@dataclass
class NameMatch:
    entry: HerettoEntry
    folder_id: str
    folder_path: str   # relative to where the search started: "/" or "/guides/install"


@dataclass
class NameSearch:
    matches: List[NameMatch]
    folders_searched: int
    truncated: bool


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
        folder_id=root.get("folder-uuid") or root.get("parent-folder-id"),
    )


def parse_folder(raw: bytes) -> HerettoFolder:
    root = _parse_xml(raw, "folder listing")
    if _local(root.tag) == "resource":
        raise HerettoError("That identifier names a file, not a folder.")
    name_el = root.find("name")
    path_el = root.find("xmldb-uri")
    children = root.find("children")
    folders, resources, entries = [], [], []
    for child in (children if children is not None else []):
        name, child_id = child.get("name") or "", child.get("id") or ""
        tag = _local(child.tag)
        if tag == "folder":
            folders.append((name, child_id))
            entries.append(HerettoEntry(child_id, name, True))
        elif tag == "resource":
            resources.append((name, child_id))
            entries.append(HerettoEntry(
                child_id, name, False, child.get("type") or None, child.get("mime-type") or None,
            ))
    return HerettoFolder(
        id=root.get("id") or "",
        name=name_el.text if name_el is not None else None,
        folders=folders,
        resources=resources,
        path=path_el.text.strip() if path_el is not None and path_el.text else None,
        parent_id=root.get("parent-folder-id"),
        entries=entries,
    )


def parse_repositories(raw: bytes) -> List[Tuple[str, str]]:
    """``(branch, repository)`` pairs from ``/rest/branches/``, in listing order."""
    root = _parse_xml(raw, "branch list")
    out: List[Tuple[str, str]] = []
    for branch in root.iter():
        if _local(branch.tag) != "branch":
            continue
        branch_name = branch.get("name") or "master"
        for repo in branch:
            repo_name = repo.get("name") or repo.get("id")
            if repo_name and (branch_name, repo_name) not in out:
                out.append((branch_name, repo_name))
    return out


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

    @staticmethod
    def _checked(item_id: str) -> str:
        """IDs go into the request path, so nothing that could leave it — no
        slash, dot, ``?`` or ``%`` — gets through."""
        if not ID_RE.fullmatch(item_id or ""):
            raise HerettoError("Not a Heretto file or folder ID.")
        return item_id

    async def get_file(self, file_id: str) -> HerettoFile:
        return parse_file(await self._get(f"/rest/all-files/{self._checked(file_id)}"))

    async def get_content(self, file_id: str) -> bytes:
        return await self._get(f"/rest/all-files/{self._checked(file_id)}/content")

    async def get_dependencies(self, file_id: str) -> Dict[str, str]:
        return parse_dependencies(
            await self._get(f"/rest/all-files/{self._checked(file_id)}/links/dependencies")
        )

    async def get_folder(self, folder_id: str) -> HerettoFolder:
        return parse_folder(await self._get(f"/rest/all-files/{self._checked(folder_id)}"))

    async def get_repository_root(self, branch: str, repo: str) -> HerettoFolder:
        """A repository's ``documents`` folder — the only path-addressable folder."""
        return parse_folder(await self._get(
            f"/rest/branches/{quote(branch, safe='')}/repositories/{quote(repo, safe='')}/documents/"
        ))

    _repo_root = get_repository_root

    async def list_repositories(self) -> List[Tuple[str, str]]:
        """Every ``(branch, repository)`` the account can see."""
        return parse_repositories(await self._get("/rest/branches/"))

    async def get_ancestors(self, folder: HerettoFolder) -> List[HerettoFolder]:
        """The folders above ``folder``, from its repository's ``documents``
        folder down to its parent; empty for ``documents`` itself.

        One request per level, so callers ask for it only when they jump
        somewhere rather than step into a child.
        """
        chain: List[HerettoFolder] = []
        current = folder
        for _ in range(MAX_PATH_DEPTH):
            if current.is_documents_root or not current.parent_id:
                break
            current = await self.get_folder(current.parent_id)
            chain.append(current)
        return list(reversed(chain))

    async def find_by_name(
        self, query: str, under: str, *,
        max_folders: int = SEARCH_MAX_FOLDERS, max_depth: int = SEARCH_MAX_DEPTH,
        max_matches: int = SEARCH_MAX_MATCHES, time_limit: float = SEARCH_TIME_LIMIT,
    ) -> NameSearch:
        """Files and folders whose names contain ``query``, in folder ``under``
        and every folder below it.

        Heretto has no search that answers API tokens (see the module
        docstring), so this walks the tree a level at a time, a few folders at
        once. It stops at the first limit it reaches and reports
        ``truncated`` — a bounded walk that found nothing is not proof there
        is nothing. When a token-friendly search exists, it replaces this.
        """
        needle = (query or "").strip().lower()
        if not needle:
            raise HerettoError("Enter part of a name to search for.")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + time_limit
        gate = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def load(folder_id: str) -> Optional[HerettoFolder]:
            async with gate:
                try:
                    return await self.get_folder(folder_id)
                except HerettoError as exc:
                    if exc.status_code in (401, 403):
                        raise
                    return None   # one unreadable folder doesn't end the search

        matches: List[NameMatch] = []
        seen = set()
        searched, truncated = 0, False
        level: List[Tuple[str, str]] = [(under, "")]
        for depth in range(max_depth + 1):
            batch = []
            for folder_id, rel in level:
                if folder_id in seen:
                    continue
                if searched + len(batch) >= max_folders:
                    truncated = True
                    break
                seen.add(folder_id)
                batch.append((folder_id, rel))
            remaining = deadline - loop.time()
            if not batch or remaining <= 0:
                truncated = truncated or bool(batch)
                break
            try:
                folders = await asyncio.wait_for(
                    asyncio.gather(*(load(folder_id) for folder_id, _ in batch)), remaining,
                )
            except asyncio.TimeoutError:
                truncated = True
                break
            searched += len(batch)
            next_level: List[Tuple[str, str]] = []
            for (folder_id, rel), folder in zip(batch, folders):
                if folder is None:
                    continue
                for entry in folder.entries:
                    if needle in entry.name.lower():
                        matches.append(NameMatch(entry, folder_id, rel or "/"))
                    if entry.is_folder:
                        next_level.append((entry.id, f"{rel}/{entry.name}"))
            if truncated or len(matches) >= max_matches:
                truncated = truncated or bool(next_level) or len(matches) > max_matches
                break
            level = next_level
            if not level:
                break
        else:
            truncated = bool(level)

        matches.sort(key=lambda m: (
            not m.entry.is_folder, m.entry.name.lower() != needle, m.entry.name.lower(), m.folder_path,
        ))
        return NameSearch(matches[:max_matches], searched, truncated)

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
                    f"It contains: {self._listing(current)}",
                    folder_id=current.id,
                )
            folder_id = next((fid for name, fid in current.folders if name.lower() == target), None)
            if folder_id is None:
                raise HerettoError(
                    f"No folder named {segment!r} in {trail}/. "
                    f"It contains: {self._listing(current)}",
                    folder_id=current.id,
                )
            current = await self.get_folder(folder_id)
            trail += "/" + segment
        raise HerettoError(f"Could not resolve {path!r}.")  # pragma: no cover

    async def resolve_folder(self, branch: str, repo: str, path: str) -> HerettoFolder:
        """The folder a typed path names in one repository.

        The path is relative to the repository's ``documents`` folder
        (``/guides/install``), and may repeat the branch, repository and
        ``documents`` (``master/product/documents/guides/install``). A folder
        ID, or a Heretto URL containing one, opens that folder.
        """
        text = (path or "").strip().replace("\\", "/")
        found = UUID_RE.search(text)
        if found:
            return await self.get_folder(found.group(0).lower())
        parts = [p for p in text.split("/") if p]
        if len(parts) >= 2 and parts[0] == branch and parts[1] == repo:
            parts = parts[2:]
        if parts and parts[0] == "documents":
            parts = parts[1:]
        if len(parts) > MAX_PATH_DEPTH:
            raise HerettoError("That path is deeper than any Heretto folder tree should be.")

        current = await self.get_repository_root(branch, repo)
        trail = f"{branch}/{repo}/documents/"
        for segment in parts:
            target = segment.lower()
            folder_id = next((fid for name, fid in current.folders if name.lower() == target), None)
            if folder_id is None:
                if any(name.lower() == target for name, _ in current.resources):
                    raise HerettoError(
                        f"{segment!r} in {trail} is a file, not a folder. "
                        "Open its folder and select it from the list.",
                        folder_id=current.id,
                    )
                raise HerettoError(
                    f"No folder named {segment!r} in {trail}. It contains: {self._listing(current)}",
                    folder_id=current.id,
                )
            current = await self.get_folder(folder_id)
            trail += segment + "/"
        return current

    @staticmethod
    def _listing(folder: HerettoFolder) -> str:
        names = sorted([n + "/" for n, _ in folder.folders] + [n for n, _ in folder.resources])
        return ", ".join(names[:15]) + (" …" if len(names) > 15 else "") if names else "(nothing)"
