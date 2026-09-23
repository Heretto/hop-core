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
        CredentialTypeRegistry.register(
            "openai", label="OpenAI", is_ai_configuration=True
        )

    A type registered with ``is_ai_configuration=True`` holds an AI
    configuration — an API key plus the model it addresses — and becomes
    selectable as an agent's model configuration. Nothing else changes about
    how the credential is stored or created.
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
    def get_ai_types(cls) -> list[str]:
        """Credential types registered as AI configurations."""
        return [
            type_key
            for type_key, metadata in cls._types.items()
            if metadata.get("is_ai_configuration")
        ]

    @classmethod
    def is_ai_type(cls, type_key: str) -> bool:
        return bool(cls._types.get(type_key, {}).get("is_ai_configuration"))

    @classmethod
    def clear(cls) -> None:
        cls._types.clear()
