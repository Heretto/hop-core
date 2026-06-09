"""Core configuration for hop-core applications.

Host apps subclass HopCoreSettings and call configure() at startup
to register their settings factory.
"""

from pydantic_settings import BaseSettings
from typing import Callable, List, Optional
from functools import lru_cache


class HopCoreSettings(BaseSettings):
    # Application
    app_env: str = "development"
    app_secret_key: str
    app_debug: bool = False

    # Database
    database_url: str
    redis_url: str

    # Authentication
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # Encryption
    encryption_key: str

    # Email / SMTP (all optional)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: str = "Hop Platform"
    smtp_use_tls: bool = True

    # Password reset
    password_reset_token_expire_minutes: int = 30
    frontend_base_url: str = "http://localhost:4200"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)

    # SSO / OAuth
    sso_only: bool = False
    google_oauth_client_id: Optional[str] = None
    microsoft_oauth_client_id: Optional[str] = None
    microsoft_oauth_client_secret: Optional[str] = None
    microsoft_oauth_tenant_id: str = "common"
    oauth_redirect_base_url: Optional[str] = None

    # Single-organization mode
    single_org_mode: bool = False
    single_org_slug: Optional[str] = None
    allowed_email_domains: Optional[str] = None

    @property
    def allowed_domains_list(self) -> List[str]:
        if not self.allowed_email_domains:
            return []
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    # Cookies
    cookie_secure: bool = False
    cookie_domain: Optional[str] = None

    # CORS
    cors_origins: str = "http://localhost:4200"

    # Server
    api_prefix: str = "/api/v1"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(',')]


_settings_factory: Optional[Callable[[], HopCoreSettings]] = None


def configure(factory: Callable[[], HopCoreSettings]) -> None:
    """Register the settings factory. Must be called before get_settings()."""
    global _settings_factory
    _settings_factory = factory


def get_settings() -> HopCoreSettings:
    """Return the application settings instance.

    The host app must call configure() first to register a factory.
    """
    if _settings_factory is None:
        raise RuntimeError(
            "hop_core.config.configure() must be called before using settings. "
            "Call configure(your_get_settings) at application startup."
        )
    return _settings_factory()
