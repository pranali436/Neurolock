from fastapi import Depends, Header, HTTPException
from .supabase_client import auth_client
from .mfa import verify_biometric_token

def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in first.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        response = auth_client.auth.get_user(token)
        user = response.user
        if not user:
            raise ValueError("No user")
        return {"id": str(user.id), "email": user.email or ""}
    except Exception:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired. Please sign in again.")


def verified_user(
    user: dict = Depends(current_user),
    x_biometric_token: str | None = Header(default=None, alias="X-Biometric-Token"),
) -> dict:
    """First factor (Supabase session) AND a valid, server-issued second-factor
    token bound to the same user. This is the gate for protected endpoints; the
    decision is enforced here on the server, not by frontend navigation."""
    payload = verify_biometric_token(x_biometric_token, expected_user_id=user["id"])
    if not payload:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "biometric_required",
                "message": "Complete typing-rhythm verification before accessing this resource.",
            },
        )
    return {
        "id": user["id"],
        "email": user["email"],
        "biometric_expires_at": int(payload["x"]),
    }
