"""Signed, expiring tokens for the "unlock my account" email link.

The token is stateless: it carries the user id and an expiry, and is signed
with an HMAC so it cannot be forged. It is only sent to the account owner's
registered email address. Reusing a token is harmless because unlocking simply
clears the failure counter.
"""

import base64
import hashlib
import hmac
import json
import time

from .config import settings


def _secret() -> bytes:
    return (settings.unlock_secret or settings.supabase_service_role_key).encode()


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(body: str) -> str:
    digest = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return _b64e(digest)


def create_unlock_token(user_id: str, email: str, expires_at: int) -> str:
    """Return a signed token that unlocks `user_id` until `expires_at` (unix)."""
    payload = json.dumps(
        {"u": str(user_id), "e": email, "x": int(expires_at)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    body = _b64e(payload)
    return f"{body}.{_sign(body)}"


def verify_unlock_token(token: str, now: int | None = None) -> dict | None:
    """Return the token payload when valid and unexpired, else None."""
    try:
        body, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None

    if not hmac.compare_digest(signature, _sign(body)):
        return None

    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None

    if not isinstance(payload, dict) or "u" not in payload or "x" not in payload:
        return None

    current = int(now) if now is not None else int(time.time())
    if current > int(payload["x"]):
        return None

    return payload
