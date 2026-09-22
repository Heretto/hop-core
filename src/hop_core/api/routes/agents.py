"""Agent configuration CRUD routes.

Agents are organization-scoped: every route reads and writes only the agents
of the caller's current organization. Running an agent is not a route — that
belongs to the host app's jobs and workflows, which build an
:class:`~hop_core.agents.definition.AgentDefinition` from the stored row.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload, selectinload
from typing import List, Optional
from uuid import UUID

from hop_core.agents import configurations
from hop_core.agents.definition import AgentDefinition
from hop_core.agents.providers import AiProviderError, CredentialAiService
from hop_core.agents.runner import AgentNotConfigured, AgentRunner
from hop_core.core.rate_limit import limiter
from hop_core.core.security import decrypt_credentials
from hop_core.db import get_db
from hop_core.models.agent import Agent, AgentContextFile
from hop_core.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentCreate,
    AgentFeedbackAppend,
    AgentFeedbackUpdate,
    AgentResponse,
    AgentSummaryResponse,
    AgentUpdate,
    AiConfigurationSummary,
)
from hop_core.api.dependencies import (
    CurrentUserContext,
    get_current_active_user_with_org,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents")


# ── Serialization ─────────────────────────────────────────────────────────────

def _summary(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "ai_configuration_id": agent.ai_configuration_id,
        "ai_configuration": configurations.describe(agent.ai_configuration),
        "permitted_urls": agent.permitted_urls or [],
        "context_file_count": len(agent.context_files),
        "has_feedback_memory": bool((agent.feedback_memory or "").strip()),
        "is_active": agent.is_active,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "created_by": agent.created_by,
    }


def _detail(agent: Agent) -> dict:
    return {
        **_summary(agent),
        "context_files": [
            {
                "id": f.id,
                "name": f.name,
                "content": f.content or "",
                "position": f.position,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
            }
            for f in agent.context_files
        ],
        "feedback_memory": agent.feedback_memory or "",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_owned_agent(agent_id: UUID, organization_id: UUID, db: Session) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.organization_id == organization_id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


def _assert_name_available(
    name: str,
    organization_id: UUID,
    db: Session,
    exclude_id: Optional[UUID] = None,
) -> None:
    query = db.query(Agent).filter(
        Agent.organization_id == organization_id,
        Agent.name == name,
    )
    if exclude_id is not None:
        query = query.filter(Agent.id != exclude_id)

    if query.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An agent with this name already exists",
        )


def _validate_ai_configuration(
    ai_configuration_id: Optional[UUID], organization_id: UUID, db: Session
) -> None:
    """Reject a configuration that is not this organization's, or not an AI one."""
    if ai_configuration_id is None:
        return

    if configurations.get_for_organization(ai_configuration_id, organization_id, db) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI configuration not found in this organization",
        )


