"""Turning a Heretto reference into text an agent can use.

A reference names one file. A topic is read as itself; a map is read as the
topics it links to, in map order, nested under the map's title and following
submaps — a map is a collection of links, and whoever picks one means the
content it collects.

:class:`ReferenceContentSource` is the seam the runner calls. It reads
through a :class:`ReferenceCache`, so content that is included in every run
is not refetched every run. That is also where smarter caching belongs: a
cache that stores a compressed digest of a large reference in place of the
full text slots in without the runner knowing.
"""

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional, Protocol, Tuple

from hop_core.heretto.client import HerettoClient, HerettoError, HerettoFile
from hop_core.heretto.text import _numeric_entities, dita_to_text

logger = logging.getLogger(__name__)

# A map can link to hundreds of topics; these keep one reference from
# swallowing a run. Hitting one is reported in the text, never silent.
MAX_TOPICS = 300
MAX_MAP_DEPTH = 5
MAX_CHARS = 200_000
CONCURRENT_FETCHES = 6
DEFAULT_CACHE_TTL = 600.0  # seconds

# Map elements that point at content (navigation and glossary references).
_TOPICREFS = {
    "topicref", "mapref", "chapter", "part", "appendix", "appendices", "notices",
    "glossref", "keydef", "topicsetref", "topicset", "anchorref",
    "learningObject", "learningGroup", "learningContentRef", "learningOverviewRef",
    "learningSummaryRef", "learningPlanRef",
}
_NOT_CONTENT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip",
                ".ditaval", ".css", ".js", ".json", ".mp4", ".mp3")


@dataclass
class ReferenceContent:
    """What a reference reads as."""

    file_id: str
    title: str
    text: str
    topic_count: int = 1
    # Shown to the model alongside the text, so it knows what it is missing.
    notes: List[str] = field(default_factory=list)
    fetched_at: float = field(default_factory=time.time)

    def as_prompt_text(self) -> str:
        if not self.notes:
            return self.text
        return self.text + "\n\n" + "\n".join(f"_Note: {n}_" for n in self.notes)


class ReferenceCache(Protocol):
    """Where read references are kept between runs. Keys are
    ``(credential_id, file_id)``."""

    def get(self, key: Tuple[str, str]) -> Optional[ReferenceContent]: ...

    def set(self, key: Tuple[str, str], value: ReferenceContent) -> None: ...


class TTLReferenceCache:
    """In-process cache that forgets entries after ``ttl`` seconds.

    Per process, so each worker warms its own; good enough to stop a style
    guide being refetched on every message of a test chat.
    """

    def __init__(self, ttl: float = DEFAULT_CACHE_TTL, max_entries: int = 256):
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: Dict[Tuple[str, str], ReferenceContent] = {}

    def get(self, key):
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.time() - entry.fetched_at > self.ttl:
            self._entries.pop(key, None)
            return None
        return entry

    def set(self, key, value):
        if len(self._entries) >= self.max_entries:
            oldest = min(self._entries, key=lambda k: self._entries[k].fetched_at)
            self._entries.pop(oldest, None)
        self._entries[key] = value

    def clear(self) -> None:
        self._entries.clear()


# Shared by default so the cache outlives a single request.
default_cache = TTLReferenceCache()


def _local(tag) -> str:
    return tag.split("}", 1)[1] if isinstance(tag, str) and "}" in tag else (tag if isinstance(tag, str) else "")


@dataclass
class _Link:
    href: str
    depth: int
    is_map: bool


def _map_links(map_xml: bytes) -> Tuple[Optional[str], List[_Link]]:
    """The map's title and its content links, in document order."""
    root = ET.fromstring(_numeric_entities(map_xml.decode("utf-8", errors="replace")))
    title = None
    for child in root:
        if _local(child.tag) == "title":
            title = " ".join("".join(child.itertext()).split()) or None
    if title is None:
        title = root.get("title")

    links: List[_Link] = []

    def walk(el: ET.Element, depth: int) -> None:
        for child in el:
            name = _local(child.tag)
            if name not in _TOPICREFS:
                continue
            href = (child.get("href") or "").split("#", 1)[0].strip()
            scope = child.get("scope") or ""
            fmt = (child.get("format") or "").lower()
            if href and scope not in ("external", "peer") and not href.lower().endswith(_NOT_CONTENT) \
                    and fmt in ("", "dita", "ditamap"):
                is_map = fmt == "ditamap" or href.lower().endswith((".ditamap", ".bookmap")) or name == "mapref"
                links.append(_Link(href, depth, is_map))
            walk(child, depth + 1)

    walk(root, 0)
    return title, links


def _lookup(dependencies: Dict[str, str], href: str) -> Optional[str]:
    href = href[2:] if href.startswith("./") else href
    return dependencies.get(href) or dependencies.get(href.rsplit("/", 1)[-1])


