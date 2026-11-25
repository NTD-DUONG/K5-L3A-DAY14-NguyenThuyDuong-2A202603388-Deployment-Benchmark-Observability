"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""
import hashlib
import math
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Redis TIME dùng chung đồng hồ giữa các instance; Lua tránh race giữa check/add.
WINDOW_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local window = 60
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[1]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry = window
    if #oldest > 0 then
        retry = math.max(1, math.ceil(tonumber(oldest[2]) + window - now))
    end
    return retry
end
redis.call('ZADD', KEYS[1], now, ARGV[2])
redis.call('EXPIRE', KEYS[1], window)
return 0
"""


def check_rate_limit(key: str) -> None:
    # Không lưu API key nguyên bản vào tên key Redis.
    identity = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if settings.rate_limit_per_minute <= 0:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"}
        )
    try:
        retry = r.eval(
            WINDOW_SCRIPT, 1, f"agent:rate:{identity}",
            settings.rate_limit_per_minute, uuid.uuid4().hex,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable") from None
    if retry:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(max(1, math.ceil(float(retry))))},
        )
