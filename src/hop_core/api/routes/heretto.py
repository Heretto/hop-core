"""Browsing a Heretto CCMS through the organization's Heretto connections.

These routes back the hop-ui file browser and Heretto file field: list the
connections and repositories, open folders, find files by name, and describe
a file — by ID, Heretto URL or repository path. Everything is read-only and
goes through one of the caller's organization's Heretto credentials.

A Heretto failure answers 400 with ``detail = {message, reason, folder_id}``:
``reason`` is ``credentials`` when Heretto rejected the connection,
``not_found`` for a missing file or folder, otherwise ``error``; ``folder_id``
is the folder a typed path stopped in, when there is one.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from hop_core.agents.references import heretto_connections, heretto_credential
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.core.rate_limit import limiter
from hop_core.core.security import decrypt_credentials
from hop_core.db import get_db
from hop_core.heretto import HerettoClient, HerettoError
from hop_core.heretto.client import HerettoFile, HerettoFolder
from hop_core.models.credential import Credential
from hop_core.schemas.agent import HerettoConnection
from hop_core.schemas.heretto import (
    HerettoEntryInfo,
    HerettoFileInfo,
    HerettoFolderListing,
    HerettoFolderPathRequest,
    HerettoFolderRef,
    HerettoIdentifierRequest,
    HerettoRepository,
    HerettoSearchMatch,
    HerettoSearchResponse,
)

router = APIRouter(prefix="/heretto")


# ── helpers ───────────────────────────────────────────────────────────────


def _credential(credential_id: UUID, context: CurrentUserContext, db: Session) -> Credential:
    credential = heretto_credential(credential_id, context.organization_id, db)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Heretto connection not found")
    return credential


def _failure(exc: HerettoError) -> HTTPException:
    reason = {401: "credentials", 403: "credentials", 404: "not_found"}.get(exc.status_code, "error")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"message": exc.message, "reason": reason, "folder_id": exc.folder_id},
    )


@asynccontextmanager
async def _client(credential: Credential) -> AsyncIterator[HerettoClient]:
    """A client for the credential; any Heretto failure inside becomes a 400."""
    try:
        try:
            payload = decrypt_credentials(credential.encrypted_data)
        except Exception:
            raise HerettoError("This Heretto connection's details can't be read. Edit it under Credentials.")
        async with HerettoClient.from_payload(payload) as client:
            yield client
    except HerettoError as exc:
        raise _failure(exc)


def _entry(entry) -> HerettoEntryInfo:
    return HerettoEntryInfo(
        id=entry.id, name=entry.name, kind=entry.kind,
        type=entry.heretto_type, mime_type=entry.mime_type,
    )


def _listing(folder: HerettoFolder, ancestors: Optional[List[HerettoFolder]] = None) -> HerettoFolderListing:
    top = ancestors[0] if ancestors else folder
    branch, repository = folder.repository or top.repository or (None, None)
    entries = sorted(folder.entries, key=lambda e: (not e.is_folder, e.name.lower()))
    return HerettoFolderListing(
        id=folder.id,
        name=folder.name or "",
        path=folder.path,
        parent_id=None if folder.is_documents_root else folder.parent_id,
        branch=branch,
        repository=repository,
        ancestors=None if ancestors is None else [
            HerettoFolderRef(id=a.id, name=a.name or "") for a in ancestors
        ],
        entries=[_entry(e) for e in entries],
    )


def _iso(value: Optional[str]) -> Optional[str]:
    """Heretto timestamps are epoch milliseconds."""
    if value and value.isdigit():
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    return value or None


def _file_info(file: HerettoFile, client: HerettoClient, credential: Credential) -> HerettoFileInfo:
    file_id = file.id.lower()
    kind = file.kind
    return HerettoFileInfo(
        id=file_id,
        name=file.name,
        title=file.display_title,
        kind=kind,
        is_map=file.is_map,
        path=file.path,
        folder_id=file.folder_id,
        mime_type=file.mime_type,
        status=file.metadata.get("status") or None,
        last_modified=_iso(file.last_modified),
        editor_url=f"{client.base_url}/#/editor/{file_id}" if kind in ("map", "topic") else None,
        credential_id=credential.id,
        credential_name=credential.name,
    )


# ── routes ────────────────────────────────────────────────────────────────


@router.get("/connections", response_model=List[HerettoConnection])
async def list_connections(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """The organization's Heretto connections, by name."""
    out = []
    for credential in heretto_connections(context.organization_id, db):
        try:
            server_url = str(decrypt_credentials(credential.encrypted_data).get("server_url") or "")
        except Exception:
            server_url = ""
        out.append(HerettoConnection(id=credential.id, name=credential.name, server_url=server_url))
    return out


