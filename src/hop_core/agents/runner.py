"""Running an agent: input + instructions in, output out.

Agents do nothing on their own. A job or workflow hands one an
:class:`AgentRequest` and gets an :class:`AgentRunResult` back; the runner's
whole job is composing the agent's configuration into a prompt, delegating to
the injected AI service, and returning what came back.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from typing import List

from hop_core.agents.definition import AgentDefinition
from hop_core.ai import ChatMessage, GenerationRequest, SupportsGenerate

logger = logging.getLogger(__name__)


class AgentNotConfigured(RuntimeError):
    """An agent was run without a usable AI configuration."""


class AgentRequest(BaseModel):
    """What a workflow gives an agent for one run."""

    # What the agent should do this time.
    instructions: str
    # The material to do it to. Optional: some jobs are instruction-only.
    input: str = ""
    # Generation knobs for this run. The AI configuration owns the provider
    # and model; how hard to think about one job is the job's business.
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


class AgentRunResult(BaseModel):
    """What the agent returns to the workflow."""

    output: str
    agent_name: str
    # Which AI configuration produced this, for logging and audit.
    ai_configuration_name: str
    provider: str
    model: str
    system_prompt: str = Field(
        default="",
        description="The prompt the agent ran with, for logging and debugging.",
    )


class AgentRunner:
    """Runs agents against an injected AI service.

    ``ai_service`` is any object satisfying
    :class:`~hop_core.ai.SupportsGenerate` — an ``async generate(request)``
    method returning an object with ``.content``. hop-core does not pick a
    vendor; the host app supplies a service already wired to its credentials.
    """

    def __init__(self, ai_service: SupportsGenerate):
        self.ai_service = ai_service

    def build_user_prompt(self, request: AgentRequest) -> str:
        """Compose the per-run prompt from instructions and input."""
        sections = [f"## Instructions\n\n{request.instructions.strip()}"]
        user_input = (request.input or "").strip()
        if user_input:
            sections.append(f"## Input\n\n{user_input}")
        return "\n\n".join(sections)

    def _configuration(self, definition: AgentDefinition):
        configuration = definition.ai_configuration
        if configuration is None:
            raise AgentNotConfigured(
                f"Agent {definition.name!r} has no AI configuration selected"
            )
        return configuration

    async def chat(
        self,
        definition: AgentDefinition,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AgentRunResult:
        """Hold a conversation with the agent, for testing how it behaves.

        Same agent, same composed system prompt as :meth:`run` — the only
        difference is that the turns accumulate, so what is being tested is
        the agent as a workflow would get it.
        """
        configuration = self._configuration(definition)
        if not messages:
            raise ValueError("A chat needs at least one message")

        system_prompt = definition.build_system_prompt()
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )

        generation = GenerationRequest(
            system_prompt=system_prompt,
            # Repeated for services that predate multi-turn; see GenerationRequest.
            user_prompt=last_user,
            messages=list(messages),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        result = await self.ai_service.generate(generation)

        return AgentRunResult(
            output=result.content,
            agent_name=definition.name,
            ai_configuration_name=configuration.name,
            provider=configuration.provider,
            model=configuration.model,
            system_prompt=system_prompt,
        )

    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentRunResult:
        """Run ``definition`` once and return its output.

        Raises :class:`AgentNotConfigured` when the agent has no AI
        configuration — pointing at a deleted credential leaves it unset, and
        running anyway would silently fall back to whatever the service
        defaults to.
        """
        configuration = self._configuration(definition)
        system_prompt = definition.build_system_prompt()

        generation = GenerationRequest(
            system_prompt=system_prompt,
            user_prompt=self.build_user_prompt(request),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        logger.debug(
            "Running agent %r on %s/%s",
            definition.name,
            configuration.provider,
            configuration.model,
        )
        result = await self.ai_service.generate(generation)

        return AgentRunResult(
            output=result.content,
            agent_name=definition.name,
            ai_configuration_name=configuration.name,
            provider=configuration.provider,
            model=configuration.model,
            system_prompt=system_prompt,
        )
