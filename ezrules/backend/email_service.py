import logging
import smtplib
from email.message import EmailMessage

from ezrules.settings import app_settings

logger = logging.getLogger(__name__)


def _require_email_config() -> None:
    if not app_settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")
    if not app_settings.FROM_EMAIL:
        raise RuntimeError("FROM_EMAIL is not configured")


def _send_email(recipient: str, subject: str, body: str) -> None:
    if app_settings.TESTING:
        logger.info("Skipping SMTP send in testing mode for %s", recipient)
        return

    _require_email_config()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = app_settings.FROM_EMAIL
    message["To"] = recipient
    message.set_content(body)

    smtp_user = app_settings.SMTP_USER or None
    smtp_password = app_settings.SMTP_PASSWORD or None

    with smtplib.SMTP(str(app_settings.SMTP_HOST), int(app_settings.SMTP_PORT)) as smtp:
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        else:
            logger.warning(
                "SMTP server %s:%s does not support STARTTLS; sending without TLS",
                app_settings.SMTP_HOST,
                app_settings.SMTP_PORT,
            )
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def send_invitation_email(recipient_email: str, token: str) -> None:
    invite_link = f"{app_settings.APP_BASE_URL.rstrip('/')}/accept-invite?token={token}"
    body = (
        "You have been invited to ezrules.\n\n"
        "Use the link below to accept your invitation and set your password:\n"
        f"{invite_link}\n\n"
        "If you did not expect this invitation, you can ignore this email."
    )
    _send_email(recipient_email, "You are invited to ezrules", body)


def send_password_reset_email(recipient_email: str, token: str) -> None:
    reset_link = f"{app_settings.APP_BASE_URL.rstrip('/')}/reset-password?token={token}"
    body = (
        "A password reset was requested for your ezrules account.\n\n"
        "Use the link below to set a new password:\n"
        f"{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    _send_email(recipient_email, "Reset your ezrules password", body)
