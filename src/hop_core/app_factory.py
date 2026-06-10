"""Application factory for hop-core based applications."""

from typing import Callable, List, Optional
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from hop_core.config import configure, get_settings, HopCoreSettings
from hop_core.db import init_engine, init_db
from hop_core.core.rate_limit import limiter
from hop_core.core.csrf import CSRFMiddleware
from hop_core.core.oauth import init_oauth
from hop_core.core.logging import setup_logging
from hop_core.middleware import SecurityHeadersMiddleware
from hop_core.api.routes import auth, sso, account, organizations, invitations, credentials, admin, superadmin

logger = logging.getLogger(__name__)


def create_hop_app(
    settings_factory: Callable[[], HopCoreSettings],
    extra_routers: Optional[List] = None,
    title: str = "Hop Application",
    description: str = "",
    version: str = "1.0.0",
    include_admin: bool = True,
    include_superadmin: bool = True,
    include_credentials_router: bool = True,
) -> FastAPI:
    """Create a FastAPI application with hop-core platform routes.

    Args:
        settings_factory: Callable that returns the app settings instance.
        extra_routers: Additional APIRouter instances for domain-specific routes.
        title: Application title for OpenAPI docs.
        description: Application description for OpenAPI docs.
        version: Application version.
        include_admin: Include dev-only admin routes.
        include_superadmin: Include superadmin routes.
        include_credentials_router: Include hop-core's generic credentials router.
            Set to False when the host app provides its own credentials router via
            extra_routers with type-specific sub-routes (e.g. /credentials/jira).
    """
    configure(settings_factory)
    settings = get_settings()

    init_engine(settings.database_url, echo=settings.app_debug)

    setup_logging(
        level="DEBUG" if settings.app_debug else "INFO",
        use_json=(settings.app_env == "production"),
    )

    init_oauth(
        microsoft_client_id=settings.microsoft_oauth_client_id,
        microsoft_client_secret=settings.microsoft_oauth_client_secret,
        microsoft_tenant_id=settings.microsoft_oauth_tenant_id,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting up...")
        await init_db()
        yield
        logger.info("Shutting down...")

    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware stack (order matters — outermost first)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.cookie_secure)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key, max_age=300)
    app.add_middleware(CSRFMiddleware)

    # Core routes
    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix, tags=["auth"])
    app.include_router(sso.router, prefix=prefix, tags=["sso"])
    app.include_router(invitations.router, prefix=prefix, tags=["invitations"])
    if include_credentials_router:
        app.include_router(credentials.router, prefix=prefix, tags=["credentials"])
    app.include_router(account.router, prefix=prefix, tags=["account"])
    app.include_router(organizations.router, prefix=prefix, tags=["organizations"])

    if include_superadmin:
        app.include_router(superadmin.router, prefix=prefix, tags=["superadmin"])

    if include_admin and settings.app_env == "development":
        app.include_router(admin.router, prefix=prefix, tags=["admin"])

    # Domain-specific routes
    if extra_routers:
        for router in extra_routers:
            app.include_router(router, prefix=prefix)

    @app.get("/")
    async def root():
        return {"message": title, "version": version}

    return app
