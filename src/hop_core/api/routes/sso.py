"""SSO authentication routes.

Google: Client-side ID token flow via Google Identity Services.
Microsoft: Server-side authorization code flow via authlib.
"""

import re
import uuid
import logging
from datetime import datetime, timedelta

import jwt as pyjwt
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from hop_core.config import get_settings
from hop_core.core.oauth import oauth
from hop_core.core.rate_limit import limiter
from hop_core.core.security import create_access_token, create_refresh_token, set_auth_cookies
from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.models.organization import Organization, OrganizationMember, user_organizations
from hop_core.models.enums import OrganizationRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso")

_google_jwks_client = pyjwt.PyJWKClient(
    "https://www.googleapis.com/oauth2/v3/certs",
    cache_jwk_set=True,
    lifespan=3600,
)


def _frontend_url(path: str = "/") -> str:
    settings = get_settings()
    if settings.oauth_redirect_base_url:
        return settings.oauth_redirect_base_url.rstrip("/") + path
    origins = settings.cors_origins_list
    if origins:
        return origins[0].rstrip("/") + path
    return path


def _safe_return_url(url: str | None) -> str:
    if not url:
        return "/dashboard"
    try:
        decoded = url if isinstance(url, str) else str(url)
        if decoded.startswith("/") and not decoded.startswith("//") and "://" not in decoded:
            return decoded
    except Exception:
        pass
    return "/dashboard"


def _create_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


def _build_token_data(user: User, db: Session) -> dict:
    token_data = {"sub": str(user.id), "email": user.email}
    stmt = select(user_organizations).where(user_organizations.c.user_id == user.id)
    user_orgs = db.execute(stmt).fetchall()

    if user_orgs:
        default_org = user_orgs[0]
        role_val = default_org.role.value if hasattr(default_org.role, "value") else default_org.role
        token_data["org_id"] = str(default_org.organization_id)
        token_data["org_role"] = role_val.lower() if isinstance(role_val, str) else role_val

    return token_data


def _handle_sso_login(
    db: Session,
    provider: str,
    oauth_id: str,
    email: str,
    name: str | None,
) -> User:
    settings = get_settings()

    user = db.query(User).filter(
        User.oauth_provider == provider,
        User.oauth_id == oauth_id,
    ).first()
    if user:
        return user

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.oauth_provider = provider
        user.oauth_id = oauth_id
        db.commit()
        return user

    allowed = settings.allowed_domains_list
    if allowed:
        domain = email.split("@")[-1].lower()
        if domain not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is not allowed for your email domain.",
            )

    user = User(
        email=email,
        password_hash=None,
        oauth_provider=provider,
        oauth_id=oauth_id,
        is_active=True,
    )
    db.add(user)
    db.flush()

    if settings.single_org_mode:
        if not settings.single_org_slug:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfiguration: SINGLE_ORG_SLUG is not set.",
            )
        org = db.query(Organization).filter(Organization.slug == settings.single_org_slug).first()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfiguration: default organization not found.",
            )
        user.current_organization_id = org.id
        membership = OrganizationMember(
            user_id=user.id, organization_id=org.id, role=OrganizationRole.MEMBER,
        )
        db.add(membership)
    else:
        org_name = f"{name}'s Organization" if name else f"{email.split('@')[0]}'s Organization"
        base_slug = _create_slug(org_name)
        slug = base_slug
        counter = 1
        while db.query(Organization).filter(Organization.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(id=uuid.uuid4(), name=org_name, slug=slug)
        db.add(org)
        db.flush()

        user.current_organization_id = org.id
        membership = OrganizationMember(
            user_id=user.id, organization_id=org.id, role=OrganizationRole.ADMIN,
        )
        db.add(membership)

    db.commit()
    db.refresh(user)
    return user


def _set_auth_cookies_and_respond(user: User, db: Session) -> dict:
    settings = get_settings()
    token_data = _build_token_data(user, db)
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    expires_at = int((
        datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    ).timestamp())

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


@router.get("/providers")
async def get_sso_providers():
    settings = get_settings()
    google_enabled = bool(settings.google_oauth_client_id)
    microsoft_enabled = hasattr(oauth, "microsoft") and oauth.microsoft is not None
    resp: dict = {
        "google": google_enabled,
        "microsoft": microsoft_enabled,
        "sso_only": settings.sso_only,
        "single_org_mode": settings.single_org_mode,
    }
    if google_enabled:
        resp["google_client_id"] = settings.google_oauth_client_id
    return resp


class GoogleTokenRequest(BaseModel):
    credential: str


@router.post("/google/token")
@limiter.limit("30/minute")
async def sso_google_verify_token(
    request: Request,
    body: GoogleTokenRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google Sign-In is not configured",
        )

    try:
        signing_key = _google_jwks_client.get_signing_key_from_jwt(body.credential)
        payload = pyjwt.decode(
            body.credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_oauth_client_id,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )
    except pyjwt.exceptions.PyJWTError as e:
        logger.warning("Google ID token validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential",
        )

    email = payload.get("email")
    if not email or not payload.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified",
        )

    user = _handle_sso_login(
        db, provider="google", oauth_id=payload["sub"], email=email, name=payload.get("name"),
    )

    tokens = _set_auth_cookies_and_respond(user, db)
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return tokens


@router.get("/microsoft")
@limiter.limit("10/minute")
async def sso_microsoft_login(request: Request, return_url: str | None = None):
    if not hasattr(oauth, "microsoft") or oauth.microsoft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Microsoft SSO not configured",
        )

    safe_return = _safe_return_url(return_url)
    request.session["sso_return_url"] = safe_return

    redirect_uri = _frontend_url("/api/v1/auth/sso/microsoft/callback")
    return await oauth.microsoft.authorize_redirect(request, redirect_uri)


@router.get("/microsoft/callback")
async def sso_microsoft_callback(request: Request, db: Session = Depends(get_db)):
    if not hasattr(oauth, "microsoft") or oauth.microsoft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Microsoft SSO not configured",
        )

    try:
        token = await oauth.microsoft.authorize_access_token(request)
    except Exception as e:
        logger.warning("Microsoft SSO token exchange failed: %s", e)
        return RedirectResponse(url=_frontend_url("/login?sso_error=token_exchange_failed"))

    userinfo = token.get("userinfo")
    if not userinfo:
        return RedirectResponse(url=_frontend_url("/login?sso_error=no_user_info"))

    email = userinfo.get("email") or userinfo.get("preferred_username")
    if not email:
        return RedirectResponse(url=_frontend_url("/login?sso_error=email_not_verified"))

    user = _handle_sso_login(
        db, provider="microsoft", oauth_id=userinfo["sub"], email=email, name=userinfo.get("name"),
    )

    token_data = _build_token_data(user, db)
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return_url = request.session.pop("sso_return_url", "/dashboard")
    redirect_url = _frontend_url(f"/auth/sso/complete?return_url={return_url}")

    resp = RedirectResponse(url=redirect_url, status_code=302)
    set_auth_cookies(resp, access_token, refresh_token)
    return resp
