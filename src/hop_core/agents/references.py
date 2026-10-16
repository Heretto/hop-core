"""Reading an agent's Heretto references from inside the host app.

Agents with Heretto references need a :class:`ReferenceContentSource` to read
them. The chat route builds one per request; a host app's jobs and workflows
build theirs the same way::

    source = heretto_reference_source(organization_id, db)
    result = await AgentRunner(ai_service, reference_source=source).run(definition, request)

Without one, references included in every run are reported to the agent as
unavailable, and on-demand Heretto content is not offered.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from hop_core.core.security import decrypt_credentials
from hop_core.heretto import HerettoError, ReferenceCache, ReferenceContentSource
from hop_core.models.credential import Credential

HERETTO_CREDENTIAL_TYPE = "heretto"


def heretto_connections(organization_id, db: Session):
    """The organization's Heretto credentials, by name."""
    return db.query(Credential).filter(
        Credential.organization_id == organization_id,
        Credential.type == HERETTO_CREDENTIAL_TYPE,
    ).order_by(Credential.name).all()


def heretto_credential(credential_id, organization_id, db: Session):
    """The organization's Heretto credential with this ID, or None."""
    return db.query(Credential).filter(
        Credential.id == credential_id,
        Credential.organization_id == organization_id,
        Credential.type == HERETTO_CREDENTIAL_TYPE,
    ).first()


def heretto_reference_source(
    organization_id, db: Session, cache: ReferenceCache = None,
) -> ReferenceContentSource:
    """A reference reader that uses the organization's own Heretto connections.

    A reference naming a connection from another organization reads as
    missing, so one organization's agent can never read through another's
    credentials.
    """
    async def load(credential_id: str) -> dict:
        credential = heretto_credential(UUID(str(credential_id)), organization_id, db)
        if credential is None:
            raise HerettoError("its Heretto connection no longer exists")
        try:
            return decrypt_credentials(credential.encrypted_data)
        except Exception as exc:
            raise HerettoError(
                "its Heretto connection could not be decrypted — re-enter the API token"
            ) from exc

    return ReferenceContentSource(load, cache=cache)
