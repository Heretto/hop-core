"""Generic credential Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


class CredentialCreate(BaseModel):
    type: str
    name: str
    credentials: Dict[str, Any]


class CredentialUpdate(BaseModel):
    name: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None


class CredentialResponse(BaseModel):
    id: UUID
    type: str
    name: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Non-secret field values, drawn from the type's registered spec so a key
    # the spec does not describe is never echoed back. Empty for a type with
    # no spec.
    values: Dict[str, Any] = Field(default_factory=dict)
    # Which secret fields hold a value, so a form can say "leave blank to
    # keep" without disclosing any part of the secret itself.
    secrets_set: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True
