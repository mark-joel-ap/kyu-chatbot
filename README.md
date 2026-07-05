# KYU Admission Support Chatbot

> An AI-powered RAG chatbot embedded in a mirror of the Kyambogo University website,
> helping prospective students get instant, accurate answers about admissions, fees,
> programmes, and requirements.

---

## Architecture Overview

```
User Question
     │
     ▼
┌─────────────┐   fetch   ┌──────────────────────────────────────────────────────┐
│  Chat Widget│──────────▶│              FastAPI Backend                         │
│ (HTML/JS)   │           │  POST /chat                                          │
└─────────────┘           │       │                                              │
                          │       ▼                                              │
                          │  ┌──────────┐   embed query   ┌──────────────────┐  │
                          │  │Retriever │────────────────▶│ ChromaDB         │  │
                          │  │          │◀────────────────│ (all-MiniLM-L6)  │  │
                          │  └──────────┘   top-k chunks  └──────────────────┘  │
                          │       │                                              │
                          │       ▼                                              │
                          │  ┌──────────┐   prompt+context                      │
                          │  │ RAG      │──────────────────▶ Groq (Llama 3)     │
                          │  │ Pipeline │◀────────────────── answer              │
                          │  └──────────┘                                        │
                          └──────────────────────────────────────────────────────┘
                                │
                                ▼ {"answer": "...", "sources": [...]}
```

**Tech stack:**
- Scraping: Crawl4AI (Markdown output) + wget/httrack (site mirror)
- Embeddings: `all-MiniLM-L6-v2` (local, no API cost)
- Vector DB: ChromaDB (persistent local storage)
- LLM: Groq Cloud API → Llama 3 8B (free tier)
- Backend: FastAPI + uvicorn
- Frontend: Vanilla HTML/CSS/JS chat bubble

---

## Team Division of Work

| Member | Folder(s) | Scripts |
|--------|-----------|---------|
| **Mugasi Van Surrender - Data Engineer** | `scraper/`, `cleaner/` | `scrape.py`, `mirror.sh`, `clean.py` |
| **Kintu Joshua - AI/DB Specialist** | `embedder/` | `embed.py`, `retriever.py` |
| **Apunyo Joel Mark - Backend Dev** | `backend/` | `app.py`, `rag.py` |
| **Kamukama Jonan - Frontend & UI** | `frontend/`, `mirror/` | `widget.html`, `inject.js` |

---

## Prerequisites

