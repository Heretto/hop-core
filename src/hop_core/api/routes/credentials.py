"""Generic credential CRUD routes.

Type-specific routes (Jira, Heretto, AI test endpoints) are provided
by the host application.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.models.credential import Credential
from hop_core.schemas.credential import CredentialCreate, CredentialUpdate, CredentialResponse
from hop_core.api.dependencies import get_current_active_user
from hop_core.core.security import encrypt_credentials, decrypt_credentials

router = APIRouter(prefix="/credentials")


def mask_secret(value: str) -> str:
    """Mask a secret string, showing only first 4 and last 4 characters."""
    if not value or len(value) <= 8:
        return "*" * len(value) if value else ""
    return value[:4] + "*" * min(len(value) - 8, 20) + value[-4:]


@router.get("", response_model=List[CredentialResponse])
async def list_credentials(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.current_organization_id:
        return []
    credentials = db.query(Credential).filter(
        Credential.organization_id == current_user.current_organization_id,
    ).all()
    return credentials


@router.post("", response_model=CredentialResponse)
async def create_credential(
    credential_data: CredentialCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be part of an organization to create credentials",
        )

    existing = db.query(Credential).filter(
        Credential.organization_id == current_user.current_organization_id,
        Credential.type == credential_data.type,
        Credential.name == credential_data.name,
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential with this name already exists",
        )

    encrypted_data = encrypt_credentials(credential_data.credentials)

    new_credential = Credential(
        user_id=current_user.id,
        organization_id=current_user.current_organization_id,
        type=credential_data.type,
        name=credential_data.name,
        encrypted_data=encrypted_data,
        created_by=current_user.email,
    )

    db.add(new_credential)
    db.commit()
    db.refresh(new_credential)

    return new_credential


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    credential = db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == current_user.current_organization_id,
    ).first()

    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    return credential


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: UUID,
    credential_data: CredentialUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    credential = db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == current_user.current_organization_id,
    ).first()

    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    if credential_data.name:
        credential.name = credential_data.name

    if credential_data.credentials:
        existing_creds = decrypt_credentials(credential.encrypted_data)

        for key, value in credential_data.credentials.items():
            if key == "api_key" and value and "*" in value:
                continue
            existing_creds[key] = value

        credential.encrypted_data = encrypt_credentials(existing_creds)

    db.commit()
    db.refresh(credential)

    return credential


@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    credential = db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == current_user.current_organization_id,
    ).first()

    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    db.delete(credential)
    db.commit()

    return {"message": "Credential deleted successfully"}
