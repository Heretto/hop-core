"""CSRF protection middleware using the double-submit cookie pattern.

State-changing requests (POST, PUT, DELETE, PATCH) that carry an
access_token cookie must also include an ``X-CSRF-Token`` header whose
value matches the ``csrf_token`` cookie set at login.

Requests authenticated via the ``Authorization`` header (API clients,
tests) are exempt because they are not vulnerable to CSRF.

Auth endpoints (login, register, refresh, logout) are also exempt.
"""

import hmac
from typing import FrozenSet, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_DEFAULT_EXEMPT_SUFFIXES = frozenset({
    "/auth/login",
    "/auth/logout",
    "/auth/register",
    "/auth/refresh",
    "/auth/forgot-password",
    "/auth/reset-password",
})


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_paths: Optional[FrozenSet[str]] = None):
        super().__init__(app)
        if exempt_paths is not None:
            self._exempt_paths = exempt_paths
        else:
            self._exempt_paths = frozenset(
                f"/api/v1{suffix}" for suffix in _DEFAULT_EXEMPT_SUFFIXES
            )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        if request.url.path in self._exempt_paths:
            return await call_next(request)

        if request.headers.get("authorization"):
            return await call_next(request)

        if "access_token" not in request.cookies:
            return await call_next(request)

        csrf_cookie = request.cookies.get("csrf_token", "")
        csrf_header = request.headers.get("x-csrf-token", "")

        if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

        return await call_next(request)
