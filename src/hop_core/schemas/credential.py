"""Generic credential Pydantic schemas."""

from pydantic import BaseModel
from typing import Optional, Dict, Any
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

    class Config:
        from_attributes = True
