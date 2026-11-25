import time

from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
from .config import settings
from .auth import current_user
from .supabase_client import admin, auth_client
from .biometrics import summarize, distance, validate_features
from .typing_analysis import TYPING_SAMPLES, analyze_test
from .email_alerts import send_lockout_email, send_security_alert
from .unlock import create_unlock_token, verify_unlock_token
from .mfa import create_biometric_token, verify_biometric_token


def record_failure_and_alert(user: dict, failure_type: str) -> None:
    """Record an authentication failure and email on the third failure."""
    try:
        result = admin.rpc(
            "record_auth_failure",
            {
                "p_user_id": user["id"],
                "p_failure_type": failure_type,
            },
        ).execute()

        rows = result.data or []
        if not rows or not rows[0].get("should_alert"):
            return

        event = (
            "Three failed password login attempts"
            if failure_type == "password"
            else "Three failed typing verification attempts"
        )

        try:
            sent = send_security_alert(
                user["email"],
                event,
                "Three failed attempts were recorded within 15 minutes. "
                "If this wasn't you, review your account security.",
            )
        except Exception:
            sent = False

        admin.table("security_events").insert({
            "user_id": user["id"],
            "event_type": f"{failure_type}_failure_threshold_reached",
            "details": {"email_sent": sent},
        }).execute()

    except Exception:
        # Do not expose internal database or email details to users.
        # Production deployments should also record a sanitized server log.
        pass


app = FastAPI(title="NeuroLock API", version="1.0.0")

origins = [
    x.strip()
    for x in settings.allowed_origins.split(",")
    if x.strip()
]

for origin in [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]:
    if origin not in origins:
        origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class Sample(BaseModel):
    features: dict

class EnrollmentRequest(BaseModel):
    samples: list[Sample] = Field(min_length=3, max_length=3)

class VerifyRequest(BaseModel):
    samples: list[Sample] = Field(min_length=3, max_length=3)

class TypingEvent(BaseModel):
    kind: Literal["keydown", "keyup"]
    key: str = Field(min_length=1, max_length=16)
    code: str = Field(min_length=1, max_length=32)
    time_ms: float = Field(ge=0, le=300_000)
    repeat: bool = False

class TypingAttempt(BaseModel):
    typed_text: str = Field(max_length=120)
    events: list[TypingEvent] = Field(max_length=1200)

class TypingAnalysisRequest(BaseModel):
    samples: list[TypingAttempt] = Field(min_length=3, max_length=3)

class AlertRequest(BaseModel):
    event: str = "Security notification"
    detail: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str 