- Python 3.10+ (3.11 recommended)
- pip / conda
- A free [Groq API key](https://console.groq.com/) (takes 2 minutes)
- wget or httrack (for site mirroring)
- Docker + Docker Compose (optional, for containerised deployment)

---

## Quick Start (Local)

### 1. Clone & Install

```bash
git clone https://github.com/mark-joel-ap/kyu-chatbot.git
cd kyu-chatbot

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### 3. Mirror the KYU Website (Data Engineer - Mugasi Van Surrender)

```bash
chmod +x scraper/mirror.sh
./scraper/mirror.sh
# Creates: mirror/kyu.ac.ug/ and mirror/admissions.kyu/
```

### 4. Scrape Admission Content (Data Engineer - Mugasi Van Surrender)

```bash
python scraper/scrape.py
# Output: data/raw/*.md  (aim for ≥ 20 files)
```

### 5. Clean the Data (Data Engineer - Mugasi Van Surrender)

```bash
python cleaner/clean.py
# Output: data/cleaned/*.md
```

### 6. Build the Vector Database (AI/DB Specialist - Kintu Joshua)

```bash
python embedder/embed.py
# Output: chroma_db/  (persistent vector store)

# Verify retrieval works:
python embedder/retriever.py
```

### 7. Start the Backend (Backend Dev - Apunyo Joel Mark)

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

Test it:

**Windows (PowerShell)** — use `curl.exe` or `Invoke-RestMethod` (plain `curl` is a PowerShell alias and breaks JSON quoting):

```powershell
# Health check
Invoke-RestMethod http://localhost:8000/health

# Chat (recommended)
Invoke-RestMethod -Uri http://localhost:8000/chat -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "What are the fees for Bachelor of Engineering?"}'

# Or run the helper script:
.\scripts\test-api.ps1
```

**macOS / Linux / Git Bash:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the fees for Bachelor of Engineering?"}'
```

Expected response:
```json
{
  "answer": "According to the KYU fees schedule...",
  "sources": ["admissions_fees", "programmes_engineering"],
  "chunks_used": 3,
  "processing_time_ms": 1240
}
```

### 8. Embed the Chat Widget (Frontend Dev - Kamukama Jonan)

**Option A – Direct HTML injection:**

Open `mirror/kyu.ac.ug/index.html` (or any page) and paste before `</body>`:
```html
<script>window.KYU_CHAT_API = "http://localhost:8000";</script>
<script src="/frontend/inject.js"></script>
```

**Option B – Preview the widget standalone:**
```bash
# Open in browser:
open frontend/widget.html
# or: python -m http.server 8080 then visit http://localhost:8080/frontend/widget.html
```

### 9. Run the Test Suite

```bash
# With backend running:
pytest tests/test_chatbot.py -v

# Quality test (50 questions):
python tests/test_chatbot.py
# Report saved to: logs/quality_test_report.json
```

---

## Or: Run Everything at Once

```bash
# Full pipeline (scrape → clean → embed → serve):
python run_pipeline.py

# Individual phases:
python run_pipeline.py --phase scrape
python run_pipeline.py --phase embed
python run_pipeline.py --phase serve
```

---

## Docker Deployment

```bash
# Build and start all services:
docker-compose -f docker/docker-compose.yml up --build

# Services:
#   http://localhost:8000  → FastAPI backend (API)
#   http://localhost:8001  → ChromaDB HTTP API
#   http://localhost:8080  → Mirrored KYU site with chat widget
```

**Note:** Run the scraper and embedder *before* starting Docker so the vector store is populated:
```bash
python scraper/scrape.py
python cleaner/clean.py
python embedder/embed.py
# Then:
docker-compose -f docker/docker-compose.yml up --build
```

---

## Project Structure

```
kyu-chatbot/
├── config.py                  # Central config (paths, model names, settings)
├── .env.example               # Environment variable template
├── requirements.txt           # Python dependencies
├── run_pipeline.py            # One-command pipeline runner
│
├── scraper/
│   ├── scrape.py              # Crawl4AI scraper → data/raw/*.md
│   └── mirror.sh              # httrack/wget site mirror
│
├── cleaner/
│   └── clean.py               # Data cleaning → data/cleaned/*.md
│
├── embedder/
│   ├── embed.py               # Chunking + embedding → ChromaDB
│   └── retriever.py           # Retriever interface (used by backend)
│
├── backend/
│   ├── app.py                 # FastAPI server (POST /chat, GET /health)
│   └── rag.py                 # RAG pipeline (retriever + Groq LLM)
│
├── frontend/
│   ├── widget.html            # Self-contained chat widget (preview)
│   └── inject.js              # Single-script site injection loader
│
├── tests/
│   └── test_chatbot.py        # pytest suite + 50-question quality test
│
├── docker/
│   ├── Dockerfile             # Backend container
│   ├── docker-compose.yml     # Backend + ChromaDB + Nginx
│   └── nginx.conf             # Mirror site serving config
│
├── data/
│   ├── raw/                   # Raw scraped Markdown (git-ignored)
│   ├── cleaned/               # Cleaned Markdown (git-ignored)
│   └── chunks/                # Persisted chunks JSON (git-ignored)
├── chroma_db/                 # Persistent vector store (git-ignored)
└── logs/                      # Application logs (git-ignored)
```

---

## Interface Contracts

### Retriever → Backend

```python
from embedder.retriever import retrieve, RetrievedChunk

chunks: list[RetrievedChunk] = retrieve(query="...", top_k=5)
# chunk.text        – the raw chunk text
# chunk.source      – source filename slug
# chunk.score       – cosine distance (0 = identical)
# chunk.chunk_index – position within source file
```

### Backend API → Frontend

**POST /chat**
```json
// Request
{ "question": "What are the engineering fees?" }

// Response
{
  "answer":             "According to KYU's fees schedule…",
  "sources":            ["admissions_fees", "programmes_engineering"],
  "chunks_used":        3,
  "processing_time_ms": 1240
}
```

**GET /health**
```json
{
  "status":          "ok",
  "vector_count":    342,
  "embedding_model": "all-MiniLM-L6-v2",
  "llm_model":       "llama-3.1-8b-instant"
}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GROQ_API_KEY not set` | Copy `.env.example` → `.env` and add your key |
| Chat returns "unexpected error" | Groq may have retired the model — set `GROQ_MODEL=llama-3.1-8b-instant` in `.env` and restart uvicorn |
| `chromadb collection not found` | Run `python embedder/embed.py` first |
| `scraper captures < 20 pages` | Run `./scraper/mirror.sh` as a fallback |
| `Backend returns 429` | Wait 60 s (rate limit is 10 req/min/IP) |
| `Widget shows "Cannot connect"` | Ensure backend is running on port 8000 |
| `curl` JSON error on Windows | Use `curl.exe` (not `curl`) or `Invoke-RestMethod`; see `scripts/test-api.ps1` |
| `curl: Could not resolve host: are/the/...` | PowerShell split your JSON body — use single quotes around JSON or run `.\scripts\test-api.ps1` |
| Slow first response | Embedding model is loading; subsequent responses are faster |
| Docker: `permission denied on chroma_db` | `chmod -R 777 chroma_db data logs` |

---

## Security Notes

- Never commit `.env` to version control (it's in `.gitignore`).
- In production, restrict CORS to your mirror domain.
- Set `RATE_LIMIT_RPM` lower if you expect abuse.
- Input length is validated server-side (max 500 chars).
- The LLM is strictly prompted to use only retrieved context.

---

## Verification Checklist

- [ ] `data/raw/` contains ≥ 20 `.md` files after scraping
- [ ] `python embedder/retriever.py` returns chunks for a sample query
- [ ] `curl http://localhost:8000/health` returns `{"status": "ok", ...}`
- [ ] `curl -X POST http://localhost:8000/chat -d '{"question":"engineering fees"}'` returns a grounded answer
- [ ] The chat widget appears on the mirror site and responds correctly
- [ ] `pytest tests/ -v` – all tests pass

---

*Built for Kyambogo University — Kampala, Uganda.*
*This chatbot supplements but does not replace official admissions guidance. You can contact the admissions office at admissions@kyu.ac.ug or call +256-41-4285001.*
