"""Async email service using SMTP."""

import logging
from email.message import EmailMessage

import aiosmtplib

from hop_core.config import get_settings
from hop_core.core.exceptions import EmailNotConfiguredError

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, html_body: str) -> None:
    """Send an email via SMTP. Raises EmailNotConfiguredError if SMTP is not set up."""
    settings = get_settings()
    if not settings.smtp_configured:
        raise EmailNotConfiguredError("SMTP is not configured")

    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
    logger.info("Email sent to %s: %s", to_email, subject)


async def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """Send a password reset email with a link containing the token."""
    settings = get_settings()
    reset_url = f"{settings.frontend_base_url}/reset-password?token={reset_token}"
    html_body = f"""\
<h2>Password Reset Request</h2>
<p>You requested a password reset for your account.</p>
<p><a href="{reset_url}">Click here to reset your password</a></p>
<p>This link expires in {settings.password_reset_token_expire_minutes} minutes.</p>
<p>If you did not request this, you can safely ignore this email.</p>
"""
    await send_email(to_email, "Password Reset", html_body)
