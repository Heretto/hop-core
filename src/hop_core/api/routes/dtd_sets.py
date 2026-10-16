"""DTD-set routes: upload an organization's own DITA grammar, track its
processing, choose the organization default, and manage versions.

Reading is open to every member (the agent editor lists the sets); changing
anything requires an organization admin. Mounted with
``create_hop_app(include_dtd_sets_router=True)``; needs the ``dita`` extra.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from hop_core import dtd_sets
from hop_core.api.dependencies import (
    CurrentUserContext,
    get_current_active_user_with_org,
    require_org_admin,
)
from hop_core.config import get_settings
from hop_core.db import get_db
from hop_core.dita.packages import PackageReport
from hop_core.models.dtd_set import DtdSet, DtdSetVersion
from hop_core.models.organization import Organization
from hop_core.schemas.dtd_set import (
    AgentRef,
    DtdSetDefaultUpdate,
    DtdSetDetail,
    DtdSetList,
    DtdSetSummary,
    DtdSetVersionInfo,
    PackageInfo,
)

router = APIRouter(prefix="/dtd-sets")

_CHUNK = 1024 * 1024


# ── Serialization ─────────────────────────────────────────────────────────────

def _report(version: Optional[DtdSetVersion]) -> PackageReport:
    return PackageReport.from_dict(version.report if version is not None and version.report else {})


def _counts(report: PackageReport):
    if not report.document_types:
        return None, None
    return len(report.document_types), sum(1 for d in report.document_types if d.kind == "specialized")


def _builtin_summary(db: Session, org: Organization) -> DtdSetSummary:
    report = dtd_sets.builtin_report()
    count, specialized = _counts(report)
    return DtdSetSummary(
        id=dtd_sets.BUILTIN_ID, name=dtd_sets.BUILTIN_NAME, builtin=True,
        is_default=dtd_sets.organization_default_id(org) == dtd_sets.BUILTIN_ID,
        description="The OASIS DITA 1.3 standard, included with Hop.",
        based_on="OASIS standard", document_type_count=count, specialized_count=specialized,
        status="ready", used_by=len(dtd_sets.agents_using(db, org.id, dtd_sets.BUILTIN_ID)),
    )


def _summary(db: Session, org: Organization, dtd_set: DtdSet) -> DtdSetSummary:
    current = dtd_sets.current_version(dtd_set)
    latest = dtd_set.versions[0] if dtd_set.versions else None
    shown = current or latest
    report = _report(current)
    count, specialized = _counts(report)
    if current is not None:
        set_status = "ready"
    else:
        set_status = latest.status if latest is not None else "failed"
    summary = DtdSetSummary(
        id=str(dtd_set.id), name=dtd_set.name, description=dtd_set.description or "",
        is_default=dtd_sets.organization_default_id(org) == str(dtd_set.id),
        version_label=shown.label if shown else None,
        filename=shown.filename if shown else None,
        based_on=report.based_on, document_type_count=count, specialized_count=specialized,
        status=set_status, warning_count=len(report.issues),
        used_by=len(dtd_sets.agents_using(db, org.id, str(dtd_set.id))),
        updated_at=(current.processed_at if current else None) or dtd_set.updated_at,
    )
    if latest is not None and latest is not current:
        summary.latest_version_id = str(latest.id)
        summary.latest_label = latest.label
        summary.latest_status = latest.status
        summary.latest_step = latest.step
        summary.latest_error = latest.error
    return summary


def _version_info(dtd_set: DtdSet, version: DtdSetVersion) -> DtdSetVersionInfo:
    return DtdSetVersionInfo(
        id=str(version.id), label=version.label, filename=version.filename,
        size_bytes=version.size_bytes, status=version.status, step=version.step,
        error=version.error, is_current=version.id == dtd_set.current_version_id,
        uploaded_by=version.uploaded_by, created_at=version.created_at,
        processed_at=version.processed_at, steps=dtd_sets.step_states(version),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _org(db: Session, context: CurrentUserContext) -> Organization:
    return db.get(Organization, context.organization_id)


def _owned_set(db: Session, context: CurrentUserContext, dtd_set_id: str) -> DtdSet:
    dtd_set = dtd_sets.get_set(db, context.organization_id, dtd_set_id)
    if dtd_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DTD set not found")
    return dtd_set


def _owned_version(dtd_set: DtdSet, version_id: str) -> DtdSetVersion:
    version = next((v for v in dtd_set.versions if str(v.id) == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version


async def _read_zip(upload: UploadFile) -> bytes:
    """The upload's bytes, refusing anything over the size limit as it streams."""
    limit = get_settings().dtd_upload_max_mb * 1024 * 1024
    if not (upload.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a .zip file.")
    data = bytearray()
    while chunk := await upload.read(_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"The zip is larger than {get_settings().dtd_upload_max_mb} MB.",
            )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The upload is empty.")
    return bytes(data)


def _new_version(dtd_set: DtdSet, label: str, upload: UploadFile, data: bytes, user_email: str) -> DtdSetVersion:
    version = DtdSetVersion(
        label=(label or "").strip() or "v1.0", filename=upload.filename or "dtds.zip",
        size_bytes=len(data), archive=data, status="processing", step=0, step_details=[],
        uploaded_by=user_email,
    )
    dtd_set.versions.append(version)
    dtd_set.updated_at = datetime.now(timezone.utc)
    return version


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=DtdSetList)
async def list_dtd_sets(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    org = _org(db, context)
    rows = db.query(DtdSet).options(selectinload(DtdSet.versions)).filter(
        DtdSet.organization_id == context.organization_id).order_by(DtdSet.name).all()
    default_id = dtd_sets.organization_default_id(org)
    if default_id != dtd_sets.BUILTIN_ID and not dtd_sets.is_usable(db, org.id, default_id):
        default_id = dtd_sets.BUILTIN_ID
    summaries = [_summary(db, org, r) for r in rows]
    builtin = _builtin_summary(db, org)
    # The default first, then the built-in set, then the rest by name.
    ordered = sorted([*summaries, builtin], key=lambda s: (not s.is_default, not s.builtin, s.name.lower()))
    return DtdSetList(default_id=default_id, max_upload_mb=get_settings().dtd_upload_max_mb, sets=ordered)


@router.put("/default", response_model=DtdSetList)
async def set_default(
    body: DtdSetDefaultUpdate,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    if not dtd_sets.is_usable(db, context.organization_id, body.dtd_set_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the built-in set or one that finished processing can be the default.",
        )
    dtd_sets.set_organization_default(_org(db, context), body.dtd_set_id)
    db.commit()
    return await list_dtd_sets(context, db)


@router.post("", response_model=DtdSetVersionInfo, status_code=status.HTTP_202_ACCEPTED)
async def upload_dtd_set(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=255),
    version: str = Form("v1.0", max_length=64),
    description: str = Form("", max_length=2000),
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    """Upload a new set. Processing continues after this returns; poll the
    version for progress."""
    data = await _read_zip(file)
    dtd_set = DtdSet(organization_id=context.organization_id, name=name.strip(),
                     description=description.strip(), created_by=context.user.email)
    db.add(dtd_set)
    new = _new_version(dtd_set, version, file, data, context.user.email)
    db.commit()
    background.add_task(dtd_sets.process_version, new.id)
    db.refresh(dtd_set)
    return _version_info(dtd_set, new)


@router.post("/{dtd_set_id}/versions", response_model=DtdSetVersionInfo, status_code=status.HTTP_202_ACCEPTED)
async def upload_version(
    dtd_set_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    version: str = Form(..., min_length=1, max_length=64),
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    """Upload a new version. Apps keep using the current one until it is ready."""
    dtd_set = _owned_set(db, context, dtd_set_id)
    if any(v.status == "processing" for v in dtd_set.versions):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A version of this set is still processing.")
    data = await _read_zip(file)
    new = _new_version(dtd_set, version, file, data, context.user.email)
    db.commit()
    background.add_task(dtd_sets.process_version, new.id)
    db.refresh(dtd_set)
    return _version_info(dtd_set, new)


@router.get("/{dtd_set_id}", response_model=DtdSetDetail)
async def get_dtd_set(
    dtd_set_id: str,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    org = _org(db, context)
    if dtd_set_id == dtd_sets.BUILTIN_ID:
        summary = _builtin_summary(db, org)
        report = dtd_sets.builtin_report()
        return DtdSetDetail(
            **summary.model_dump(),
            package=PackageInfo(based_on="OASIS DITA 1.3", file_count=report.file_count,
                                catalog=report.catalog, public_id_count=report.public_id_count),
            document_types=[d.__dict__ for d in report.document_types],
            agents=[AgentRef(id=str(a.id), name=a.name)
                    for a in dtd_sets.agents_using(db, org.id, dtd_sets.BUILTIN_ID)],
        )

    dtd_set = _owned_set(db, context, dtd_set_id)
    summary = _summary(db, org, dtd_set)
    current = dtd_sets.current_version(dtd_set)
    shown = current or (dtd_set.versions[0] if dtd_set.versions else None)
    report = _report(shown)
    return DtdSetDetail(
        **summary.model_dump(),
        uploaded_by=shown.uploaded_by if shown else None,
        package=PackageInfo(
            based_on=report.based_on, filename=shown.filename if shown else None,
            size_bytes=shown.size_bytes if shown else None, file_count=report.file_count or None,
            catalog=report.catalog, public_id_count=report.public_id_count or None,
            processed_at=shown.processed_at if shown else None,
        ),
        issues=[i.__dict__ for i in report.issues],
        document_types=[d.__dict__ for d in report.document_types],
        agents=[AgentRef(id=str(a.id), name=a.name) for a in dtd_sets.agents_using(db, org.id, str(dtd_set.id))],
        versions=[_version_info(dtd_set, v) for v in dtd_set.versions],
    )


@router.get("/{dtd_set_id}/versions/{version_id}", response_model=DtdSetVersionInfo)
async def get_version(
    dtd_set_id: str,
    version_id: str,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """A version's processing state — what the upload dialog polls."""
    dtd_set = _owned_set(db, context, dtd_set_id)
    return _version_info(dtd_set, _owned_version(dtd_set, version_id))


@router.post("/{dtd_set_id}/versions/{version_id}/restore", response_model=DtdSetDetail)
async def restore_version(
    dtd_set_id: str,
    version_id: str,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    """Make an earlier version the one apps validate against."""
    dtd_set = _owned_set(db, context, dtd_set_id)
    version = _owned_version(dtd_set, version_id)
    if version.status != "ready":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only a version that finished processing can be restored.")
    dtd_set.current_version_id = version.id
    dtd_set.updated_at = datetime.now(timezone.utc)
    db.commit()
    return await get_dtd_set(dtd_set_id, context, db)


@router.get("/{dtd_set_id}/versions/{version_id}/download")
async def download_version(
    dtd_set_id: str,
    version_id: str,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    dtd_set = _owned_set(db, context, dtd_set_id)
    version = _owned_version(dtd_set, version_id)
    safe_name = (version.filename or "dtds.zip").replace('"', "")
    return Response(content=version.archive, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe_name}"'})


@router.delete("/{dtd_set_id}")
async def delete_dtd_set(
    dtd_set_id: str,
    context: CurrentUserContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    """Delete a set nothing relies on: not the default, chosen by no agent."""
    org = _org(db, context)
    dtd_set = _owned_set(db, context, dtd_set_id)
    if dtd_sets.organization_default_id(org) == str(dtd_set.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This is the organization default. Choose a different default first.")
    agents = dtd_sets.agents_using(db, org.id, str(dtd_set.id))
    if agents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(agents)} agent(s) use this set. Move them to another set first.",
        )
    version_ids = [v.id for v in dtd_set.versions]
    db.delete(dtd_set)
    db.commit()
    for version_id in version_ids:
        dtd_sets.forget_unpacked(version_id)
    return {"message": "DTD set deleted"}
