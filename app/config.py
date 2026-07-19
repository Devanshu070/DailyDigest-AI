"""
config.py — Application configuration via pydantic-settings.

Reads from environment variables / .env file.
All settings are validated at startup — a missing required var raises immediately.
"""

import re
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_cron_part(index: int, fallback: int) -> int:
    """Dynamically extracts a time part from the GitHub Actions cron schedule (0=minute, 1=hour)."""
    workflow_path = Path(__file__).parent.parent / ".github/workflows/daily_digest.yml"
    if workflow_path.exists():
        content = workflow_path.read_text(encoding="utf-8")
        match = re.search(r"cron:\s*[\"']([^\"']+)[\"']", content)
        if match:
            cron_expr = match.group(1)
            parts = cron_expr.split()
            if len(parts) > index and parts[index].isdigit():
                return int(parts[index])
    return fallback


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Default digest time — used by seed_user.py to set the initial digest_time
    # for the default user. The runner reads digest_time from each User row in the DB.
    # Falls back to 6:00 UTC if the cron expression uses a step pattern (e.g. */4).
    pipeline_run_hour_utc: int = _get_cron_part(index=1, fallback=6)
    pipeline_run_minute_utc: int = _get_cron_part(index=0, fallback=0)

    # Database
    database_url: str

    # Groq
    groq_api_key: str

    # Firebase project ID — used to verify Firebase ID tokens for account deletion.
    firebase_project_id: str = ""

    # Gmail SMTP — email delivery
    gmail_sender: str       # your Gmail address, e.g. you@gmail.com
    gmail_app_password: str # 16-char App Password (not your account password)

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
