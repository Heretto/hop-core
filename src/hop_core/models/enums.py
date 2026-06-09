"""Enums and registries for hop-core models."""

import enum
from typing import Dict, Optional, Any


class OrganizationRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class CredentialTypeRegistry:
    """Registry for credential types.

    Host apps register their credential types at startup::

        CredentialTypeRegistry.register("jira", label="Jira")
        CredentialTypeRegistry.register("openai", label="OpenAI")
    """

    _types: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, type_key: str, label: Optional[str] = None, **metadata: Any) -> None:
        cls._types[type_key] = {"label": label or type_key, **metadata}

    @classmethod
    def get_types(cls) -> list[str]:
        return list(cls._types.keys())

    @classmethod
    def is_registered(cls, type_key: str) -> bool:
        return type_key in cls._types

    @classmethod
    def get_metadata(cls, type_key: str) -> Dict[str, Any]:
        return cls._types.get(type_key, {})

    @classmethod
    def clear(cls) -> None:
        cls._types.clear()
