# docker/Dockerfile
# ──────────────────
# Multi-stage build for the KYU Chatbot FastAPI backend.
#
# Build:   docker build -f docker/Dockerfile -t kyu-chatbot .
# Run:     docker run -p 8000:8000 --env-file .env kyu-chatbot

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install --default-timeout=300 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch \
    -r requirements-runtime.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY config.py        ./config.py
COPY backend/         ./backend/
COPY embedder/        ./embedder/
COPY frontend/        ./frontend/
COPY chroma_db/       ./chroma_db/

# Create directories (will be mounted as volumes in production)
RUN mkdir -p data/raw data/cleaned data/chunks logs

# Non-root user for security
RUN useradd -m -u 1000 kyu && chown -R kyu:kyu /app
USER kyu

# Pre-download the embedding model at build time (optional but faster startup)
# Comment out if you want a smaller image and prefer downloading at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run on platform-provided PORT (CraneCloud/Heroku-style), default 8000.
# Use a shell form so ${PORT} is expanded.
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --loop asyncio"]
