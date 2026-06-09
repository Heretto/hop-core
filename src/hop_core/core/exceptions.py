"""Core exceptions for hop-core applications."""

from typing import Any, Optional, Dict


class HopException(Exception):
    """Base exception for hop-core applications."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(HopException):
    """Authentication failed."""
    pass


class AuthorizationError(HopException):
    """User not authorized for this action."""
    pass


class CredentialError(HopException):
    """Credential-related error."""
    pass


class EmailNotConfiguredError(HopException):
    """Email/SMTP is not configured."""
    pass
