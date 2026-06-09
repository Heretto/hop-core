"""Core middleware for hop-core applications."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enable_hsts: bool = False):
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
