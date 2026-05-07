"""
config.py – Central configuration for KYU Admission Support Chatbot.
All paths, model names, and tunable parameters live here.
Never hardcode secrets – they come from .env via python-dotenv.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load .env from project root

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DATA_DIR        = BASE_DIR / "data"
RAW_DIR         = DATA_DIR / "raw"          # Raw scraped Markdown files
CLEANED_DIR     = DATA_DIR / "cleaned"      # Cleaned Markdown files
CHUNKS_DIR      = DATA_DIR / "chunks"       # (Optional) persisted chunks JSON
LOGS_DIR        = BASE_DIR / "logs"
CHROMA_DIR      = BASE_DIR / "chroma_db"   # Persistent ChromaDB directory

# Ensure directories exist
for d in [RAW_DIR, CLEANED_DIR, CHUNKS_DIR, LOGS_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Scraper ──────────────────────────────────────────────────────────────────
TARGET_URLS = [
    "https://www.kyu.ac.ug/",
    "https://admissions.kyu.ac.ug/",
]

ADMISSION_URL_PATTERNS = [
    "/admissions", "/fees", "/programmes", "/requirements",
    "/application", "/undergraduate", "/postgraduate",
    "/international", "/scholarships", "/contacts",
    "/about", "/faculties", "/schools", "/departments",
    "/news", "/announcements", "/downloads",
]

# ─── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 800   # characters
CHUNK_OVERLAP = 100   # characters

# ─── Embedding ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # local, free, fast (~80 MB)
CHROMA_COLLECTION = "kyu_admissions"

# ─── Retrieval ────────────────────────────────────────────────────────────────
TOP_K = 5  # number of chunks to retrieve per query

# ─── LLM / Groq ───────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama3-8b-8192")   # or llama3-70b-8192
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_TOKENS    = 512
TEMPERATURE   = 0.1   # low = factual, deterministic answers

# ─── Backend ──────────────────────────────────────────────────────────────────
BACKEND_HOST     = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT     = int(os.getenv("BACKEND_PORT", "8000"))
RATE_LIMIT_RPM   = 10   # requests per minute per IP
MAX_QUESTION_LEN = 500  # max characters for user input

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE  = LOGS_DIR / "chatbot.log"
