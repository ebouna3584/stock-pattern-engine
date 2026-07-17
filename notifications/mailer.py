"""
Email sending via Resend. Degrades gracefully with no API key set — logs the
email instead of sending, so local dev/signup flows still work end-to-end
without a Resend account.
"""
import logging

from api.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning(f"RESEND_API_KEY not set — skipping send. Would have emailed {to}: {subject}")
        return False
    try:
        import resend
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as exc:
        logger.error(f"Email send failed for {to}: {exc}")
        return False


def send_verification_email(to: str, token: str) -> bool:
    link = f"{settings.APP_BASE_URL}/api/v1/auth/verify?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
      <h2>Confirm your email</h2>
      <p>Click below to verify your Stock Pattern Engine account:</p>
      <p><a href="{link}" style="display:inline-block;background:#3b82f6;color:#fff;
         padding:10px 20px;border-radius:6px;text-decoration:none;">Verify Email</a></p>
      <p style="color:#64748b;font-size:12px;">If you didn't sign up, you can ignore this email.</p>
    </div>
    """
    return send_email(to, "Verify your email — Stock Pattern Engine", html)
