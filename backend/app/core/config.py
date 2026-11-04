"""Runtime configuration for Turnitout V2.

All document processing is local by default. The only network feature is the
explicitly opt-in originality search, which is disabled unless the user runs a
search from the UI/API.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # Rule-based engine settings (no LLM dependencies)
    rule_engine_enabled: bool = True
    rule_verbose_logging: bool = False

    # Legacy processing settings remain for API compatibility; the rule engine
    # evaluates the complete document in one deterministic pass.
    turnitout_batch_size: int = 8
    turnitout_max_workers: int = 1
    turnitout_max_retries: int = 0
    turnitout_max_passes: int = 1
    turnitout_max_paragraph_chars: int = 0
    turnitout_min_paragraph_chars: int = 1
    cache_max_size: int = 1000
    max_file_size_mb: int = 25

    # Optional local PDF OCR; never enabled implicitly.
    pdf_ocr_enabled: bool = False
    pdf_ocr_language: str = "eng"
    pdf_ocr_dpi: int = 200

    # Optional local NLP/LLM providers. Both are opt-in and disabled by default.
    spacy_enabled: bool = False
    spacy_model: str = "en_core_web_sm"
    ollama_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_api_key: str = ""
    ollama_timeout: float = 180.0
    ollama_num_ctx: int = 8192

    # Originality / source matching (explicit user action only)
    enable_web_originality: bool = False
    web_timeout: float = 12.0
    web_max_queries: int = 6
    web_pages_per_query: int = 2
    web_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    # API authentication. Configure a JSON object mapping stable user IDs to
    # high-entropy bearer tokens before exposing the API beyond localhost.
    api_tokens: str = Field(default="", validation_alias="OG_API_TOKENS")
    api_auth_required: bool = Field(default=False, validation_alias="OG_API_AUTH_REQUIRED")
    # Per-owner + direct-client-IP request budget; shared gateways must add distributed limits.
    api_rate_limit_per_minute: int = Field(default=120, validation_alias="OG_API_RATE_LIMIT_PER_MINUTE")

    # Storage / CORS
    upload_dir: str = str(BASE_DIR / "backend" / "uploads")
    export_dir: str = str(BASE_DIR / "backend" / "exports")
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )
    debug: bool = False

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
Path(settings.export_dir).mkdir(parents=True, exist_ok=True)