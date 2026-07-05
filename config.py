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
# Official KYU hosts we treat as in-scope for the knowledge base.
KYU_HOSTS = (
    "kyu.ac.ug",
    "www.kyu.ac.ug",
    "admissions.kyu.ac.ug",
    "apply.kyu.ac.ug",
)

TARGET_URLS = [
    "https://www.kyu.ac.ug/",
    "https://kyu.ac.ug/",
    "https://admissions.kyu.ac.ug/",
]

# High-value admission pages (seed list — always crawled even if link discovery fails)
SEED_URLS = [
    "https://kyu.ac.ug/about-admissions/",
    "https://kyu.ac.ug/academic-programmes/",
    "https://kyu.ac.ug/undergraduate-programmes/",
    "https://kyu.ac.ug/graduate-programmes-2/",
    "https://kyu.ac.ug/applications/",
    "https://kyu.ac.ug/admission-lists/",
    "https://kyu.ac.ug/fees-structures/",
    "https://kyu.ac.ug/cut-off-point/",
    "https://kyu.ac.ug/new-academic-calendar/",
    "https://kyu.ac.ug/scholarship/",
    "https://kyu.ac.ug/get-in-touch-contact-us-visit-us-kyambogo-university/",
    "https://kyu.ac.ug/schools-faculties/",
    "https://kyu.ac.ug/category/admissions/",
    "https://kyu.ac.ug/office-of-the-bursar-finance-department/",
    "https://ar.kyu.ac.ug/",
]

ADMISSION_URL_PATTERNS = [
    "admission", "apply", "application", "programme", "program",
    "fees", "fee", "tuition", "requirement", "cut-off", "cutoff",
    "undergraduate", "graduate", "postgraduate", "international",
    "scholarship", "calendar", "contact", "facult", "school",
    "handbook", "bursar", "registrar", "entry",
]

MIN_SCRAPED_PAGES = 20

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
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
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
