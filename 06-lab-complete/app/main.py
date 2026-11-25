"""
Production AI Agent — Part 6 Final Project (bản khung)

Hoàn thành các TODO để đạt đủ 12 tiêu chí trong README.md, rồi kiểm tra:
    python check_production_ready.py

Bản khung này chạy được (uvicorn app.main:app) nhưng chưa đạt tiêu chí nào.
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from utils.mock_llm import ask as llm_ask
from app.auth import verify_api_key
from app.redis_client import r, redis_healthy
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_cost

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
logger.info("logging_initialized")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Không ping Redis tại startup: liveness vẫn hoạt động khi Redis mất.
    logger.info("startup")
    try:
        yield
    finally:
        # Uvicorn chờ request đang xử lý xong trước khi gọi lifespan shutdown.
        logger.info("shutdown_started")
        r.close()
        logger.info("shutdown_complete")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_request(request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        logger.info("request", extra={"fields": {
            "method": request.method,
            "path": getattr(route, "path", "unmatched"),
            "status": status,
            "ms": round((time.perf_counter() - started) * 1000, 3),
        }})


@app.get("/health")
def health():
    return {"status": "ok"}

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    # Mock trả chuỗi, nên ước tính token theo số từ thay vì usage từ API thật.
    record_cost(max(1, len(body.question.split()) * 2), max(1, len(answer.split()) * 2))
    return {"question": body.question, "answer": answer}


# Uvicorn quản lý SIGTERM; không ghi đè signal handler của server.
