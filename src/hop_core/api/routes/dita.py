"""DITA rendering route.

``POST /dita/render`` turns a DITA topic into an HTML fragment for
``<hop-dita-content>``. Opt in with ``create_hop_app(include_dita_router=True)``;
it needs the ``dita`` extra (lxml).

The route renders one self-contained topic. Content that points outside it —
conrefs to other files, keyrefs — needs a map or repository the route cannot
see, so it renders as authored and is reported in ``warnings``. Apps that can
resolve it should call :class:`hop_core.dita.DitaRenderer` from their own
route with a ``loader`` and ``keys``.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from hop_core.api.dependencies import get_current_active_user
from hop_core.core.rate_limit import limiter
from hop_core.dita.renderer import DitaParseError, DitaRenderer
from hop_core.models.user import User

router = APIRouter(prefix="/dita")

# Generous for a single topic; bounds the parse cost of one request.
MAX_TOPIC_BYTES = 2 * 1024 * 1024


class DitaRenderRequest(BaseModel):
    content: str = Field(min_length=1)
    exclude: Dict[str, List[str]] = Field(default_factory=dict)
    show_draft: bool = False
    heading_offset: int = Field(default=0, ge=0, le=5)


class DitaRenderResponse(BaseModel):
    html: str
    title: str
    shortdesc: Optional[str] = None
    topic_id: Optional[str] = None
    topic_type: str
    lang: Optional[str] = None
    warnings: List[str] = []


@router.post("/render", response_model=DitaRenderResponse)
@limiter.limit("120/minute")
def render_topic(
    request: Request,
    payload: DitaRenderRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Render a DITA topic to an HTML fragment.

    A plain ``def``: rendering is CPU-bound, so FastAPI runs it in its threadpool
    rather than on the event loop.
    """
    if len(payload.content.encode("utf-8")) > MAX_TOPIC_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Topic exceeds {MAX_TOPIC_BYTES // (1024 * 1024)} MB",
        )
    renderer = DitaRenderer(
        exclude=payload.exclude,
        show_draft=payload.show_draft,
        heading_offset=payload.heading_offset,
    )
    try:
        result = renderer.render(payload.content)
    except DitaParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return result.to_dict()
