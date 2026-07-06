"""Authentication, encryption, and security utilities.

All settings access is lazy — no module-level get_settings() calls.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
import ipaddress
import socket
from urllib.parse import urlparse

import jwt
import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import json

from hop_core.core.exceptions import AuthenticationError

_ENCRYPTION_SALT = b"release-notes-agent-credential-encryption"

# Lazy Fernet singletons
_fernet = None
_legacy_fernet = None


def _derive_fernet_key(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_ENCRYPTION_SALT,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _derive_legacy_fernet_key(passphrase: str) -> bytes:
    return base64.urlsafe_b64encode(passphrase.encode()[:32].ljust(32, b'0'))


def _get_fernet():
    global _fernet, _legacy_fernet
    if _fernet is None:
        from hop_core.config import get_settings
        settings = get_settings()
        if len(settings.encryption_key) < 16:
            raise ValueError(
                "ENCRYPTION_KEY must be at least 16 characters. "
                "Generate a strong key, e.g.: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        _fernet = Fernet(_derive_fernet_key(settings.encryption_key))
        _legacy_fernet = Fernet(_derive_legacy_fernet_key(settings.encryption_key))
    return _fernet, _legacy_fernet


def _get_jwt_settings():
    from hop_core.config import get_settings
    settings = get_settings()
    return settings.jwt_secret_key, settings.jwt_algorithm


# --- Password hashing ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# --- JWT tokens ---

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    from hop_core.config import get_settings
    settings = get_settings()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    secret, algorithm = _get_jwt_settings()
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def create_refresh_token(data: Dict[str, Any]) -> str:
    from hop_core.config import get_settings
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    secret, algorithm = _get_jwt_settings()
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        secret, algorithm = _get_jwt_settings()
        return jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid token")


def create_password_reset_token(email: str) -> str:
    from hop_core.config import get_settings
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.password_reset_token_expire_minutes)
    to_encode = {"sub": email, "type": "password_reset", "exp": expire}
    secret, algorithm = _get_jwt_settings()
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def decode_password_reset_token(token: str) -> str:
    try:
        secret, algorithm = _get_jwt_settings()
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        if payload.get("type") != "password_reset":
            raise AuthenticationError("Invalid token type")
        email = payload.get("sub")
        if not email:
            raise AuthenticationError("Invalid token")
        return email
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Password reset link has expired")
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid password reset token")


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# --- Cookie management ---

def set_auth_cookies(response, access_token: str, refresh_token: str) -> None:
    from hop_core.config import get_settings
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        key="csrf_token",
        value=generate_csrf_token(),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        domain=settings.cookie_domain,
    )


def clear_auth_cookies(response) -> None:
    from hop_core.config import get_settings
    settings = get_settings()
    response.delete_cookie(key="access_token", path="/api/v1", domain=settings.cookie_domain)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth", domain=settings.cookie_domain)
    response.delete_cookie(key="csrf_token", path="/", domain=settings.cookie_domain)


# --- Credential encryption ---

def encrypt_credentials(credentials: Dict[str, Any]) -> bytes:
    fernet, _ = _get_fernet()
    return fernet.encrypt(json.dumps(credentials).encode())


def decrypt_credentials(encrypted_data: bytes) -> Dict[str, Any]:
    fernet, legacy_fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(encrypted_data)
        return json.loads(decrypted.decode())
    except InvalidToken:
        decrypted = legacy_fernet.decrypt(encrypted_data)
        return json.loads(decrypted.decode())


# --- SSRF protection ---

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_server_url(url: str) -> str:
    """Validate a user-supplied server URL to prevent SSRF."""
    from hop_core.config import get_settings
    settings = get_settings()

    parsed = urlparse(url)

    allowed_schemes = ("https",)
    if settings.app_env == "development":
        allowed_schemes = ("https", "http")
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL must use {' or '.join(allowed_schemes)}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")

    try:
        addrinfos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for family, _, _, _, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError("URL must not point to a private or internal address")

    return url
