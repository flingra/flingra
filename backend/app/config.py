from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLINGRA_",
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str = ""
    migration_database_url: str | None = None
    db_host: str | None = None
    db_port: int = 3306
    db_name: str | None = None
    db_user: str | None = None
    db_password: SecretStr | None = None
    db_ssl_mode: str = "REQUIRED"
    db_ssl_ca: Path | None = None
    session_cookie_name: str = "flingra_session"
    session_ttl_hours: int = 720
    admin_session_ttl_hours: int = Field(default=8, ge=1, le=24)
    session_cookie_secure: bool = True
    allowed_origins: list[str] = Field(default_factory=list)
    admin_allowed_origins: list[str] = Field(default_factory=list)
    rate_limit_redis_url: SecretStr | None = None
    rate_limiting_enabled: bool = True
    demo_profiles_enabled: bool = False
    max_request_bytes: int = Field(default=1_048_576, ge=1)
    google_client_id: str | None = None
    opencage_api_key: SecretStr | None = None
    payment_provider: str | None = None
    paystack_secret_key: SecretStr | None = None
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: SecretStr | None = None
    media_upload_max_bytes: int = Field(default=10_485_760, ge=1)
    brevo_api_key: SecretStr | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "Flingra"
    frontend_url: str = "http://localhost:5173"
    terms_version: str = "v1"
    privacy_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
