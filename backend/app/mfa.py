"""Short-lived, server-signed proof that the typing-rhythm second factor passed.

This token is the completed-second-factor state. It is stateless: it carries the
user id, a fixed purpose marker and an expiry, and is signed with an HMAC so a
client cannot forge or edit it. It is issued ONLY by POST /api/biometric/verify
after the server-side matcher has passed, and is required (alongside the
Supabase session token) by every second-factor-protected endpoint.

Because the decision lives in this signed, expiring token, a client cannot gain
access by sending a boolean or an accuracy percentage of its own.
"""

import base64
import hashlib
import hmac
import json
import time

from .config import settings

PURPOSE = "biometric"


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


def create_biometric_token(
    user_id: str,
    ttl_seconds: int | None = None,
    now: int | None = None,
) -> str:
    """Return a signed token proving `user_id` completed the second factor."""
    issued = int(now) if now is not None else int(time.time())
    ttl = int(
        ttl_seconds
        if ttl_seconds is not None
        else settings.biometric_token_ttl_seconds
    )
    payload = json.dumps(
        {"sub": str(user_id), "p": PURPOSE, "iat": issued, "x": issued + ttl},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    body = _b64e(payload)
    return f"{body}.{_sign(body)}"


def verify_biometric_token(
    token: str | None,
    expected_user_id: str | None = None,
    now: int | None = None,
) -> dict | None:
    """Return the payload when the token is authentic, unexpired and, if
    `expected_user_id` is given, belongs to that user. Otherwise return None."""
    if not token or not isinstance(token, str):
        return None

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

    if (
        not isinstance(payload, dict)
        or payload.get("p") != PURPOSE
        or "sub" not in payload
        or "x" not in payload
    ):
        return None

    current = int(now) if now is not None else int(time.time())
    if current > int(payload["x"]):
        return None

    if expected_user_id is not None and str(payload["sub"]) != str(expected_user_id):
        return None

    return payload
