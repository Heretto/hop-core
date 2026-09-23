"""Agent configurations: stored definitions and the runtime that uses them.

An agent is an organization-scoped configuration — a name, the AI
configuration it runs on, markdown context files, permitted reference URLs,
and a separate feedback memory. The model configuration is established
separately (a credential of a type registered with
``is_ai_configuration=True``) and the agent selects one, so several agents can
share one key and model.

Agents do nothing on their own; jobs and workflows supply input and
instructions and receive output::

    definition = AgentDefinition.from_model(agent_row)
    result = await AgentRunner(ai_service).run(
        definition,
        AgentRequest(instructions="Summarize the changes", input=diff),
    )

CRUD lives at ``/api/v1/agents`` (see
:mod:`hop_core.api.routes.agents`); the management UI is
``HopAgentsComponent`` in ``@heretto/hop-ui``.
"""

from hop_core.agents import configurations
from hop_core.agents.definition import AgentDefinition, AiConfiguration, ContextFile
from hop_core.agents.providers import (
    AiProviderError,
    AiProviderRegistry,
    BUILTIN_TOOL_GENERATORS,
    CredentialAiService,
    GenerationResponse,
    MAX_TOOL_ITERATIONS,
)
from hop_core.agents.runner import (
    AgentNotConfigured,
    AgentRequest,
    AgentRunner,
    AgentRunResult,
)
from hop_core.agents.urls import (
    InvalidPermittedUrl,
    is_url_permitted,
    normalize_url,
    normalize_urls,
)

__all__ = [
    "configurations",
    "AgentDefinition",
    "AiConfiguration",
    "AiProviderError",
    "AiProviderRegistry",
    "BUILTIN_TOOL_GENERATORS",
    "CredentialAiService",
    "GenerationResponse",
    "MAX_TOOL_ITERATIONS",
    "ContextFile",
    "AgentNotConfigured",
    "AgentRequest",
    "AgentRunner",
    "AgentRunResult",
    "InvalidPermittedUrl",
    "is_url_permitted",
    "normalize_url",
    "normalize_urls",
]
