import time
from collections import defaultdict, deque
from fastapi import HTTPException
from .config import settings
from .session import USE_REDIS

try:
    from .session import _redis
except ImportError:
    _redis = None

_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(api_key: str) -> None:
    now = time.time()
    bucket = api_key[:8]
    
    if USE_REDIS and _redis:
        key = f"rate_limit:{bucket}"
        
        # Sliding window using sorted sets
        p = _redis.pipeline()
        p.zremrangebyscore(key, 0, now - 60)
        p.zadd(key, {str(now): now})
        p.zcard(key)
        p.expire(key, 60)
        res = p.execute()
        
        count = res[2]
        if count > settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            )
        return

    # Fallback to pure Python memory (only works linearly in 1 process)
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
