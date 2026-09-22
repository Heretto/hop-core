"""Reading AI configurations — the model configuration agents point at.

An AI configuration is an ordinary credential whose type was registered with
``is_ai_configuration=True``. The credential's *type* is the provider, and its
encrypted payload carries the API key and the model it addresses::

    CredentialTypeRegistry.register("anthropic", label="Anthropic",
                                    is_ai_configuration=True)

    POST /credentials  {"type": "anthropic", "name": "Anthropic — Opus 5",
                        "credentials": {"api_key": "...", "model": "claude-opus-5"}}

Nothing here returns the API key. Callers that need it decrypt the credential
themselves, which keeps the key out of API responses and out of prompts.
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from hop_core.core.security import decrypt_credentials
from hop_core.models.credential import Credential
from hop_core.models.enums import CredentialTypeRegistry

logger = logging.getLogger(__name__)


def read_model(credential: Credential) -> str:
    """The model named by an AI configuration, or "" if it does not name one.

    A credential whose payload cannot be decrypted (a rotated encryption key,
    say) reads as no model rather than raising: the agent still lists, and the
    problem shows up where it belongs — at run time.
    """
    try:
        return decrypt_credentials(credential.encrypted_data).get("model", "") or ""
    except Exception:
        logger.warning(
            "Could not read the model from credential %s", credential.id, exc_info=True
        )
        return ""


def describe(credential: Optional[Credential]) -> Optional[dict]:
    """The display shape of an AI configuration, without its secret."""
    if credential is None:
        return None

    metadata = CredentialTypeRegistry.get_metadata(credential.type)
    return {
        "id": credential.id,
        "name": credential.name,
        "provider": credential.type,
        "provider_label": metadata.get("label") or credential.type,
        "model": read_model(credential),
    }


def list_for_organization(organization_id: UUID, db: Session) -> List[Credential]:
    """Every AI configuration available to an organization.

    Returns nothing when the host app has registered no AI credential types —
    the agent UI reads that as "no configurations have been set up yet".
    """
    ai_types = CredentialTypeRegistry.get_ai_types()
    if not ai_types:
        return []

    return db.query(Credential).filter(
        Credential.organization_id == organization_id,
        Credential.type.in_(ai_types),
    ).order_by(Credential.name).all()


def get_for_organization(
    credential_id: UUID, organization_id: UUID, db: Session
) -> Optional[Credential]:
    """One AI configuration, or None if it is not one, or not this org's."""
    credential = db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == organization_id,
    ).first()

    if credential is None or not CredentialTypeRegistry.is_ai_type(credential.type):
        return None

    return credential
