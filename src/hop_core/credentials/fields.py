"""Field specifications that describe how to fill in a credential type.

A credential's payload is an opaque dict as far as storage is concerned. These
specs say what belongs in it, which lets one generic UI render a correct form
for every type an app has registered, and lets the API validate what it is
given without hop-core knowing anything about Jira or Anthropic.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

FieldType = Literal["text", "password", "email", "url", "select", "textarea"]


class CredentialFieldOption(BaseModel):
    value: str
    label: str


class CredentialField(BaseModel):
    """One input in a credential form."""

    name: str
    label: str
    type: FieldType = "text"
    required: bool = True
    # Secrets are write-only: never returned, and left alone on update when
    # the form submits them blank.
    secret: bool = False
    # Non-secret fields marked for display shown as a column in the list.
    summary: bool = False
    placeholder: str = ""
    help: str = ""
    options: List[CredentialFieldOption] = Field(default_factory=list)


class CredentialTypeSpec(BaseModel):
    """A credential type as the management UI needs to see it."""

    type: str
    label: str
    # Types sharing a group render in one tab, with a picker choosing between
    # them — which is how three AI providers become one "AI Providers" tab.
    group: Optional[str] = None
    group_label: Optional[str] = None
    icon: str = "key"
    description: str = ""
    is_ai_configuration: bool = False
    # Whether a connection tester is registered — the UI only offers a Test
    # button where something can actually answer.
    testable: bool = False
    fields: List[CredentialField] = Field(default_factory=list)


def public_values(spec: Optional[CredentialTypeSpec], payload: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a stored payload that is safe to return.

    Driven by the spec rather than by the payload, so a key the spec does not
    describe is never echoed back. An unregistered type has no spec and
    therefore discloses nothing.
    """
    if spec is None:
        return {}

    return {
        field.name: payload.get(field.name)
        for field in spec.fields
        if not field.secret and payload.get(field.name) is not None
    }


def secrets_set(spec: Optional[CredentialTypeSpec], payload: Dict[str, Any]) -> List[str]:
    """Which secret fields currently hold a value.

    The UI uses this to say "leave blank to keep the existing value" instead
    of showing a masked secret — masking still leaks a key's first and last
    characters, and nothing here needs them.
    """
    if spec is None:
        return []

    return [
        field.name
        for field in spec.fields
        if field.secret and payload.get(field.name)
    ]


def validate_payload(spec: Optional[CredentialTypeSpec], payload: Dict[str, Any]) -> List[str]:
    """Names of required fields the payload is missing.

    Types with no registered spec are not validated, so an app that registers
    nothing keeps today's free-form behaviour.
    """
    if spec is None or not spec.fields:
        return []

    return [
        field.name
        for field in spec.fields
        if field.required and not str(payload.get(field.name) or "").strip()
    ]
