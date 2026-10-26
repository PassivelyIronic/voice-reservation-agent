"""Application settings. Model IDs, keys, paths and timeouts live here, never in code."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Profile = Literal["cloud", "cpu", "local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    voice_profile: Profile = "cloud"

    # LLM
    groq_api_key: SecretStr | None = None
    groq_agent_model: str = ""
    groq_simulator_model: str = "llama-3.1-8b-instant"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # STT
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cuda"
    groq_stt_model: str = "whisper-large-v3-turbo"

    # TTS
    kokoro_voice: str = ""

    # App
    db_path: Path = Path("data/osteria.db")
    log_level: str = "INFO"
    turns_log_path: Path = Path("logs/turns.jsonl")
    tool_timeout_secs: float = 2.0
    chat_reply_timeout_secs: float = 60.0
    fault_injection: str = ""

    # Tracing
    otel_exporter_otlp_endpoint: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