def typing_test_completed(user_id: str) -> bool:
    """Return whether the user has completed all three typing samples."""
    try:
        result = (
            admin.table("security_events")
            .select("details")
            .eq("user_id", user_id)
            .eq("event_type", "typing_analysis_completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return False
        details = rows[0].get("details") or {}
        if isinstance(details, dict):
            return bool(details.get("complete", True))
        return bool(details)
    except Exception:
        return False


def record_password_failure(email: str) -> None:
    """Record a genuine failed login and alert on the third failure."""
    try:
        result = admin.rpc(
            "record_password_failure_by_email",
            {"p_email": email},
        ).execute()

        rows = result.data or []
        if not rows or not rows[0].get("should_alert"):
            return

        row = rows[0]
        user_id = str(row["user_id"])
        registered_email = row["user_email"]

        # The 3rd failure locks the account. Email the owner an unlock link that
        # stays valid until the lockout window ends, so they can get back in
        # early without waiting the full 15 minutes.
        lockout = password_lockout(registered_email)
        retry_seconds = (
            int(lockout["retry_after"]) if lockout else LOCKOUT_WINDOW_MINUTES * 60
        )
        retry_seconds = max(retry_seconds, 0)
        unlock_minutes = max(1, (retry_seconds + 59) // 60)
        token = create_unlock_token(
            user_id, registered_email, int(time.time()) + retry_seconds
        )
        unlock_url = f"{settings.api_base_url.rstrip('/')}/api/unlock?token={token}"

        try:
            sent = send_lockout_email(registered_email, unlock_url, unlock_minutes)
        except Exception:
            sent = False

        admin.table("security_events").insert({
            "user_id": user_id,
            "event_type": "password_failure_threshold_reached",
            "details": {"email_sent": sent, "unlock_minutes": unlock_minutes},
        }).execute()

    except Exception:
        # Do not expose internal database or email errors to the user.
        pass


LOCKOUT_FAILURE_LIMIT = 3
LOCKOUT_WINDOW_MINUTES = 15


def password_lockout(email: str) -> dict | None:
    """Return lockout details when the account is temporarily locked, else None."""
    try:
        result = admin.rpc(
            "get_password_lockout_by_email",
            {"p_email": email},
        ).execute()
    except Exception:
        # Fail open: a broken check must not block a legitimate sign-in.
        return None

    rows = result.data or []
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return None

    row = rows[0]
    if not row.get("locked"):
        return None

    return {
        "failure_count": row.get("failure_count"),
        "retry_after": max(int(row.get("retry_after_seconds") or 0), 0),
    }


@app.post("/api/login")
def login(payload: LoginRequest):
    email = payload.email.strip()

    # Temporary lockout: check before any authentication attempt.
    lockout = password_lockout(email)
    if lockout:
        wait_minutes = max(1, (lockout["retry_after"] + 59) // 60)
        raise HTTPException(
            status_code=423,
            detail=(
                "Account temporarily locked after too many failed login attempts. "
                f"Please try again in about {wait_minutes} minute"
                f"{'' if wait_minutes == 1 else 's'}."
            ),
            headers={"Retry-After": str(lockout["retry_after"])},
        )

    try:
        response = auth_client.auth.sign_in_with_password({
            "email": email,
            "password": payload.password,
        })
    except Exception as exc:
        # Supabase auth exposes a stable error `code`; fall back to the message
        # for older clients that do not set it.
        error_code = getattr(exc, "code", None)
        error_message = str(exc).lower()

        # Count only the normal invalid-credentials response. All other errors
        # must not be treated as wrong-password attempts.
        if error_code == "invalid_credentials" or "invalid login credentials" in error_message:
            record_password_failure(email)
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password.",
            )

        # A registered account whose email has not been confirmed yet. Email
        # confirmation is not bypassed; the user is told the concrete next step
        # instead of a misleading "temporarily unavailable" message.
        if error_code == "email_not_confirmed" or "email not confirmed" in error_message:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Your email address has not been confirmed yet. Open the "
                    "confirmation link we emailed you, or use the password reset "
                    "link to verify your email and set a new password."
                ),
            )

        # Rate limits, network failures, or other unexpected errors.
        raise HTTPException(
            status_code=503,
            detail="Sign-in is temporarily unavailable. Please try again.",
        )

    if not response.user or not response.session:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    # A successful login resets the password-failure counter.
    try:
        admin.rpc(
            "reset_auth_failure",
            {
                "p_user_id": str(response.user.id),
                "p_failure_type": "password",
            },
        ).execute()
    except Exception:
        pass

    # Notify the registered account owner after successful login.
    try:
        sent = send_security_alert(
            response.user.email or "",
            "Successful login to NeuroLock",
            "A successful login to your NeuroLock account was detected. "
            "If this wasn't you, please review your account security.",
        )

        admin.table("security_events").insert({
            "user_id": str(response.user.id),
            "event_type": "successful_login",
            "details": {"email_sent": sent},
        }).execute()
    except Exception:
        pass

    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "token_type": "bearer",
        # Password authentication is the only gate now; typing verification is
        # no longer part of the sign-in flow.
        "biometric_required": False,
        "biometric_verified": False,
        "user": {
            "id": str(response.user.id),
            "email": response.user.email or "",
        },
    }


_UNLOCK_PAGE = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>__TITLE__</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#0f172a;margin:0;
             display:flex;align-items:center;justify-content:center;min-height:100vh">
  <div style="background:#ffffff;max-width:440px;width:90%;padding:36px;border-radius:14px;
              text-align:center;box-shadow:0 10px 30px rgba(0,0,0,.3)">
    <h1 style="margin:0 0 12px;font-size:22px;color:__COLOR__">__TITLE__</h1>
    <p style="color:#475569;line-height:1.5">__MESSAGE__</p>
    <p style="margin-top:28px">
      <a href="__SIGN_IN_URL__"
         style="background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 26px;
                border-radius:8px;font-weight:bold;display:inline-block">Go to NeuroLock</a>
    </p>
  </div>
