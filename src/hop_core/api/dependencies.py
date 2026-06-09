"""FastAPI dependencies for authentication and authorization."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from dataclasses import dataclass
from uuid import UUID

from hop_core.db import get_db
from hop_core.models.user import User
from hop_core.models.organization import Organization, OrganizationMember
from hop_core.models.enums import OrganizationRole
from hop_core.core.security import decode_token
from hop_core.core.exceptions import AuthenticationError

security = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    if credentials and credentials.credentials:
        return credentials.credentials

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _validate_access_token(token: str, db: Session):
    try:
        payload = decode_token(token)

        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token payload")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise AuthenticationError("User not found")

        if not user.is_active:
            raise AuthenticationError("User is inactive")

        return user, payload

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@dataclass
class CurrentUserContext:
    user: User
    organization_id: Optional[UUID] = None
    organization: Optional[Organization] = None
    organization_role: Optional[OrganizationRole] = None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(request, credentials)
    user, _ = _validate_access_token(token, db)
    return user


async def get_current_user_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentUserContext:
    token = _extract_token(request, credentials)
    user, payload = _validate_access_token(token, db)

    org_id = payload.get("org_id")
    org = None
    org_role = None

    if org_id:
        membership = db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == org_id,
        ).first()

        if membership:
            org = db.query(Organization).filter(Organization.id == org_id).first()
            org_role = membership.role
    else:
        membership = db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user.id,
        ).first()

        if membership:
            org_id = membership.organization_id
            org = db.query(Organization).filter(Organization.id == org_id).first()
            org_role = membership.role

    return CurrentUserContext(
        user=user,
        organization_id=org_id,
        organization=org,
        organization_role=org_role,
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_active_user_with_org(
    context: CurrentUserContext = Depends(get_current_user_context),
) -> CurrentUserContext:
    if not context.user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    if not context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to an organization",
        )

    return context


async def require_org_admin(
    context: CurrentUserContext = Depends(get_current_active_user_with_org),
) -> CurrentUserContext:
    if context.organization_role != OrganizationRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return context


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user
