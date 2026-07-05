"""
backend/app.py
───────────────
Phase 3: FastAPI backend server.

Endpoints:
    POST /chat    – accepts {"question": "..."} → {"answer": "...", "sources": [...]}
    GET  /health  – {"status": "ok", "vectors": N, "model": "..."}

Features:
    - CORS enabled for frontend integration
    - Rate limiting: 10 requests/min/IP (via slowapi)
    - Input validation (max length, empty check)
    - Full request/response logging
    - Async handlers for non-blocking Groq calls

Usage:
    uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    LOG_FILE,
    LOG_LEVEL,
    MAX_QUESTION_LEN,
    RATE_LIMIT_RPM,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
log = logging.getLogger("backend")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ─── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ─── App lifespan (startup / shutdown) ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm the embedding model and ChromaDB on startup."""
    log.info("Backend starting up – pre-warming retriever …")
    try:
        from embedder.retriever import _load_resources
        _load_resources()
        log.info("Retriever ready ✓")
    except Exception as exc:
        log.warning(
            f"Retriever pre-warm failed (run embedder first): {exc}"
        )
    yield
    log.info("Backend shutting down.")


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="KYU Admissions Chatbot API",
    description="RAG-powered chatbot for Kyambogo University admissions queries.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS – allow the mirrored frontend to call this API ──────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Restrict to your mirror domain in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Rate limiting error handler ───────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ─── Request / Response models ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question must not be empty.")
        if len(v) > MAX_QUESTION_LEN:
            raise ValueError(
                f"Question too long (max {MAX_QUESTION_LEN} characters)."
            )
        # Basic sanitisation: strip null bytes
        v = v.replace("\x00", "")
        return v


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    chunks_used: int
    processing_time_ms: int


class HealthResponse(BaseModel):
    status: str
    vector_count: int
    embedding_model: str
    llm_model: str


# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the admissions chatbot a question",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.

    Accepts a JSON body: {"question": "your question here"}
    Returns:  {"answer": "...", "sources": [...], "chunks_used": N, "processing_time_ms": N}

    Rate limited to 10 requests per minute per IP.
    """
    start = time.monotonic()
    log.info(
        f"[CHAT] IP={request.client.host} | "
        f"question={body.question!r:.100}"
    )

    try:
        from backend.rag import build_answer
        result = await build_answer(body.question)
    except Exception as exc:
        log.exception(f"Unhandled error in build_answer: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Internal error. Please contact the admissions office.",
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    log.info(
        f"[CHAT] answered in {elapsed_ms}ms | "
        f"sources={result['sources']} | "
        f"answer_preview={result['answer'][:80]!r}"
    )

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        chunks_used=result["chunks_used"],
        processing_time_ms=elapsed_ms,
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
async def health() -> HealthResponse:
    """
    Health check endpoint for monitoring.
    Returns vector store stats and model info.
    """
    from config import GROQ_MODEL

    vector_count = 0
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(CHROMA_COLLECTION)
        vector_count = collection.count()
    except Exception:
        pass  # DB might not exist yet

    return HealthResponse(
        status="ok",
        vector_count=vector_count,
        embedding_model=EMBEDDING_MODEL,
        llm_model=GROQ_MODEL,
    )


@app.get("/", include_in_schema=False)
async def root():
    """Redirect browsers to the chat widget demo."""
    return RedirectResponse(url="/demo")


@app.get("/demo", include_in_schema=False)
async def demo_page():
    """Simulated mirror page with the chat widget embedded."""
    demo = FRONTEND_DIR / "demo.html"
    if not demo.exists():
        return JSONResponse(
            {"message": "KYU Admissions Chatbot API. POST /chat to get started."}
        )
    return FileResponse(demo)


@app.get("/preview", include_in_schema=False)
async def widget_preview():
    """Standalone widget preview page."""
    widget = FRONTEND_DIR / "widget.html"
    return FileResponse(widget)


# Serve frontend assets (widget.html, inject.js, demo.html) for local dev / mirror embed
if FRONTEND_DIR.is_dir():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )


# ─── Dev entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    from config import BACKEND_HOST, BACKEND_PORT

    uvicorn.run(
        "backend.app:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
        log_level=LOG_LEVEL.lower(),
    )
