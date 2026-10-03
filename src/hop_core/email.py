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


async def send_verification_email(to_email: str, verification_token: str) -> None:
    """Send the link that confirms an account's email address.

    In development with no SMTP configured, the link is logged instead so the
    flow can be exercised locally; elsewhere startup refuses that combination.
    """
    settings = get_settings()
    verify_url = f"{settings.frontend_base_url}/verify-email?token={verification_token}"
    if not settings.smtp_configured and settings.app_env == "development":
        logger.warning("SMTP not configured; email verification link for %s: %s", to_email, verify_url)
        return
    html_body = f"""\
<h2>Confirm your email address</h2>
<p>Confirm this address to finish setting up your account.</p>
<p><a href="{verify_url}">Click here to verify your email</a></p>
<p>This link expires in {settings.email_verification_token_expire_hours} hours.</p>
<p>If you did not create an account, you can safely ignore this email.</p>
"""
    await send_email(to_email, "Verify your email address", html_body)