async def read_file(client: HerettoClient, file: HerettoFile) -> ReferenceContent:
    """Read one file as a reference — a topic as itself, a map as its topics."""
    if not file.is_map:
        title, text = dita_to_text(await client.get_content(file.id), heading_level=1)
        return ReferenceContent(file.id, file.title or title or file.display_title, text)
    return await _read_map(client, file)


async def _read_map(client: HerettoClient, file: HerettoFile) -> ReferenceContent:
    notes: List[str] = []
    seen: set = {file.id}
    # (heading level, file id) in output order; maps contribute a heading only.
    order: List[Tuple[int, str, Optional[str]]] = []

    async def expand(map_id: str, map_xml: bytes, level: int, map_depth: int) -> None:
        try:
            _, links = _map_links(map_xml)
        except ET.ParseError as exc:
            notes.append(f"A map could not be read and was skipped: {exc}")
            return
        dependencies = await client.get_dependencies(map_id)
        for link in links:
            if len([o for o in order if o[1]]) >= MAX_TOPICS:
                notes.append(f"Only the first {MAX_TOPICS} topics were included.")
                return
            target = _lookup(dependencies, link.href)
            if target is None:
                notes.append(f"Could not find the file for link {link.href!r}.")
                continue
            if target in seen:
                continue
            seen.add(target)
            if link.is_map:
                if map_depth + 1 > MAX_MAP_DEPTH:
                    notes.append(f"Submaps nested deeper than {MAX_MAP_DEPTH} levels were left out.")
                    continue
                submap_xml = await client.get_content(target)
                try:
                    submap_title, _ = _map_links(submap_xml)
                except ET.ParseError:
                    submap_title = None
                if submap_title:
                    order.append((level + link.depth, "", submap_title))
                await expand(target, submap_xml, level + link.depth + 1, map_depth + 1)
            else:
                order.append((level + link.depth, target, None))

    map_xml = await client.get_content(file.id)
    try:
        map_title, _ = _map_links(map_xml)
    except ET.ParseError as exc:
        raise HerettoError(f"The map could not be read: {exc}") from exc
    title = file.title or map_title or file.display_title
    await expand(file.id, map_xml, 2, 0)

    semaphore = asyncio.Semaphore(CONCURRENT_FETCHES)

    async def fetch(file_id: str, level: int) -> str:
        async with semaphore:
            try:
                _, text = dita_to_text(await client.get_content(file_id), heading_level=min(level, 6))
                return text
            except HerettoError as exc:
                notes.append(f"A linked topic could not be read ({exc.message}).")
                return ""

    bodies = await asyncio.gather(*[
        fetch(fid, lvl) if fid else _heading(lvl, heading)
        for lvl, fid, heading in order
    ])
    parts = [f"# {title}"] + [b for b in bodies if b]
    text, truncated = _cap("\n\n".join(parts))
    if truncated:
        notes.append(f"The map's content was cut off at {MAX_CHARS:,} characters.")
    return ReferenceContent(
        file.id, title, text,
        topic_count=sum(1 for o in order if o[1]),
        notes=list(dict.fromkeys(notes)),  # a limit hit in nested maps reports once
    )


async def _heading(level: int, text: Optional[str]) -> str:
    return "#" * max(1, min(level, 6)) + " " + (text or "")


def _cap(text: str) -> Tuple[str, bool]:
    if len(text) <= MAX_CHARS:
        return text, False
    return text[:MAX_CHARS].rsplit("\n", 1)[0], True


CredentialLoader = Callable[[str], Awaitable[dict]]


class ReferenceContentSource:
    """Reads Heretto references for a run, through a cache.

    ``load_credential`` returns the decrypted payload of a Heretto
    credential by ID; the host's database session lives behind it, so this
    class carries none.
    """

    def __init__(self, load_credential: CredentialLoader,
                 cache: Optional[ReferenceCache] = None,
                 client_factory: Optional[Callable[[dict], HerettoClient]] = None):
        self.load_credential = load_credential
        self.cache = cache if cache is not None else default_cache
        # Looked up here rather than as a default argument, so a replacement
        # installed on HerettoClient (a host's subclass, a test fake) is used.
        self.client_factory = client_factory or HerettoClient.from_payload

    async def read(self, credential_id: str, file_id: str) -> ReferenceContent:
        key = (str(credential_id), str(file_id))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        payload = await self.load_credential(str(credential_id))
        async with self.client_factory(payload) as client:
            file = await client.get_file(str(file_id))
            content = await read_file(client, file)
        content.text, truncated = _cap(content.text)
        if truncated and not any("cut off" in n for n in content.notes):
            content.notes.append(f"The content was cut off at {MAX_CHARS:,} characters.")
        self.cache.set(key, content)
        return content
