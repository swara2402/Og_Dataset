"""Adapter for the repository's existing local Ollama provider."""
from __future__ import annotations

from typing import Any

from ollama_provider import OllamaProvider


class LocalOllamaAdapter:
    name = "ollama"

    def __init__(self, provider: OllamaProvider | None = None, model: str = "") -> None:
        self.provider = provider or OllamaProvider()
        self.model = model

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "configured": bool(self.model), "model": self.model or None,
                "default_url": self.provider.base_url}

    def suggest_json(self, system: str, user: str) -> tuple[str, float]:
        if not self.model:
            raise ValueError("Set an explicit local Ollama model before requesting suggestions.")
        return self.provider.chat_json(self.model, system, user, temperature=0.2)
