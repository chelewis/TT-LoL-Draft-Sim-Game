"""Application settings, read from environment variables / a .env file. Secrets never live in code."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LDM_", extra="ignore")

    # SQLite for local development; set LDM_DATABASE_URL=postgresql+psycopg://... in production.
    database_url: str = "sqlite:///./league_draft_manager.db"
    secret_key: str = "dev-secret-change-me"
    access_token_minutes: int = 60 * 24 * 7
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # background task that applies draft timeouts and notifies clients
    run_timeout_task: bool = True
    timeout_poll_seconds: float = 1.0
    # rate limit for auth endpoints (requests per window per client)
    auth_rate_limit: int = 30
    auth_rate_window_seconds: int = 60
    # Riot account import (optional). Get a personal key at developer.riotgames.com and set LDM_RIOT_API_KEY.
    # The key stays on the server; it is never sent to the browser.
    riot_api_key: str = ""
    riot_cache_seconds: int = 3600
    riot_user_cooldown_seconds: int = 10
    # Sign in with Google (optional). The OAuth "Web application" client ID from Google Cloud Console
    # (APIs & Services > Credentials). Public, not a secret; no client secret is needed. Empty hides the button.
    google_client_id: str = ""
    # usernames allowed to open the Admin tab and edit global config (JSON list), e.g. LDM_ADMIN_USERNAMES=["lewis"]
    admin_usernames: list[str] = []

    @property
    def riot_enabled(self) -> bool:
        return bool(self.riot_api_key)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id)

    def is_admin(self, username: str) -> bool:
        return username.lower() in {name.lower() for name in self.admin_usernames}


settings = Settings()
