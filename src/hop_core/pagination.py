"""Server-side pagination helpers for FastAPI + SQLAlchemy.

Usage — backend route:

    from hop_core.pagination import PaginationParams, PaginatedResponse, paginate
    from hop_core.models.user import User

    SORT_MAP = {
        "email": User.email,
        "created_at": User.created_at,
    }

    @router.get("/users", response_model=PaginatedResponse[UserResponse])
    async def list_users(
        params: Annotated[PaginationParams, Depends()],
        db: Session = Depends(get_db),
    ):
        q = db.query(User).filter(User.is_active == True)
        # Apply domain-specific filters before calling paginate():
        if params.filter:
            term = f"%{params.filter}%"
            q = q.filter(User.email.ilike(term))
        items, total = paginate(q, params, SORT_MAP)
        return PaginatedResponse(items=[serialize(u) for u in items], total=total,
                                  page=params.page, page_size=params.page_size)
"""

from typing import Annotated, Any, Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel
from fastapi import Query

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency — query params for pagination, sorting, and filtering.

    Inject with ``Depends()``:

        async def my_route(params: Annotated[PaginationParams, Depends()]):
            ...
    """

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
        page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize")] = 25,
        sort_by: Annotated[Optional[str], Query(alias="sortBy")] = None,
        sort_dir: Annotated[Literal["asc", "desc"], Query(alias="sortDir")] = "asc",
        filter: Annotated[Optional[str], Query(max_length=200)] = None,
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_dir = sort_dir
        self.filter = filter or ""


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated envelope returned by server-side table endpoints."""

    items: List[T]
    total: int
    page: int
    page_size: int


def paginate(
    query: Any,
    params: "PaginationParams",
    sort_map: Optional[dict[str, Any]] = None,
) -> tuple[list, int]:
    """Apply sort → count → offset/limit to a SQLAlchemy ORM query.

    Args:
        query:    A SQLAlchemy ORM query (``db.query(Model).filter(...)``).
        params:   Dependency-injected ``PaginationParams`` from the request.
        sort_map: Maps ``sort_by`` values the client may send to SQLAlchemy
                  column expressions.  Keys not in this map are ignored so
                  clients cannot sort by arbitrary columns.

    Returns:
        ``(items, total)`` — the sliced ORM objects and the unsliced count.

    Filtering is intentionally NOT done here: which columns are searchable is
    domain-specific.  Apply ``.filter()`` before calling ``paginate()``.
    """
    if sort_map and params.sort_by and params.sort_by in sort_map:
        col = sort_map[params.sort_by]
        query = query.order_by(col.desc() if params.sort_dir == "desc" else col.asc())

    total: int = query.count()
    offset = (params.page - 1) * params.page_size
    items = query.offset(offset).limit(params.page_size).all()
    return items, total
