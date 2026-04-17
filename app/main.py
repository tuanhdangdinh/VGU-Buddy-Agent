"""
Study Buddy — Production-Ready AI Agent for VGU Students
Combines all Day 12 concepts:
  - Config from env vars (12-factor)
  - Structured JSON logging
  - API key authentication
  - Rate limiting (sliding window)
  - Cost guard (daily budget)
  - Stateless session via Redis
  - LangGraph ReAct agent with RAG
  - Health + readiness probes
  - Graceful shutdown
  - Security headers / CORS
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import os
import signal
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys

if __name__ == "__main__" and os.environ.get("VGU_RAG_SKIP_VENV_REEXEC") != "1":
    project_root = Path(__file__).resolve().parent.parent
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        os.environ["VGU_RAG_SKIP_VENV_REEXEC"] = "1"
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.graph import run_agent
from app.agent.rag import build_vectorstore, is_vectorstore_ready
from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, get_daily_cost, record_cost
from app.rate_limiter import check_rate_limit
from app.session import append_message, load_history, new_session_id, storage_backend

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False


# ─── Lifespan ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "env": settings.environment,
        "model": settings.llm_model,
        "storage": storage_backend(),
    }))

    build_vectorstore()  # pre-build FAISS index regardless of Gemini availability

    if not settings.gemini_api_key:
        logger.warning(json.dumps({"event": "warn", "msg": "GEMINI_API_KEY not set — /ask will fail"}))

    _is_ready = True
    logger.info(json.dumps({"event": "ready", "vectorstore_ready": is_vectorstore_ready()}))
    yield
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


# ─── App ────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def security_and_logging(request: Request, call_next):
    start = time.time()
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if "server" in response.headers:
        del response.headers["server"]
    logger.info(json.dumps({
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": round((time.time() - start) * 1000, 1),
    }))
    return response


# ─── Models ─────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class AskResponse(BaseModel):
    session_id: str
    question: str
    answer: str
    model: str
    turn: int
    storage: str
    timestamp: str


# ─── Endpoints ──────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "description": "AI Study Buddy for VGU students — powered by Claude + LangGraph + RAG",
        "endpoints": {"ask": "POST /ask", "health": "GET /health", "ready": "GET /ready"},
    }


@app.post("/ask", response_model=AskResponse)
async def ask_agent(
    body: AskRequest,
    _key: str = Depends(verify_api_key),
):
    check_rate_limit(_key)
    check_budget()

    session_id = body.session_id or new_session_id()
    history_before = load_history(session_id) or []
    append_message(session_id, "user", body.question)

    answer, input_tokens, output_tokens = await run_agent(body.question, history_before)

    record_cost(input_tokens, output_tokens)
    history_after = append_message(session_id, "assistant", answer)
    turn = sum(1 for m in history_after if m["role"] == "user")

    logger.info(json.dumps({
        "event": "agent_response",
        "session": session_id,
        "turn": turn,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "daily_cost_usd": get_daily_cost(),
    }))

    return AskResponse(
        session_id=session_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        turn=turn,
        storage=storage_backend(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/chat/{session_id}/history")
def get_history(session_id: str, _key: str = Depends(verify_api_key)):
    history = load_history(session_id)
    if not history:
        raise HTTPException(404, f"Session {session_id} not found or expired")
    return {"session_id": session_id, "messages": history, "count": len(history)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "model": settings.llm_model,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "daily_cost_usd": get_daily_cost(),
        "storage": storage_backend(),
        "agent_ready": bool(settings.gemini_api_key),
        "vectorstore_ready": is_vectorstore_ready(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready yet")
    return {
        "ready": True,
        "storage": storage_backend(),
        "vectorstore_ready": is_vectorstore_ready(),
    }


# ─── Graceful Shutdown ──────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal_received", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
