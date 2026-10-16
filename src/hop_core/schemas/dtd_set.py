"""DTD-set Pydantic schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DtdSetSummary(BaseModel):
    """A row of the DTD sets list (and the head of the detail page)."""

    id: str
    name: str
    builtin: bool = False
    is_default: bool = False
    description: str = ""
    # The version apps validate against; null until one processes successfully.
    version_label: Optional[str] = None
    filename: Optional[str] = None
    based_on: Optional[str] = None
    document_type_count: Optional[int] = None
    specialized_count: Optional[int] = None
    # "ready" | "processing" | "failed" — of the set as a whole: processing or
    # failed only while there is no usable version.
    status: str
    warning_count: int = 0
    # The most recent upload, when it is not the version in use.
    latest_version_id: Optional[str] = None
    latest_label: Optional[str] = None
    latest_status: Optional[str] = None
    latest_step: Optional[int] = None
    latest_error: Optional[str] = None
    used_by: int = 0
    updated_at: Optional[datetime] = None


class DtdSetList(BaseModel):
    default_id: str
    max_upload_mb: int
    sets: List[DtdSetSummary]


class DtdSetDefaultUpdate(BaseModel):
    dtd_set_id: str


class StepState(BaseModel):
    key: str
    label: str
    # "done" | "running" | "pending" | "failed"
    state: str
    detail: str = ""


class DtdSetVersionInfo(BaseModel):
    id: str
    label: str
    filename: str
    size_bytes: int
    status: str
    step: int
    error: Optional[str] = None
    is_current: bool = False
    uploaded_by: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    steps: List[StepState] = []


class DocumentTypeInfo(BaseModel):
    name: str
    root: str
    public_id: str
    shell: str
    kind: str
    specializes: Optional[str] = None
    parses: bool = True


class IssueInfo(BaseModel):
    title: str
    detail: str = ""
    file: Optional[str] = None
    line: Optional[int] = None
    severity: str = "warning"


class PackageInfo(BaseModel):
    based_on: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    file_count: Optional[int] = None
    catalog: Optional[str] = None
    public_id_count: Optional[int] = None
    processed_at: Optional[datetime] = None


class AgentRef(BaseModel):
    id: str
    name: str


class DtdSetDetail(DtdSetSummary):
    uploaded_by: Optional[str] = None
    package: PackageInfo
    issues: List[IssueInfo] = []
    document_types: List[DocumentTypeInfo] = []
    agents: List[AgentRef] = []
    versions: List[DtdSetVersionInfo] = []
