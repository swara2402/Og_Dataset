"""Bearer-token authentication and request-scoped job ownership.

Set OG_API_TOKENS to a JSON object of stable user IDs and high-entropy tokens,
for example {"alice":"<random-secret>","bob":"<another-random-secret>"}.
"""
from __future__ import annotations

import hmac
import json
from contextvars import ContextVar
from typing import Dict, Optional

current_owner_id: ContextVar[str] = ContextVar("current_owner_id", default="local")


def _parse_tokens(raw_tokens: str) -> Dict[str, str]:
    def reject_duplicate_users(pairs):
        parsed = {}
        for user_id, token in pairs:
            if user_id in parsed:
                raise ValueError("OG_API_TOKENS must not contain duplicate user IDs.")
            parsed[user_id] = token
        return parsed

    try:
        value = json.loads(raw_tokens, object_pairs_hook=reject_duplicate_users)
    except json.JSONDecodeError as exc:
        raise ValueError("OG_API_TOKENS must contain a valid JSON object.") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("OG_API_TOKENS must be a non-empty JSON object.")
    if len(value) > 500:
        raise ValueError("OG_API_TOKENS cannot contain more than 500 users.")
    if any(
        not isinstance(user, str) or not user.strip() or len(user) > 128 or user == "local"
        or not isinstance(token, str) or len(token) < 32 or len(token) > 512
        or token.strip() != token
        for user, token in value.items()
    ):
        raise ValueError("OG_API_TOKENS must map non-local user IDs to tokens of 32-512 characters.")
    if len(set(value.values())) != len(value):
        raise ValueError("Each OG_API_TOKENS user must have a unique bearer token.")
    return value


def resolve_owner(
    authorization: Optional[str],
    raw_tokens: str,
    auth_required: bool = False,
) -> str:
    if not raw_tokens.strip():
        if auth_required:
            raise ValueError("API authentication is required but OG_API_TOKENS is not configured.")
        return "local"

    tokens = _parse_tokens(raw_tokens)
    if not authorization or not authorization.startswith("Bearer "):
        raise PermissionError("Bearer token required.")
    supplied = authorization[7:].strip()
    if not supplied:
        raise PermissionError("Bearer token required.")
    # Compare every configured token to avoid returning early on a user match.
    matched_user = None
    for user_id, expected in tokens.items():
        if hmac.compare_digest(supplied, expected):
            matched_user = user_id
    if matched_user is None:
        raise PermissionError("Invalid bearer token.")
    return matched_user


# A small in-process sliding-window limiter. For multi-worker or multi-instance
# deployments, enforce the same limits at a shared gateway (for example Redis
# or a reverse proxy); this memory is intentionally not presented as distributed.
import threading
import time
from collections import defaultdict, deque

_rate_lock = threading.Lock()
_rate_events = defaultdict(deque)


def is_rate_limited(key: str, limit: int, window_seconds: int = 60) -> bool:
    """Return True when key has exhausted its request budget for the window."""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _rate_lock:
        events = _rate_events[key]
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return True
        events.append(now)
        # Bound stale-key growth during long-running local sessions.
        if len(_rate_events) > 10_000:
            for stale_key in list(_rate_events):
                stale_events = _rate_events[stale_key]
                while stale_events and stale_events[0] <= cutoff:
                    stale_events.popleft()
                if not stale_events:
                    _rate_events.pop(stale_key, None)
        return False


def reset_rate_limits() -> None:
    """Clear limiter state; exposed for deterministic tests only."""
    with _rate_lock:
        _rate_events.clear()


def is_admin(owner_id: str, raw_tokens: str, raw_admin_users: str) -> bool:
    """Local single-user mode is admin; token users need explicit admin listing."""
    if not raw_tokens.strip():
        return owner_id == "local"
    administrators = {item.strip() for item in raw_admin_users.split(",") if item.strip()}
    return owner_id in administrators
