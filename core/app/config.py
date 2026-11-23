"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    public_url: str = "http://localhost:3000"
    secret_key: str = "change-me-in-production-please-use-64-random-chars"
    database_url: str = "postgresql+psycopg://talentmatch:talentmatch@localhost:5432/talentmatch"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"

    # sessions
    session_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    magic_link_days: int = 30

    # background tasks: when true, tasks run inline (tests, single-process dev)
    tasks_eager: bool = False

    # storage
    storage_backend: str = "local"  # local | s3
    storage_dir: str = "./var/storage"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-central"
    max_upload_mb: int = 10

    # AI providers. Without a key the platform runs in rule-based "degraded" mode.
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    llm_model: str = "mistral-small-latest"
    ocr_model: str = "mistral-ocr-latest"
    embeddings_provider: str = "hash"  # hash | bge-m3 | mistral
    embedding_dim: int = 1024
    sem_low: float = 0.05   # cosine mapped to 0 (calibrated per embeddings provider)
    sem_high: float = 0.55  # cosine mapped to 1
    ai_daily_cv_cap_per_org: int = 2000
    ai_daily_chat_cap_per_org: int = 300

    # e-mail (SMTP, e.g. Brevo). Empty host = log to console.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "TalentMatch <no-reply@talentmatch.local>"

    # anti-abuse
    turnstile_secret: str = ""
    clamav_host: str = ""
    clamav_port: int = 3310
    rate_limit_enabled: bool = True

    # GDPR
    notice_version: str = "2026-11"
    retention_months: int = 24
    erasure_days: int = 30
    reject_undo_minutes: int = 10

    # bootstrap admin (created by `tm bootstrap`)
    admin_email: str = ""
    admin_password: str = ""

    sentry_dsn: str = ""

    @property
    def is_prod(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
