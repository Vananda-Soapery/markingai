"""
Central configuration for MarkingAI backend.
Reads from environment variables / .env file.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
SESSIONS_DIR = UPLOAD_DIR / "sessions"

UPLOAD_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"
    max_concurrent_grading: int = 3

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key) and self.openai_api_key != "sk-your-key-here"


settings = Settings()
