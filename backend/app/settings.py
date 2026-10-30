from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://donor_app:change-me@localhost:5432/donor_management"
    )
    jwt_secret_key: str = ""
    access_token_expire_minutes: int = 30
    frontend_origins: str = "http://localhost:5173,http://localhost:8443"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def razorpay_configured(self) -> bool:
        return self.razorpay_key_id.startswith("rzp_test_") and bool(self.razorpay_key_secret)


settings = Settings()
