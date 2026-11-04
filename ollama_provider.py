"""Ollama adapter used by Turnitout.

Supports:
- Local Ollama: http://127.0.0.1:11434
- Hosted Ollama behind an HTTPS/authentication gateway.

Ollama itself does not provide application-level authentication. Never expose
port 11434 directly to the public internet. For hosted use, point this client
at hosted_gateway.py or an equivalent private authenticated gateway.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple


class OllamaError(RuntimeError):
    pass


class OllamaProvider:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        api_key: Optional[str] = None,
        timeout: float = 180,
        num_ctx: int = 8192,
        keep_alive: str = "5m",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.total_requests = 0
        self.total_time = 0.0

    def _request(self, path: str, payload: Optional[dict] = None) -> Tuple[dict, float]:
        start_time = time.time()
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                elapsed = time.time() - start_time
                self.total_requests += 1
                self.total_time += elapsed
                return json.loads(raw) if raw else {}, elapsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code in (401, 403):
                raise OllamaError("Hosted model gateway rejected its API key. Check OLLAMA_API_KEY.") from exc
            raise OllamaError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Start Ollama locally or check the hosted model URL. "
                f"Details: {exc.reason}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaError(f"Ollama request timed out after {self.timeout:g} seconds.") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned a response that was not valid JSON.") from exc

    def health(self) -> bool:
        result, _ = self._request("/api/tags")
        return isinstance(result, dict) and "models" in result

    def preload_model(self, model: str) -> None:
        """OPTIMIZATION: Preload the model into memory before processing to avoid cold start delays.
        Sends a minimal request to load the model so it's ready for actual processing."""
        payload = {
            "model": model,
            "keep_alive": self.keep_alive,
            "messages": []  # Minimal request just to load the model
        }
        try:
            self._request("/api/chat", payload)
            print(f"✓ Model {model} preloaded into memory")
        except Exception:
            # If preload fails (expected - empty messages), it's okay
            pass

    def chat_json(self, model: str, system: str, user: str, temperature: float = 0.2, max_tokens: Optional[int] = None, top_p: Optional[float] = None) -> Tuple[str, float]:
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "keep_alive": self.keep_alive,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }
        if top_p is not None:
            payload["options"]["top_p"] = top_p
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
            
        result, elapsed = self._request("/api/chat", payload)
        content = result.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned an empty response.")
        return content.strip(), elapsed