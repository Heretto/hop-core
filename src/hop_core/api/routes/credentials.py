"""Generic credential CRUD routes.

Credentials are stored as an encrypted opaque payload. What belongs in that
payload is described by the *field spec* an application registers for the
type, which drives the management UI and the validation here. Types with no
registered spec keep working as free-form dictionaries.

Type-specific behaviour beyond storage — testing a Jira connection, listing a
provider's models — is still the host application's job.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from hop_core.core.rate_limit import limiter
from hop_core.credentials import get_spec, get_specs, public_values, run_test, secrets_set, validate_payload
from hop_core.credentials.fields import CredentialTypeSpec
from hop_core.credentials.testing import CredentialTestResult, CredentialTesterRegistry
from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.models.credential import Credential
from hop_core.schemas.credential import CredentialCreate, CredentialUpdate, CredentialResponse
from hop_core.api.dependencies import get_current_active_user
from hop_core.core.security import encrypt_credentials, decrypt_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials")


def mask_secret(value: str) -> str:
    """Mask a secret string, showing only first 4 and last 4 characters."""
    if not value or len(value) <= 8:
        return "*" * len(value) if value else ""
    return value[:4] + "*" * min(len(value) - 8, 20) + value[-4:]


def _serialize(credential: Credential) -> dict:
    """A credential as the API returns it — never its secrets."""
    spec = get_spec(credential.type)
    try:
        payload = decrypt_credentials(credential.encrypted_data)
    except Exception:
        logger.warning(
            "Could not decrypt credential %s", credential.id, exc_info=True
        )
        payload = {}

    return {
        "id": credential.id,
        "type": credential.type,
        "name": credential.name,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
        "values": public_values(spec, payload),
        "secrets_set": secrets_set(spec, payload),
    }


def _assert_payload_complete(type_key: str, payload: dict) -> None:
    missing = validate_payload(get_spec(type_key), payload)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required field(s): {', '.join(missing)}",
        )


@router.get("", response_model=List[CredentialResponse])
async def list_credentials(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.current_organization_id:
        return []
    credentials = db.query(Credential).filter(
        Credential.organization_id == current_user.current_organization_id,
    ).order_by(Credential.type, Credential.name).all()
    return [_serialize(credential) for credential in credentials]


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

    _assert_payload_complete(credential_data.type, credential_data.credentials)

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

    return _serialize(new_credential)


@router.get("/types", response_model=List[CredentialTypeSpec])
async def list_credential_types(
    current_user: User = Depends(get_current_active_user),
):
    """The credential types this application has registered.

    Drives the management UI: one tab per type (or per group), and a form
    built from each type's fields. An app that registers nothing gets an
    empty list and a UI that says so.
    """
    return get_specs()


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

    return _serialize(credential)


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
        spec = get_spec(credential.type)
        secret_fields = {f.name for f in spec.fields if f.secret} if spec else set()

        for key, value in credential_data.credentials.items():
            # A secret submitted blank means "keep what is stored" — the form
            # never receives the current value, so it cannot resend it.
            if key in secret_fields and not str(value or "").strip():
                continue
            # Legacy masked-value guard, for callers that echo back a mask.
            if key == "api_key" and value and "*" in value:
                continue
            existing_creds[key] = value

        _assert_payload_complete(credential.type, existing_creds)
        credential.encrypted_data = encrypt_credentials(existing_creds)

    db.commit()
    db.refresh(credential)

    return _serialize(credential)


@router.post("/{credential_id}/test", response_model=CredentialTestResult)
@limiter.limit("10/minute")
async def test_credential(
    request: Request,
    credential_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Check that a credential actually reaches the service it names.

    Rate-limited because every call leaves the building, and an AI provider
    test costs real tokens.

    A credential that cannot connect is a 200 with ``success: false`` — the
    request succeeded, the connection did not, and the UI wants to show why.
    Only a missing credential or an untestable type is an error status.
    """
    credential = db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == current_user.current_organization_id,
    ).first()

    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    if not CredentialTesterRegistry.is_testable(credential.type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Credentials of type '{credential.type}' cannot be tested",
        )

    try:
        payload = decrypt_credentials(credential.encrypted_data)
    except Exception:
        logger.warning("Could not decrypt credential %s for testing", credential.id, exc_info=True)
        return CredentialTestResult(
            success=False,
            message="This credential could not be decrypted. Re-enter its secrets and try again.",
        )

    return await run_test(credential.type, payload)


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
