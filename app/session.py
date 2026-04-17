"""Stateless session storage — Redis with in-memory fallback."""
import json
import uuid
from datetime import datetime, timezone

try:
    import redis as _redis_lib
    from .config import settings
    if settings.redis_url:
        _redis = _redis_lib.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
    else:
        raise Exception("No REDIS_URL")
except Exception:
    USE_REDIS = False
    _store: dict = {}


def new_session_id() -> str:
    return str(uuid.uuid4())


def load_history(session_id: str) -> list:
    key = f"history:{session_id}"
    if USE_REDIS:
        raw = _redis.get(key)
        return json.loads(raw) if raw else []
    return _store.get(key, [])


def save_history(session_id: str, history: list, ttl: int = 3600) -> None:
    key = f"history:{session_id}"
    if USE_REDIS:
        _redis.setex(key, ttl, json.dumps(history))
    else:
        _store[key] = history


def append_message(session_id: str, role: str, content: str) -> list:
    history = load_history(session_id)
    history.append({
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    if len(history) > 20:
        history = history[-20:]
    save_history(session_id, history)
    return history


def storage_backend() -> str:
    return "redis" if USE_REDIS else "in-memory"
