"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Đơn giá mô phỏng của bài lab, không phải xác nhận giá dịch vụ hiện hành.
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def budget_key() -> str:
    return "agent:cost:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        total = float(r.get(budget_key()) or 0)
    except RedisError:
        raise HTTPException(status_code=503, detail="Budget store unavailable") from None
    if total >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must be non-negative")
    cost = (
        input_tokens * PRICE_INPUT_PER_1K
        + output_tokens * PRICE_OUTPUT_PER_1K
    ) / 1000
    try:
        # MULTI/EXEC cộng chi phí và đặt TTL nguyên tử, chia sẻ giữa mọi worker.
        key = budget_key()
        with r.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 172800)
            pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Budget store unavailable") from None
    return cost
