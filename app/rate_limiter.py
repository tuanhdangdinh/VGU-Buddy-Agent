import time
from collections import defaultdict, deque
from fastapi import HTTPException
from .config import settings

_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(api_key: str) -> None:
    now = time.time()
    bucket = api_key[:8]
    window = _windows[bucket]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        oldest = window[0]
        retry_after = int(oldest + 60 - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)
