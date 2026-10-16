"""DTD sets: an organization's choice of DITA grammar, and getting a validator for it.

Which grammar applies is resolved in order: the agent's own choice, then the
organization default, then the built-in OASIS DITA 1.3 set. A choice that is
not usable (deleted, or with no version that processed successfully) falls
through to the next, so validation never stops because of an upload. A host
app's jobs get the right validator with::

    validator = validator_for(db, organization_id, agent_id=agent.id)

Uploaded packages are stored in the database and unpacked on demand into a
local cache directory (``HOP_DTD_CACHE_DIR``, default under the system temp
directory), so a restart or a second replica only costs an unzip.

Requires the ``dita`` extra (lxml).
"""

import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from hop_core.dita.grammar import DtdSet as Grammar
from hop_core.dita.packages import STEPS, PackageError, PackageReport, index_directory, process_package, unpack
from hop_core.dita.validator import DitaValidator
from hop_core.models.agent import Agent
from hop_core.models.dtd_set import BUILTIN_DTD_SET_ID, AgentDtdSet, DtdSet, DtdSetVersion
from hop_core.models.organization import Organization

logger = logging.getLogger(__name__)

BUILTIN_ID = BUILTIN_DTD_SET_ID
BUILTIN_NAME = "OASIS DITA 1.3"
_DEFAULT_KEY = "default_dtd_set_id"


# ── Organization default and agent choice ─────────────────────────────────────

def organization_default_id(org: Organization) -> str:
    return (org.settings or {}).get(_DEFAULT_KEY) or BUILTIN_ID


def set_organization_default(org: Organization, dtd_set_id: str) -> None:
    # A new dict, so SQLAlchemy sees the JSON column change.
    org.settings = {**(org.settings or {}), _DEFAULT_KEY: dtd_set_id}


def agent_choice(db: Session, agent_id) -> Optional[str]:
    row = db.get(AgentDtdSet, agent_id)
    return row.dtd_set_id if row else None


def set_agent_choice(db: Session, agent_id, dtd_set_id: Optional[str]) -> None:
    row = db.get(AgentDtdSet, agent_id)
    if dtd_set_id is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(AgentDtdSet(agent_id=agent_id, dtd_set_id=dtd_set_id))
    else:
        row.dtd_set_id = dtd_set_id


def get_set(db: Session, organization_id, dtd_set_id: str) -> Optional[DtdSet]:
    try:
        key = UUID(str(dtd_set_id))
    except ValueError:
        return None
    return db.query(DtdSet).filter(DtdSet.id == key, DtdSet.organization_id == organization_id).first()


def current_version(dtd_set: DtdSet) -> Optional[DtdSetVersion]:
    if dtd_set.current_version_id is None:
        return None
    return next((v for v in dtd_set.versions if v.id == dtd_set.current_version_id), None)


def is_usable(db: Session, organization_id, dtd_set_id: str) -> bool:
    """Built in, or an uploaded set with a version that processed successfully."""
    if dtd_set_id == BUILTIN_ID:
        return True
    dtd_set = get_set(db, organization_id, dtd_set_id)
    return dtd_set is not None and current_version(dtd_set) is not None


def resolve_id(db: Session, organization_id, agent_id=None) -> str:
    """The set that applies: the agent's choice, the organization default, or built in."""
    org = db.get(Organization, organization_id)
    candidates = []
    if agent_id is not None:
        choice = agent_choice(db, agent_id)
        if choice:
            candidates.append(choice)
    if org is not None:
        candidates.append(organization_default_id(org))
    for candidate in candidates:
        if is_usable(db, organization_id, candidate):
            return candidate
    return BUILTIN_ID


def agents_using(db: Session, organization_id, dtd_set_id: str) -> List[Agent]:
    """Agents that choose this set themselves (not the ones following the default)."""
    return (
        db.query(Agent)
        .join(AgentDtdSet, AgentDtdSet.agent_id == Agent.id)
        .filter(Agent.organization_id == organization_id, AgentDtdSet.dtd_set_id == str(dtd_set_id))
        .order_by(Agent.name)
        .all()
    )


# ── Grammar on disk ───────────────────────────────────────────────────────────

def _cache_root() -> Path:
    root = Path(os.environ.get("HOP_DTD_CACHE_DIR") or Path(tempfile.gettempdir()) / "hop-core-dtd-sets")
    root.mkdir(parents=True, exist_ok=True)
    return root


_unpack_lock = threading.Lock()


