#!/usr/bin/env python3
"""Verify the local Turnitout UI/API and local-only privacy contract.

This check contacts only loopback addresses. It never makes external requests.
Set OG_API_SMOKE_TOKEN when local API authentication is enabled.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = os.environ.get("OG_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
APP_URL = os.environ.get("OG_APP_URL", "http://127.0.0.1:5173").rstrip("/")


def get(url: str):
    headers = {}
    token = os.environ.get("OG_API_SMOKE_TOKEN")
    if token and url.startswith(API_BASE):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=5) as response:
        return response.status, response.read()


def main() -> int:
    for url in (API_BASE, APP_URL):
        if not url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            print(f"Refusing non-loopback URL: {url}", file=sys.stderr)
            return 2

    try:
        status, body = get(f"{API_BASE}/api/v1/health")
        health = json.loads(body)
        assert status == 200 and health.get("status") == "healthy", health
        assert health.get("engine_status") == "ready", health
        assert health.get("installed_rule_count", 0) > 0, health

        _, settings_body = get(f"{API_BASE}/api/v1/config/settings")
        settings = json.loads(settings_body)
        privacy = settings.get("privacy", {})
        assert privacy.get("local_only") is True, privacy
        assert privacy.get("hosted_llm") is False, privacy

        _, page = get(f"{APP_URL}/")
        assert b'<div id="root"' in page or b'<div id="app"' in page, (
            "Frontend did not return the expected application shell."
        )
    except (AssertionError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"LOCAL ACCEPTANCE FAILED: {exc}", file=sys.stderr)
        if isinstance(exc, HTTPError) and exc.code == 401:
            print("Set OG_API_SMOKE_TOKEN to a configured local bearer token.", file=sys.stderr)
        return 1

    print("LOCAL ACCEPTANCE PASSED")
    print(f"  API: {API_BASE}/api/v1/health")
    print(f"  UI:  {APP_URL}")
    print("  Engine: deterministic rules loaded")
    print("  Privacy: local_only=true; hosted_llm=false")
    print("  Network: checks were restricted to loopback URLs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
