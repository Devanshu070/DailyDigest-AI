"""
config.py — Application configuration via pydantic-settings.

Reads from environment variables / .env file.
All settings are validated at startup — a missing required var raises immediately.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Groq
    groq_api_key: str

    # Resend — email delivery
    resend_api_key: str

    # Digest delivery
    # All recipient emails live here — edit this to change who gets the digest.
    # For multiple recipients in the future, this could become a DB table.
    digest_recipient_email: str

    @property
    def sqlalchemy_database_url(self) -> str:
        """
        Cloud platforms (like Render/Heroku) inject URLs starting with 'postgres://'.
        SQLAlchemy 2.0 crashes unless it is exactly 'postgresql://'.
        This intercepts and fixes the cloud-injected string silently.
        """
        return self.database_url.replace("postgres://", "postgresql://", 1)


settings = Settings()
