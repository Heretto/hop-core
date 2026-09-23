"""Credential type definitions: what a credential of each type contains.

hop-core stores credentials as an encrypted opaque payload and does not care
what is in it. Registering a *field specification* for a type is what lets the
generic management UI render a correct form for it, lets the API reject an
incomplete payload, and lets a response safely echo back the non-secret parts.

An application registers the built-in types it needs::

    from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types

    register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)

and declares anything else itself::

    CredentialTypeRegistry.register(
        "zendesk", label="Zendesk", fields=[{...}]
    )
    CredentialTesterRegistry.register("zendesk", test_zendesk)

Registering a tester is what puts a Test button next to that type in the
credentials UI; the built-in types bring theirs along automatically.
"""

from hop_core.credentials.builtin import (
    AI_PROVIDER_TYPES,
    BUILTIN_CREDENTIAL_TYPES,
    register_builtin_types,
)
from hop_core.credentials.fields import (
    CredentialField,
    CredentialFieldOption,
    CredentialTypeSpec,
    public_values,
    secrets_set,
    validate_payload,
)
from hop_core.credentials.registry import get_spec, get_specs
from hop_core.credentials.testing import (
    CredentialTestResult,
    CredentialTester,
    CredentialTesterRegistry,
    run_test,
)

__all__ = [
    "AI_PROVIDER_TYPES",
    "BUILTIN_CREDENTIAL_TYPES",
    "register_builtin_types",
    "CredentialField",
    "CredentialFieldOption",
    "CredentialTypeSpec",
    "public_values",
    "secrets_set",
    "validate_payload",
    "get_spec",
    "get_specs",
    "CredentialTestResult",
    "CredentialTester",
    "CredentialTesterRegistry",
    "run_test",
]
