import time
from fastapi import HTTPException
from .config import settings
from .session import USE_REDIS

try:
    from .session import _redis
except ImportError:
    _redis = None

# Gemini 2.0 Flash pricing
PRICE_INPUT = 0.0001   # $0.10 per 1M tokens → per 1K tokens
PRICE_OUTPUT = 0.0004  # $0.40 per 1M tokens → per 1K tokens

_monthly_cost = 0.0
_reset_month = time.strftime("%Y-%m")


def check_budget() -> None:
    current_cost = get_monthly_cost()
    if current_cost >= settings.monthly_budget_usd:
        raise HTTPException(503, f"Monthly budget of ${settings.monthly_budget_usd} exhausted. Resets next month.")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    global _monthly_cost, _reset_month
    cost = (input_tokens / 1000) * PRICE_INPUT + (output_tokens / 1000) * PRICE_OUTPUT
    month = time.strftime("%Y-%m")
    
    if USE_REDIS and _redis:
        key = f"cost:{month}"
        new_val = _redis.incrbyfloat(key, cost)
        # set expire for 35 days 
        _redis.expire(key, 35 * 86400)
        return float(new_val)
        
    if month != _reset_month:
        _monthly_cost = 0.0
        _reset_month = month
    _monthly_cost += cost
    return _monthly_cost


def get_monthly_cost() -> float:
    month = time.strftime("%Y-%m")
    if USE_REDIS and _redis:
        val = _redis.get(f"cost:{month}")
        return float(val) if val else 0.0
    return round(_monthly_cost, 6)
