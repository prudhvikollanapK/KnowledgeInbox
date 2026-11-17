from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        hide_input_in_errors=True,
    )

    ai_provider: Literal["auto", "openai", "demo"] = "auto"
    openai_api_key: SecretStr = SecretStr("")
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4.1-mini"
    database_path: Path = ROOT / "data" / "inbox.sqlite3"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    app_name: str = Field(default="INBOX", min_length=1, max_length=80)
    app_title: str = Field(default="Knowledge inbox", min_length=1, max_length=120)
    assistant_name: str = Field(default="Zebra", min_length=1, max_length=80)
    assistant_title: str = Field(default="How can I help you today?", min_length=1, max_length=180)
    assistant_placeholder: str = Field(
        default="Ask anything about your saved content…",
        min_length=1,
        max_length=200,
    )
    assistant_suggestions: list[str] = Field(
        default_factory=lambda: [
            "What is my city?",
            "What do you know about me?",
            "Summarize my notes",
        ],
        max_length=3,
    )

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def trim_key(cls, value):
        return value.strip() if isinstance(value, str) else value

    def public_config(self) -> dict:
        # Explicit allowlist: never serialize the full Settings object to the browser.
        return {
            "app_name": self.app_name,
            "app_title": self.app_title,
            "assistant_name": self.assistant_name,
            "assistant_title": self.assistant_title,
            "assistant_placeholder": self.assistant_placeholder,
            "assistant_suggestions": self.assistant_suggestions,
        }

    @property
    def provider(self) -> str:
        if self.ai_provider == "auto":
            return "openai" if self.openai_api_key.get_secret_value() else "demo"
        return self.ai_provider