@router.get("/{credential_id}/repositories", response_model=List[HerettoRepository])
@limiter.limit("60/minute")
async def list_repositories(
    request: Request,
    credential_id: UUID,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Every branch and repository the connection's account can see."""
    async with _client(_credential(credential_id, context, db)) as client:
        pairs = await client.list_repositories()
    return [HerettoRepository(branch=b, repository=r) for b, r in pairs]


@router.get("/{credential_id}/repositories/{branch}/{repository}", response_model=HerettoFolderListing)
@limiter.limit("120/minute")
async def open_repository(
    request: Request,
    credential_id: UUID,
    branch: str,
    repository: str,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """A repository's ``documents`` folder: where browsing starts."""
    async with _client(_credential(credential_id, context, db)) as client:
        folder = await client.get_repository_root(branch, repository)
    listing = _listing(folder, [])
    listing.branch, listing.repository = listing.branch or branch, listing.repository or repository
    return listing


@router.get("/{credential_id}/folders/{folder_id}", response_model=HerettoFolderListing)
@limiter.limit("120/minute")
async def open_folder(
    request: Request,
    credential_id: UUID,
    folder_id: str,
    ancestors: bool = Query(False, description="Include the folders above it, for breadcrumbs"),
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """A folder's subfolders and files, folders first."""
    async with _client(_credential(credential_id, context, db)) as client:
        folder = await client.get_folder(folder_id)
        chain = await client.get_ancestors(folder) if ancestors else None
    return _listing(folder, chain)


@router.post("/{credential_id}/folders/resolve", response_model=HerettoFolderListing)
@limiter.limit("30/minute")
async def resolve_folder(
    request: Request,
    credential_id: UUID,
    body: HerettoFolderPathRequest,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """The folder a typed or pasted path names in a repository, with its ancestors."""
    async with _client(_credential(credential_id, context, db)) as client:
        folder = await client.resolve_folder(body.branch, body.repository, body.path)
        chain = await client.get_ancestors(folder)
    return _listing(folder, chain)


@router.get("/{credential_id}/folders/{folder_id}/search", response_model=HerettoSearchResponse)
@limiter.limit("20/minute")
async def search_folder(
    request: Request,
    credential_id: UUID,
    folder_id: str,
    q: str = Query(..., min_length=1, max_length=200),
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Files and folders whose names contain ``q``, in the folder and below.

    Bounded: ``truncated`` says a limit stopped the search early.
    """
    async with _client(_credential(credential_id, context, db)) as client:
        found = await client.find_by_name(q, folder_id)
    return HerettoSearchResponse(
        query=q.strip(),
        matches=[
            HerettoSearchMatch(**_entry(m.entry).model_dump(), folder_id=m.folder_id, folder_path=m.folder_path)
            for m in found.matches
        ],
        folders_searched=found.folders_searched,
        truncated=found.truncated,
    )


@router.get("/{credential_id}/files/{file_id}", response_model=HerettoFileInfo)
@limiter.limit("120/minute")
async def get_file(
    request: Request,
    credential_id: UUID,
    file_id: str,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """A file's title, location, type and dates."""
    credential = _credential(credential_id, context, db)
    async with _client(credential) as client:
        file = await client.get_file(file_id)
        return _file_info(file, client, credential)


@router.post("/{credential_id}/resolve", response_model=HerettoFileInfo)
@limiter.limit("30/minute")
async def resolve_file(
    request: Request,
    credential_id: UUID,
    body: HerettoIdentifierRequest,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """The file a pasted file ID, Heretto URL or repository path names."""
    credential = _credential(credential_id, context, db)
    async with _client(credential) as client:
        file = await client.resolve(body.identifier)
        return _file_info(file, client, credential)
