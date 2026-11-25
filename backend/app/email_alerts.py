import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from .config import settings

logger = logging.getLogger("neurolock.email_alerts")

_MAX_LOG_CHARS = 500
_SMTP_TIMEOUT_SECONDS = 15

_LOCKOUT_HTML = """\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#0f172a">
  <h2 style="color:#0f172a;margin-bottom:8px">Your NeuroLock account is locked</h2>
  <p>We detected <strong>3 failed sign-in attempts</strong> on your NeuroLock account,
  so it has been temporarily locked for about __MINUTES__ minute(s).</p>
  <p>If this was you, you can unlock it <strong>right now</strong> &mdash; no need to wait:</p>
  <p style="text-align:center;margin:28px 0">
    <a href="__UNLOCK_URL__"
       style="background:#2563eb;color:#ffffff;text-decoration:none;padding:14px 30px;
              border-radius:8px;font-weight:bold;display:inline-block;font-size:16px">
      Unlock my account
    </a>
  </p>
  <p style="font-size:13px;color:#64748b">If the button doesn't work, copy this link into
  your browser:<br><span style="word-break:break-all">__UNLOCK_URL__</span></p>
  <p style="font-size:13px;color:#64748b">If you did not try to sign in, do not click the link
  and consider resetting your password.</p>
  <p style="font-size:12px;color:#94a3b8">This link expires when the lockout window ends.</p>
</div>
"""


def _redact(value: object) -> str:
    """Return a short, log-safe string without configured email credentials."""
    text = "" if value is None else str(value)
    for secret in (settings.smtp_password, settings.email_js_private_key):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:_MAX_LOG_CHARS]


def _smtp_config_ready() -> bool:
    return bool(
        settings.smtp_username and settings.smtp_password and settings.sender_email
    )


def _emailjs_config_ready() -> bool:
    return bool(
        settings.email_js_service_id
        and settings.email_js_template_id
        and settings.email_js_public_key
    )


def _config_ready(event: str) -> bool:
    if _smtp_config_ready():
        return True
    if _emailjs_config_ready():
        return True
    logger.warning(
        "No email transport is configured for '%s'; skipping email.",
        event,
    )
    return False


def _send_emailjs(to_email: str, event: str, detail: str = "") -> bool:
    """Send using EmailJS REST API when the EmailJS credentials are configured."""
    if not _emailjs_config_ready():
        return False

    payload = {
        "service_id": settings.email_js_service_id,
        "template_id": settings.email_js_template_id,
        "user_id": settings.email_js_public_key,
        "template_params": {
            "to_email": to_email,
            "event": event,
            "detail": detail or "No additional details were provided.",
        },
    }
    if settings.email_js_private_key:
        payload["accessToken"] = settings.email_js_private_key

    req = urllib.request.Request(
        "https://api.emailjs.com/api/v1.0/email/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "NeuroLock/1.0 (EmailJS REST client)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_SMTP_TIMEOUT_SECONDS) as response:
            code = getattr(response, "status", 0)
            if code not in (200, 201, 202):
                logger.error(
                    "EmailJS rejected '%s' with HTTP %s.",
                    event,
                    code,
                )
                return False
    except urllib.error.HTTPError as exc:
        response_detail = exc.read().decode("utf-8", "replace")
        logger.error(
            "EmailJS rejected '%s' with HTTP %s: %s",
            event,
            exc.code,
            _redact(response_detail),
        )
        return False
    except Exception as exc:  # noqa: BLE001 - email must never break authentication
        logger.error(
            "EmailJS send failed for '%s': %s: %s",
            event,
            type(exc).__name__,
            _redact(exc),
        )
        return False

    logger.info("EmailJS accepted '%s'.", event)
    return True


def _deliver(message: EmailMessage, event: str) -> bool:
    """Send a message over Gmail SMTP. Never raises; returns True when accepted."""
    if not _smtp_config_ready():
        if _emailjs_config_ready():
            return _send_emailjs(
                message["To"],
                event,
                message.get_body(preferencelist=("plain",)).get_content(),
            )
        return False

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS
        ) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except Exception as exc:  # noqa: BLE001 - email must never break authentication
        logger.error(
            "SMTP send failed for '%s': %s: %s",
            event,
            type(exc).__name__,
            _redact(exc),
        )
        if _emailjs_config_ready():
            logger.info("Falling back to EmailJS for '%s'.", event)
            return _send_emailjs(message["To"], event, message.get_body(preferencelist=("plain",)).get_content())
        return False

    logger.info("SMTP accepted '%s'.", event)
    return True


def send_security_alert(to_email: str, event: str, detail: str = "") -> bool:
    """Send exactly one generic security alert email.

    Returns True when the selected transport accepted the message, False otherwise.
    This function never raises, so authentication still succeeds when email
    delivery fails. Secrets are never written to the logs.
    """
    if not _config_ready(event):
        return False

    if not to_email:
        logger.warning("No recipient for '%s'; skipping email.", event)
        return False

    if _emailjs_config_ready():
        if _send_emailjs(to_email, event, detail):
            return True
        logger.warning(
            "EmailJS failed for '%s'; falling back to SMTP if configured.",
            event,
        )

    if not _smtp_config_ready():
        return False

    message = EmailMessage()
    message["From"] = settings.sender_email
    message["To"] = to_email
    message["Subject"] = f"NeuroLock security alert: {event}"
    message.set_content(
        f"A NeuroLock security event occurred: {event}.\n"
        f"{detail}\n\nIf this wasn't you, sign in to your account and review your security."
    )
    return _deliver(message, event)


def send_lockout_email(to_email: str, unlock_url: str, unlock_minutes: int) -> bool:
    """Send the account-locked email containing a one-click unlock button."""
    event = "account lockout"
    if not _config_ready(event):
        return False

    if not to_email:
        logger.warning("No recipient for '%s'; skipping email.", event)
        return False

    if _emailjs_config_ready():
        if _send_emailjs(
            to_email,
            event,
            f"Your NeuroLock account is temporarily locked after 3 failed sign-in attempts. Unlock here: {unlock_url}",
        ):
            return True
        logger.warning(
            "EmailJS failed for '%s'; falling back to SMTP if configured.",
            event,
        )

    if not _smtp_config_ready():
        return False

    html = (
        _LOCKOUT_HTML
        .replace("__UNLOCK_URL__", unlock_url)
        .replace("__MINUTES__", str(unlock_minutes))
    )
    plain = (
        "Your NeuroLock account is temporarily locked after 3 failed sign-in "
        f"attempts (about {unlock_minutes} minute(s)).\n\n"
        "You can unlock it right now using this link:\n"
        f"{unlock_url}\n\n"
        "If you did not try to sign in, ignore this email and consider "
        "resetting your password."
    )

    message = EmailMessage()
    message["From"] = settings.sender_email
    message["To"] = to_email
    message["Subject"] = "Your NeuroLock account is locked - unlock now"
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    return _deliver(message, event)