</body>
</html>
"""


def _unlock_page(title: str, message: str, ok: bool) -> str:
    return (
        _UNLOCK_PAGE
        .replace("__TITLE__", title)
        .replace("__MESSAGE__", message)
        .replace("__COLOR__", "#16a34a" if ok else "#dc2626")
        .replace("__SIGN_IN_URL__", settings.frontend_url)
    )


@app.get("/api/unlock", response_class=HTMLResponse)
def unlock(token: str):
    payload = verify_unlock_token(token)
    if not payload:
        return _unlock_page(
            "This unlock link is not valid",
            "The link is invalid or has expired. Wait for the lockout window to "
            "end, then sign in again.",
            ok=False,
        )

    user_id = str(payload["u"])
    try:
        admin.rpc(
            "reset_auth_failure",
            {"p_user_id": user_id, "p_failure_type": "password"},
        ).execute()
    except Exception:
        return _unlock_page(
            "We couldn't unlock your account",
            "Something went wrong. Please open the link again in a moment.",
            ok=False,
        )

    try:
        admin.table("security_events").insert({
            "user_id": user_id,
            "event_type": "account_unlocked_via_email",
            "details": {"email": payload.get("e")},
        }).execute()
    except Exception:
        pass

    return _unlock_page(
        "Account unlocked",
        "Your NeuroLock account has been unlocked. You can sign in right now.",
        ok=True,
    )


@app.post("/api/test-email")
def test_email(user: dict = Depends(current_user)):
    if (
        not settings.smtp_username
        or not settings.smtp_password
        or not settings.sender_email
    ):
        raise HTTPException(
            status_code=500,
            detail="Email (SMTP) configuration is missing."
        )

    # Send to the signed-in account's own email; no recipient is hardcoded.
    sent = send_security_alert(
        user["email"],
        "NeuroLock test email",
        "Gmail SMTP is connected to NeuroLock. This is a test security alert."
    )

    if not sent:
        raise HTTPException(
            status_code=502,
            detail="The test email could not be sent."
        )

    return {"ok": True, "message": "Test email sent."}

@app.get("/health")
def health():
    return {"status": "ok", "service": "neurolock-api"}

@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "email": user["email"]}

@app.get("/api/auth/status")
def auth_status(
    user: dict = Depends(current_user),
    x_biometric_token: str | None = Header(default=None, alias="X-Biometric-Token"),
):
    """Legacy second-factor status endpoint, kept for API compatibility.
    Typing verification no longer gates any protected endpoint."""
    payload = verify_biometric_token(x_biometric_token, expected_user_id=user["id"])
    remaining = max(0, int(payload["x"]) - int(time.time())) if payload else None
    return {"biometric_verified": bool(payload), "expires_in_seconds": remaining}

@app.post("/api/enrollment")
def enroll(
    payload: EnrollmentRequest,
    user: dict = Depends(current_user),
):
    # Typing verification is disabled, so enrollment (including re-enrollment)
    # is available with the signed-in password session alone.
    vector = summarize([s.model_dump() for s in payload.samples])
    admin.table("keystroke_templates").upsert({
        "user_id": user["id"],
        "feature_vector": vector,
        "sample_count": len(payload.samples),
    }).execute()
    admin.table("security_events").insert({
        "user_id": user["id"], "event_type": "biometric_enrollment",
        "details": {"sample_count": len(payload.samples)}
    }).execute()
    return {"ok": True, "message": "Typing pattern enrolled.", "samples": len(payload.samples)}

@app.get("/api/biometric/status")
def biometric_status(user: dict = Depends(current_user)):
    row = (
        admin.table("keystroke_templates")
        .select("user_id")
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    return {"enrolled": bool(row and row.data)}

@app.post("/api/typing-analysis")
def typing_analysis(
    payload: TypingAnalysisRequest,
    user: dict = Depends(current_user),
):
    """Analyze the three public typing prompts without storing their event traces."""
    row = (
        admin.table("keystroke_templates")
        .select("feature_vector")
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    baseline = row.data.get("feature_vector") if row and row.data else None
    result = analyze_test(
        [sample.model_dump() for sample in payload.samples],
        TYPING_SAMPLES,
        baseline,
    )
    if result.get("complete"):
        try:
            admin.table("security_events").insert({
                "user_id": user["id"],
                "event_type": "typing_analysis_completed",
                "details": {"complete": True, "samples": len(payload.samples)}
            }).execute()
        except Exception:
            pass
    return result


@app.get("/api/typing-analysis/status")
def typing_analysis_status(user: dict = Depends(current_user)):
    """Return whether the current user has completed all three typing samples."""
    return {"complete": typing_test_completed(user["id"]), "samples_required": 3}


@app.get("/api/biometric/last-score")
def last_biometric_score(user: dict = Depends(current_user)):
    """Accuracy from the user's most recent real typing verification.

    Returns null when the account has never completed one, so the dashboard can
    show "Not available" instead of inventing a value.
    """
    result = (
        admin.table("security_events")
        .select("details,created_at")
        .eq("user_id", user["id"])
        .eq("event_type", "biometric_check_passed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"accuracy": None}
    details = rows[0].get("details") or {}
    accuracy = details.get("accuracy") if isinstance(details, dict) else None
    if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)):
        accuracy = None
    return {"accuracy": accuracy}


@app.post("/api/biometric/verify")
def verify(payload: VerifyRequest, user: dict = Depends(current_user)):
    row = admin.table("keystroke_templates").select("feature_vector").eq("user_id", user["id"]).maybe_single().execute()
    if not row.data:
        raise HTTPException(
            status_code=409,
            detail=(
                "You have not enrolled a typing pattern yet. Create your typing "
                "baseline on the enrollment page, then come back to verify."
            ),
        )
    # Insufficient/malformed probe data is rejected (HTTP 400) before scoring so
    # it can never be treated as a match.
    probe = summarize([sample.model_dump() for sample in payload.samples])
    score = distance(row.data["feature_vector"], probe)
    accuracy = round(1.0 - score, 4)
    required = round(settings.biometric_accuracy_threshold * 100)
    passed = accuracy >= settings.biometric_accuracy_threshold
    admin.table("security_events").insert({
        "user_id": user["id"],
        "event_type": "biometric_check_passed" if passed else "biometric_check_failed",
        "details": {"distance": round(score, 4), "accuracy": accuracy}
    }).execute()

    
    if not passed:
        record_failure_and_alert(user, "biometric")
        # Return the real scoreboard so the client can show the user exactly how
        # close they were and invite a retry. This is a mismatch, not a missing
        # second factor, so it must NOT carry the "biometric_required" code.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "biometric_mismatch",
                "message": (
                    f"Typing rhythm did not match closely enough. You scored "
                    f"{round(accuracy * 100)}% and {required}% is required. "
                    "Try again at your normal pace."
                ),
                "accuracy": accuracy,
                "required_accuracy": settings.biometric_accuracy_threshold,
                "distance": round(score, 4),
            },
        )

    try:
        admin.rpc(
            "reset_auth_failure",
            {
                "p_user_id": user["id"],
                "p_failure_type": "biometric",
            },
        ).execute()
    except Exception:
        pass

    # Issue the short-lived, server-signed second-factor token. Only the server
    # can mint this, and protected endpoints verify it independently.
    biometric_token = create_biometric_token(user["id"])
    return {
        "ok": True,
        "distance": round(score, 4),
        "accuracy": accuracy,
        "required_accuracy": settings.biometric_accuracy_threshold,
        "biometric_token": biometric_token,
        "expires_in": settings.biometric_token_ttl_seconds,
        "message": "Typing pattern matched."
    }


@app.get("/api/files")
def list_files(user: dict = Depends(current_user)):
    result = admin.table("user_files").select("id,original_name,content_type,size_bytes,created_at").eq("user_id", user["id"]).order("created_at", desc=True).execute()
    return {"files": result.data or []}

@app.post("/api/files")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(current_user)):
    if not typing_test_completed(user["id"]):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "typing_required",
                "message": "Complete all three typing samples before uploading files. Open the Typing Analysis page to finish the test.",
            },
        )

    # Development limits. Add malware scanning and stricter MIME validation before production.
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Maximum file size is 50 MB.")
    safe_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    object_path = f'{user["id"]}/{uuid4().hex}_{safe_name}'
    try:
        admin.storage.from_(settings.storage_bucket).upload(
            object_path, content,
            {"content-type": file.content_type or "application/octet-stream", "upsert": "false"}
        )
        saved = admin.table("user_files").insert({
            "user_id": user["id"], "original_name": safe_name,
            "object_path": object_path, "content_type": file.content_type or "application/octet-stream",
            "size_bytes": len(content)
        }).execute()
        return {"ok": True, "file": saved.data[0] if saved.data else {"original_name": safe_name}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Upload failed. Check private storage bucket and backend logs.") from exc

@app.post("/api/files/{file_id}/signed-url")
def signed_file_url(file_id: str, user: dict = Depends(current_user)):
    row = admin.table("user_files").select("object_path,original_name").eq("id", file_id).eq("user_id", user["id"]).maybe_single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        result = admin.storage.from_(settings.storage_bucket).create_signed_url(row.data["object_path"], 60)
        signed = result.get("signedURL") or result.get("signedUrl")
        if not signed:
            raise ValueError("No signed URL returned")
        return {"url": signed, "expires_in": 60, "filename": row.data["original_name"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create secure download link.") from exc

@app.delete("/api/files/{file_id}")
def delete_file(file_id: str, user: dict = Depends(current_user)):
    row = admin.table("user_files").select("object_path").eq("id", file_id).eq("user_id", user["id"]).maybe_single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        admin.storage.from_(settings.storage_bucket).remove([row.data["object_path"]])
        admin.table("user_files").delete().eq("id", file_id).eq("user_id", user["id"]).execute()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not delete file.") from exc

@app.post("/api/security-alert")
def security_alert(payload: AlertRequest, user: dict = Depends(current_user)):
    try:
        sent = send_security_alert(user["email"], payload.event[:120], payload.detail[:500])
    except Exception:
        sent = False
    admin.table("security_events").insert({
        "user_id": user["id"], "event_type": "security_alert_requested",
        "details": {"event": payload.event[:120], "email_sent": sent}
    }).execute()
    return {"ok": True, "email_sent": sent, "message": "Alert recorded." if not sent else "Alert email sent."}
