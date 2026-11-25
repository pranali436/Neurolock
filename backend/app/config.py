from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = "http://localhost:5173"
    storage_bucket: str = "neurolock-files"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = ""
    email_js_service_id: str = ""
    email_js_template_id: str = ""
    email_js_public_key: str = ""
    email_js_private_key: str = ""
    # Sensitivity of the typing-rhythm (second factor) check. Configurable via
    # the BIOMETRIC_ACCURACY_THRESHOLD environment variable. This default is the
    # strict PRODUCTION value; development .env files use a slightly more
    # tolerant value (see .env.example) and are never changed implicitly.
    biometric_accuracy_threshold: float = 0.70
    # How long a completed typing-rhythm (second factor) check stays valid.
    biometric_token_ttl_seconds: int = 300
    # Base URL of this API, used to build the account-unlock link in emails.
    api_base_url: str = "http://localhost:8000"
    # Secret used to sign unlock tokens. Falls back to the service-role key.
    unlock_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parent.parent / ".env"),
        extra="ignore",
    )

settings = Settings()
