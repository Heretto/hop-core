"""Built-in credential types an application can opt into.

hop-core ships the three kinds of credential the Release Notes Agent needs —
Jira, Heretto, and AI providers — because they are the ones every app built on
this platform has wanted so far. An app registers the subset that makes sense
for it::

    from hop_core.credentials import register_builtin_types

    register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)

Each built-in type brings its connection tester with it, so the Test button in
the credentials UI works without further wiring.

Anything else is a plain ``CredentialTypeRegistry.register()`` call with its
own field list, plus an optional ``CredentialTesterRegistry.register()``;
nothing here is privileged.
"""

from typing import Dict

from hop_core.credentials.fields import CredentialField, CredentialTypeSpec
from hop_core.credentials.testers import register_builtin_tester
from hop_core.models.enums import CredentialTypeRegistry

#: The AI provider types, which share one "AI Providers" tab in the UI and are
#: what an agent's model configuration is selected from.
AI_PROVIDER_TYPES = ("anthropic", "openai", "gemini")


def _ai_provider(type_key: str, label: str, model_placeholder: str) -> CredentialTypeSpec:
    return CredentialTypeSpec(
        type=type_key,
        label=label,
        group="ai",
        group_label="AI Providers",
        icon="smart_toy",
        description=f"An API key for {label}, and the model it addresses.",
        is_ai_configuration=True,
        fields=[
            CredentialField(
                name="api_key",
                label="API Key",
                type="password",
                secret=True,
                placeholder="sk-...",
            ),
            CredentialField(
                name="model",
                label="Model",
                required=False,
                summary=True,
                placeholder=model_placeholder,
                help="The model this configuration addresses. Agents select the "
                     "configuration, not the model, so changing it here moves "
                     "every agent using it.",
            ),
        ],
    )


BUILTIN_CREDENTIAL_TYPES: Dict[str, CredentialTypeSpec] = {
    "jira": CredentialTypeSpec(
        type="jira",
        label="Jira",
        icon="bug_report",
        description="A Jira site and the account issues are read as.",
        fields=[
            CredentialField(
                name="server_url",
                label="Server URL",
                type="url",
                summary=True,
                placeholder="https://your-org.atlassian.net",
            ),
            CredentialField(
                name="email",
                label="Email",
                type="email",
                summary=True,
                placeholder="you@your-org.com",
            ),
            CredentialField(
                name="api_token",
                label="API Token",
                type="password",
                secret=True,
                help="Created under Atlassian account settings, not your password.",
            ),
        ],
    ),
    "heretto": CredentialTypeSpec(
        type="heretto",
        label="Heretto",
        icon="menu_book",
        description="A Heretto CCMS instance and the account content is written as.",
        fields=[
            CredentialField(
                name="server_url",
                label="Server URL",
                type="url",
                summary=True,
                placeholder="https://your-org.heretto.com",
            ),
            CredentialField(
                name="username",
                label="Username",
                summary=True,
            ),
            CredentialField(
                name="token",
                label="API Token",
                type="password",
                secret=True,
            ),
        ],
    ),
    "anthropic": _ai_provider("anthropic", "Anthropic", "claude-opus-5"),
    "openai": _ai_provider("openai", "OpenAI", "gpt-5"),
    "gemini": _ai_provider("gemini", "Google Gemini", "gemini-2.5-pro"),
}


def register_builtin_types(*type_keys: str) -> None:
    """Register the named built-in credential types.

    Called with no arguments, registers all of them. An unknown name is an
    error rather than a silent no-op — a typo here would otherwise show up
    much later as a credential type missing from the UI.
    """
    keys = type_keys or tuple(BUILTIN_CREDENTIAL_TYPES)

    unknown = [key for key in keys if key not in BUILTIN_CREDENTIAL_TYPES]
    if unknown:
        raise ValueError(
            f"Unknown built-in credential type(s): {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(sorted(BUILTIN_CREDENTIAL_TYPES))}"
        )

    for key in keys:
        spec = BUILTIN_CREDENTIAL_TYPES[key]
        CredentialTypeRegistry.register(
            spec.type,
            label=spec.label,
            group=spec.group,
            group_label=spec.group_label,
            icon=spec.icon,
            description=spec.description,
            is_ai_configuration=spec.is_ai_configuration,
            fields=[field.model_dump() for field in spec.fields],
        )
        # A type brings its connection test and, for AI providers, its
        # generator: importing the type is all an app should have to do to
        # get a working Test button and a runnable agent.
        register_builtin_tester(key)
        if spec.is_ai_configuration:
            from hop_core.agents.providers import register_builtin_generator

            register_builtin_generator(key)