def unpacked_dir(version: DtdSetVersion) -> Path:
    """The version's grammar on local disk, unzipping the stored archive if needed."""
    target = _cache_root() / str(version.id)
    if (target / ".complete").exists():
        return target
    with _unpack_lock:
        if not (target / ".complete").exists():
            shutil.rmtree(target, ignore_errors=True)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(version.archive)
            try:
                unpack(Path(tmp.name), target)
            finally:
                os.unlink(tmp.name)
            (target / ".complete").touch()
    return target


def forget_unpacked(version_id) -> None:
    shutil.rmtree(_cache_root() / str(version_id), ignore_errors=True)


def grammar_for_version(version: DtdSetVersion, name: str) -> Grammar:
    report = PackageReport.from_dict(version.report or {})
    return report.dtd_set(unpacked_dir(version), name=name)


@lru_cache(maxsize=1)
def builtin_report() -> PackageReport:
    """The bundled grammar indexed like an upload, for listing its document types."""
    return index_directory(Grammar.oasis_dita_1_3().root / "dtd")


def validator_for(db: Session, organization_id, agent_id=None) -> DitaValidator:
    """A validator for the grammar that applies to this organization or agent."""
    dtd_set_id = resolve_id(db, organization_id, agent_id)
    if dtd_set_id == BUILTIN_ID:
        return DitaValidator()
    dtd_set = get_set(db, organization_id, dtd_set_id)
    version = current_version(dtd_set)
    try:
        return DitaValidator(dtd_set=grammar_for_version(version, dtd_set.name))
    except Exception:
        logger.exception("Could not load DTD set %s; falling back to the built-in set", dtd_set_id)
        return DitaValidator()


# ── Processing uploads ────────────────────────────────────────────────────────

def process_version(version_id, session_factory=None) -> None:
    """Process an uploaded version in its own session, recording progress.

    Runs in a worker thread after the upload request has returned. The set's
    current version moves to this one only if it succeeds.
    """
    if session_factory is None:
        from hop_core.db import get_session_factory
        session_factory = get_session_factory()
    db = session_factory()
    try:
        version = db.get(DtdSetVersion, version_id)
        if version is None:
            return
        details: List[str] = list(version.step_details or [])

        def progress(step: int, detail: str) -> None:
            while len(details) <= step:
                details.append("")
            details[step] = detail
            version.step = step
            version.step_details = list(details)
            db.commit()

        with tempfile.TemporaryDirectory() as work:
            archive = Path(work) / "upload.zip"
            archive.write_bytes(version.archive)
            target = _cache_root() / str(version.id)
            shutil.rmtree(target, ignore_errors=True)
            try:
                report = process_package(archive, target, progress)
            except PackageError as exc:
                version.status = "failed"
                version.step = exc.step
                version.error = exc.message
                version.report = exc.report.to_dict() if exc.report else None
                version.processed_at = datetime.now(timezone.utc)
                shutil.rmtree(target, ignore_errors=True)
                db.commit()
                return
            except Exception:
                logger.exception("Processing DTD set version %s failed", version_id)
                version.status = "failed"
                version.error = "Processing stopped on an unexpected error. Try uploading again."
                version.processed_at = datetime.now(timezone.utc)
                shutil.rmtree(target, ignore_errors=True)
                db.commit()
                return
            (target / ".complete").touch()

        version.status = "ready"
        version.report = report.to_dict()
        version.error = None
        version.processed_at = datetime.now(timezone.utc)
        version.dtd_set.current_version_id = version.id
        version.dtd_set.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def recover_interrupted(db: Session) -> int:
    """Mark uploads that were mid-processing when the server stopped as failed."""
    stuck = db.query(DtdSetVersion).filter(DtdSetVersion.status == "processing").all()
    for version in stuck:
        version.status = "failed"
        version.error = "Processing was interrupted when the server restarted. Upload the zip again."
        version.processed_at = datetime.now(timezone.utc)
    if stuck:
        db.commit()
    return len(stuck)


def step_states(version: DtdSetVersion) -> List[dict]:
    """The six steps as the upload dialog shows them."""
    details = list(version.step_details or [])
    out = []
    for index, (key, label) in enumerate(STEPS):
        if version.status == "ready" or index < version.step:
            state = "done"
        elif index == version.step:
            state = "failed" if version.status == "failed" else "running"
        else:
            state = "pending"
        detail = details[index] if index < len(details) else ""
        if state == "failed":
            detail = version.error or detail
        out.append({"key": key, "label": label, "state": state, "detail": detail})
    return out
