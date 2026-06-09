"""OAuth 2.0 / OpenID Connect client configuration.

Lazily initialized — the OAuth registry is populated when
init_oauth() is called by the host app or the app factory.
"""

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
_initialized = False


def init_oauth(
    microsoft_client_id: str = None,
    microsoft_client_secret: str = None,
    microsoft_tenant_id: str = "common",
) -> None:
    """Register OAuth providers based on available configuration."""
    global _initialized
    if _initialized:
        return

    if microsoft_client_id and microsoft_client_secret:
        oauth.register(
            name="microsoft",
            client_id=microsoft_client_id,
            client_secret=microsoft_client_secret,
            server_metadata_url=(
                f"https://login.microsoftonline.com/{microsoft_tenant_id}"
                "/v2.0/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

    _initialized = True
