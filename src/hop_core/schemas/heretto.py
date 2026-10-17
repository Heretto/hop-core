"""Schemas for browsing a Heretto CCMS through one of the organization's
Heretto connections (the ``/heretto`` routes behind the file browser)."""

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

FileKind = Literal["folder", "map", "topic", "image", "other"]


class HerettoRepository(BaseModel):
    branch: str
    repository: str


class HerettoEntryInfo(BaseModel):
    """A folder or file in a listing or a search result."""

    id: str
    name: str
    kind: FileKind
    # Heretto's own type for the file (Topic, Map, SiteMap, …), when it gives one.
    type: Optional[str] = None
    mime_type: Optional[str] = None


class HerettoFolderRef(BaseModel):
    id: str
    name: str


class HerettoFolderListing(BaseModel):
    id: str
    name: str
    path: Optional[str] = None
    parent_id: Optional[str] = None
    # ``(branch, repository)`` the folder is in, when its path says.
    branch: Optional[str] = None
    repository: Optional[str] = None
    # The folders above this one, from the repository's ``documents`` folder
    # down; only filled when asked for (``ancestors=true``) or after a jump.
    ancestors: Optional[List[HerettoFolderRef]] = None
    entries: List[HerettoEntryInfo]


class HerettoFolderPathRequest(BaseModel):
    """A typed path within ``branch``/``repository`` — or, with those left
    out, a folder ID, Heretto URL or full repository path on its own."""

    branch: Optional[str] = Field(default=None, min_length=1, max_length=200)
    repository: Optional[str] = Field(default=None, min_length=1, max_length=200)
    path: str = Field(max_length=2000)


class HerettoSearchMatch(HerettoEntryInfo):
    folder_id: str
    # Where the match is, relative to the folder the search started in.
    folder_path: str


class HerettoSearchResponse(BaseModel):
    query: str
    matches: List[HerettoSearchMatch]
    folders_searched: int
    # A limit stopped the walk before it covered every subfolder.
    truncated: bool


class HerettoFileInfo(BaseModel):
    """What a picker shows about a file, and what an app stores after one is chosen."""

    id: str
    name: str
    title: str
    kind: FileKind
    is_map: bool = False
    path: Optional[str] = None
    folder_id: Optional[str] = None
    mime_type: Optional[str] = None
    status: Optional[str] = None
    last_modified: Optional[str] = None   # ISO 8601
    editor_url: Optional[str] = None
    credential_id: UUID
    credential_name: str


class HerettoIdentifierRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=2000)
