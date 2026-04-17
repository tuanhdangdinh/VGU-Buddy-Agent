import time
from fastapi import HTTPException
from .config import settings

# Gemini 2.0 Flash pricing
PRICE_INPUT = 0.0001   # $0.10 per 1M tokens → per 1K tokens
PRICE_OUTPUT = 0.0004  # $0.40 per 1M tokens → per 1K tokens

_daily_cost = 0.0
_reset_day = time.strftime("%Y-%m-%d")


def check_budget() -> None:
    global _daily_cost, _reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _reset_day:
        _daily_cost = 0.0
        _reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(503, f"Daily budget of ${settings.daily_budget_usd} exhausted. Resets tomorrow.")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    global _daily_cost
    cost = (input_tokens / 1000) * PRICE_INPUT + (output_tokens / 1000) * PRICE_OUTPUT
    _daily_cost += cost
    return _daily_cost


def get_daily_cost() -> float:
    return round(_daily_cost, 6)
