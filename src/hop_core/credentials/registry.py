"""Reading credential type specs back out of the registry."""

from typing import List, Optional

from hop_core.credentials.fields import CredentialTypeSpec
from hop_core.credentials.testing import CredentialTesterRegistry
from hop_core.models.enums import CredentialTypeRegistry


def get_spec(type_key: str) -> Optional[CredentialTypeSpec]:
    """The spec for a registered type, or None if the type is unregistered.

    A type registered without ``fields`` still yields a spec — it just has no
    inputs to render, which the UI shows as a name-only credential.
    """
    if not CredentialTypeRegistry.is_registered(type_key):
        return None

    metadata = CredentialTypeRegistry.get_metadata(type_key)
    return CredentialTypeSpec(
        type=type_key,
        label=metadata.get("label") or type_key,
        group=metadata.get("group"),
        group_label=metadata.get("group_label"),
        icon=metadata.get("icon") or "key",
        description=metadata.get("description") or "",
        is_ai_configuration=bool(metadata.get("is_ai_configuration")),
        testable=CredentialTesterRegistry.is_testable(type_key),
        fields=metadata.get("fields") or [],
    )


def get_specs() -> List[CredentialTypeSpec]:
    """Every registered type, in registration order."""
    return [
        spec
        for spec in (get_spec(type_key) for type_key in CredentialTypeRegistry.get_types())
        if spec is not None
    ]