def _replace_context_files(agent: Agent, context_files) -> None:
    """Make the agent's context files exactly the list supplied.

    Clearing the collection is enough to remove the old rows: the
    relationship cascades ``delete-orphan``.
    """
    agent.context_files.clear()

    for index, context_file in enumerate(context_files):
        agent.context_files.append(
            AgentContextFile(
                name=context_file.name,
                content=context_file.content or "",
                position=context_file.position if context_file.position is not None else index,
            )
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AgentSummaryResponse])
async def list_agents(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    # The summary counts context files, so load them in one query rather than
    # one per agent.
    agents = db.query(Agent).options(
        selectinload(Agent.context_files),
        joinedload(Agent.ai_configuration),
    ).filter(
        Agent.organization_id == context.organization_id,
    ).order_by(Agent.name).all()

    return [_summary(agent) for agent in agents]


@router.post("", response_model=AgentResponse)
async def create_agent(
    agent_data: AgentCreate,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    _assert_name_available(agent_data.name, context.organization_id, db)
    _validate_ai_configuration(
        agent_data.ai_configuration_id, context.organization_id, db
    )

    agent = Agent(
        organization_id=context.organization_id,
        user_id=context.user.id,
        name=agent_data.name,
        description=agent_data.description,
        ai_configuration_id=agent_data.ai_configuration_id,
        permitted_urls=agent_data.permitted_urls,
        feedback_memory=agent_data.feedback_memory or "",
        is_active=agent_data.is_active,
        created_by=context.user.email,
    )
    _replace_context_files(agent, agent_data.context_files)

    db.add(agent)
    db.commit()
    db.refresh(agent)

    return _detail(agent)


@router.get("/ai-configurations", response_model=List[AiConfigurationSummary])
async def list_ai_configurations(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """The AI configurations an agent can be pointed at.

    These are the organization's credentials whose type was registered with
    ``is_ai_configuration=True``. They are established separately — through
    the credentials API — and an agent selects exactly one.
    """
    return [
        configurations.describe(credential)
        for credential in configurations.list_for_organization(
            context.organization_id, db
        )
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    return _detail(_get_owned_agent(agent_id, context.organization_id, db))


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    agent = _get_owned_agent(agent_id, context.organization_id, db)
    # `exclude_unset` distinguishes "not sent" from "sent as null", which
    # description relies on to be clearable.
    fields = agent_data.model_dump(exclude_unset=True)

    if agent_data.name is not None:
        _assert_name_available(
            agent_data.name, context.organization_id, db, exclude_id=agent.id
        )
        agent.name = agent_data.name

    if "description" in fields:
        agent.description = agent_data.description

    if "ai_configuration_id" in fields:
        # Explicit null clears it, which is how the UI unsets a configuration.
        _validate_ai_configuration(
            agent_data.ai_configuration_id, context.organization_id, db
        )
        agent.ai_configuration_id = agent_data.ai_configuration_id

    if agent_data.permitted_urls is not None:
        agent.permitted_urls = agent_data.permitted_urls

    if agent_data.feedback_memory is not None:
        agent.feedback_memory = agent_data.feedback_memory

    if agent_data.is_active is not None:
        agent.is_active = agent_data.is_active

    if agent_data.context_files is not None:
        _replace_context_files(agent, agent_data.context_files)

    db.commit()
    db.refresh(agent)

    return _detail(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    agent = _get_owned_agent(agent_id, context.organization_id, db)
    db.delete(agent)
    db.commit()

    return {"message": "Agent deleted successfully"}


@router.post("/{agent_id}/chat", response_model=AgentChatResponse)
@limiter.limit("30/minute")
async def chat_with_agent(
    request: Request,
    agent_id: UUID,
    chat_request: AgentChatRequest,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Talk to an agent, to see how it actually behaves.

    Runs the agent exactly as a job would — same composed system prompt, same
    AI configuration — with the conversation so far instead of a single set of
    instructions. Nothing is stored: the transcript lives in the caller.

    Rate-limited because every message is a paid model call.
    """
    # Eager-load context_files and ai_configuration so build_system_prompt()
    # always has them — lazy loading is not reliable in the async call path.
    agent = db.query(Agent).options(
        selectinload(Agent.context_files),
        joinedload(Agent.ai_configuration),
    ).filter(
        Agent.id == agent_id,
        Agent.organization_id == context.organization_id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    definition = AgentDefinition.from_model(agent)

    credential = agent.ai_configuration
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This agent has no AI configuration selected.",
        )

    try:
        payload = decrypt_credentials(credential.encrypted_data)
    except Exception:
        logger.warning(
            "Could not decrypt AI configuration %s", credential.id, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The AI configuration could not be decrypted. Re-enter its API key.",
        )

    api_key = payload.get("api_key") or ""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The AI configuration has no API key.",
        )

    service = CredentialAiService(
        provider=credential.type,
        model=str(payload.get("model") or "").strip(),
        api_key=api_key,
    )

    try:
        result = await AgentRunner(service).chat(
            definition,
            chat_request.messages,
            max_tokens=chat_request.max_tokens,
            temperature=chat_request.temperature,
        )
    except AgentNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AiProviderError as exc:
        # The vendor's own words: "model not found" is the whole answer when
        # someone is working out why their agent misbehaves.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message)

    return AgentChatResponse(
        message={"role": "assistant", "content": result.output},
        provider=result.provider,
        model=result.model,
        ai_configuration_name=result.ai_configuration_name,
        system_prompt=result.system_prompt,
    )


@router.put("/{agent_id}/memory", response_model=AgentResponse)
async def replace_agent_memory(
    agent_id: UUID,
    memory_data: AgentFeedbackUpdate,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Replace the agent's feedback memory wholesale (the UI's memory editor)."""
    agent = _get_owned_agent(agent_id, context.organization_id, db)
    agent.feedback_memory = memory_data.feedback_memory
    db.commit()
    db.refresh(agent)

    return _detail(agent)


@router.post("/{agent_id}/memory", response_model=AgentResponse)
async def append_agent_memory(
    agent_id: UUID,
    feedback_data: AgentFeedbackAppend,
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Add one piece of feedback to what the agent already remembers.

    Workflows use this after a run is reviewed, so feedback accumulates
    without the caller having to fetch and resend the whole memory.
    """
    agent = _get_owned_agent(agent_id, context.organization_id, db)

    heading = feedback_data.heading or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"### {heading}\n\n{feedback_data.feedback.strip()}"
    existing = (agent.feedback_memory or "").rstrip()
    agent.feedback_memory = f"{existing}\n\n{entry}" if existing else entry

    db.commit()
    db.refresh(agent)

    return _detail(agent)
