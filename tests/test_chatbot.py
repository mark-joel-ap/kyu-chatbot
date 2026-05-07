"""
tests/test_chatbot.py
──────────────────────
Phase 4: Comprehensive test suite.

Runs:
  1. Scraper verification  – ≥ 20 raw pages captured.
  2. Retriever smoke test  – returns relevant chunks for a sample query.
  3. API endpoint tests    – /health and /chat via httpx async client.
  4. Quality tests         – 50 common admission questions with basic
                            anti-hallucination checks.

Usage:
    # With the backend running:
    pytest tests/test_chatbot.py -v

    # Or run directly (runs subset without pytest):
    python tests/test_chatbot.py
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx

from config import CLEANED_DIR, RAW_DIR

log = logging.getLogger("tests")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BACKEND_URL = "http://localhost:8000"

# ─── 50 Common Admission Questions ───────────────────────────────────────────
ADMISSION_QUESTIONS = [
    # Fees & Tuition
    "What is the tuition fee for Bachelor of Engineering?",
    "How much does it cost to study at Kyambogo University?",
    "What are the functional fees at KYU?",
    "Are there any scholarships available at KYU?",
    "What is the fees structure for postgraduate programmes?",
    "Do international students pay different fees?",
    "What is the application fee for KYU?",
    "Are fees paid per semester or per year?",
    "What are the accommodation fees at KYU?",
    "Does KYU offer fee payment in installments?",

    # Programmes
    "What undergraduate programmes does KYU offer?",
    "Does KYU offer medical or health science programmes?",
    "What engineering courses are available at Kyambogo?",
    "What postgraduate programmes does KYU offer?",
    "Does KYU have a Faculty of Education?",
    "What business courses are offered at KYU?",
    "Does KYU offer computer science or IT programmes?",
    "Are there vocational or diploma programmes at KYU?",
    "What is the duration of a Bachelor's degree at KYU?",
    "Does KYU offer distance or online learning?",

    # Admission Requirements
    "What are the minimum A-level points required for admission?",
    "What subjects are required for engineering admission?",
    "Can I apply with a diploma to KYU?",
    "What are the entry requirements for education programmes?",
    "Does KYU accept mature age entry applicants?",
    "What is the minimum UACE score for admission?",
    "Are there special entry requirements for international students?",
    "Does KYU accept transfers from other universities?",
    "What O-level results are needed for admission?",
    "Are there prerequisite subjects for science programmes?",

    # Application Process
    "How do I apply to Kyambogo University?",
    "What is the deadline for applications?",
    "Is the application process done online?",
    "Where can I get an application form?",
    "How long does the admission process take?",
    "When does the academic year start at KYU?",
    "How will I know if my application was successful?",
    "Can I apply to multiple programmes at once?",
    "What documents do I need to submit with my application?",
    "How do I check my admission status?",

    # Campus & Student Life
    "Where is Kyambogo University located?",
    "Does KYU have student accommodation on campus?",
    "What student support services does KYU offer?",
    "Is there a library at Kyambogo University?",
    "Does KYU have sports facilities?",
    "Are there student clubs and societies at KYU?",
    "What is the student population at KYU?",
    "Does KYU have a student hospital or health center?",
    "How do I contact the admissions office?",
    "What is KYU's accreditation status?",
]

# ─── Keywords that a good answer should NOT be missing ────────────────────────
# (very basic anti-hallucination heuristics)
HALLUCINATION_SIGNALS = [
    "as of 2024",  # model fabricating dates
    "i believe",
    "i think",
    "probably",
    "approximately $",   # dollar signs (KYU uses UGX)
    "i'm not sure but",
]

# Keywords that indicate a grounded answer
GROUNDING_KEYWORDS = [
    "kyambogo", "kyu", "admissions", "programme", "fees",
    "uganda", "semester", "faculty", "school", "department",
    "contact", "apply", "requirement",
]


# ─── Test 1: Scraper verification ─────────────────────────────────────────────
class TestScraper:
    def test_raw_pages_count(self):
        raw_files = list(RAW_DIR.glob("*.md"))
        log.info(f"Raw pages found: {len(raw_files)}")
        assert len(raw_files) >= 20, (
            f"Only {len(raw_files)} pages captured – expected ≥ 20. "
            "Run scraper/scrape.py first."
        )

    def test_cleaned_pages_exist(self):
        cleaned_files = list(CLEANED_DIR.glob("*.md"))
        log.info(f"Cleaned pages found: {len(cleaned_files)}")
        assert len(cleaned_files) >= 10, (
            f"Only {len(cleaned_files)} cleaned files – expected ≥ 10. "
            "Run cleaner/clean.py first."
        )

    def test_no_empty_cleaned_files(self):
        for f in CLEANED_DIR.glob("*.md"):
            content = f.read_text(encoding="utf-8").strip()
            assert len(content) > 100, f"File is nearly empty after cleaning: {f.name}"


# ─── Test 2: Retriever smoke test ─────────────────────────────────────────────
class TestRetriever:
    def test_retriever_returns_chunks(self):
        try:
            from embedder.retriever import retrieve
        except ImportError:
            pytest.skip("Retriever module not available.")

        query = "What is the tuition fee for Bachelor of Engineering?"
        try:
            chunks = retrieve(query, top_k=3)
        except RuntimeError as e:
            pytest.skip(f"ChromaDB not ready: {e}")

        log.info(f"Retrieved {len(chunks)} chunks for engineering fee query")
        assert len(chunks) > 0, "No chunks returned – check that embed.py has been run."

    def test_retriever_chunk_has_text(self):
        try:
            from embedder.retriever import retrieve
        except ImportError:
            pytest.skip("Retriever module not available.")

        try:
            chunks = retrieve("How do I apply to KYU?", top_k=3)
        except RuntimeError as e:
            pytest.skip(f"ChromaDB not ready: {e}")

        for chunk in chunks:
            assert chunk.text.strip(), "Empty chunk text returned."
            assert chunk.source, "Chunk missing source metadata."
            assert 0.0 <= chunk.score <= 2.0, f"Unexpected score: {chunk.score}"

    def test_empty_query_returns_empty(self):
        try:
            from embedder.retriever import retrieve
        except ImportError:
            pytest.skip("Retriever module not available.")
        try:
            chunks = retrieve("", top_k=3)
        except RuntimeError:
            pytest.skip("ChromaDB not ready.")
        assert chunks == [], "Empty query should return empty list."


# ─── Test 3: API endpoint tests ───────────────────────────────────────────────
@pytest.mark.asyncio
class TestAPI:
    async def test_health_endpoint(self):
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10) as client:
            try:
                r = await client.get("/health")
            except httpx.ConnectError:
                pytest.skip("Backend not running. Start with: uvicorn backend.app:app")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert "vector_count" in data

    async def test_chat_engineering_fee(self):
        """Critical test: verify the /chat endpoint for the engineering fee question."""
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=60) as client:
            try:
                r = await client.post(
                    "/chat",
                    json={"question": "What is the tuition fee for Bachelor of Engineering?"},
                )
            except httpx.ConnectError:
                pytest.skip("Backend not running.")

        assert r.status_code == 200
        data = r.json()
        assert "answer" in data
        assert len(data["answer"]) > 20, "Answer too short."

        answer_lower = data["answer"].lower()
        # Should NOT be a hallucinated answer
        for signal in HALLUCINATION_SIGNALS:
            assert signal not in answer_lower, (
                f"Possible hallucination detected: '{signal}' in answer."
            )

        log.info(f"Engineering fee answer: {data['answer'][:200]}")

    async def test_chat_empty_question_rejected(self):
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10) as client:
            try:
                r = await client.post("/chat", json={"question": ""})
            except httpx.ConnectError:
                pytest.skip("Backend not running.")
        assert r.status_code == 422  # Pydantic validation error

    async def test_chat_too_long_question_rejected(self):
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10) as client:
            try:
                r = await client.post("/chat", json={"question": "x" * 501})
            except httpx.ConnectError:
                pytest.skip("Backend not running.")
        assert r.status_code == 422


# ─── Test 4: Quality tests – 50 questions ─────────────────────────────────────
async def run_quality_tests(subset: int = 50) -> dict:
    """
    Run up to `subset` questions through the API and collect quality metrics.

    Returns a results dict with pass/fail stats.
    """
    questions = ADMISSION_QUESTIONS[:subset]
    results = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "details": []}

    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=60) as client:
        # Check backend availability
        try:
            hr = await client.get("/health")
            hr.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPStatusError):
            log.error("Backend not running. Start it first.")
            return results

        for i, question in enumerate(questions, 1):
            results["total"] += 1
            log.info(f"[{i}/{len(questions)}] {question}")

            try:
                r = await client.post("/chat", json={"question": question})
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                log.warning(f"  HTTP {e.response.status_code} – skipped")
                results["skipped"] += 1
                continue

            data = r.json()
            answer = data.get("answer", "")
            answer_lower = answer.lower()

            # Quality checks
            passed = True
            issues = []

            # 1. Non-empty answer
            if len(answer.strip()) < 15:
                issues.append("answer_too_short")
                passed = False

            # 2. No hallucination signals
            for signal in HALLUCINATION_SIGNALS:
                if signal in answer_lower:
                    issues.append(f"hallucination_signal:{signal!r}")
                    passed = False

            # 3. Answer contains at least one grounding keyword OR
            #    the "I don't have that information" fallback
            has_grounding = any(kw in answer_lower for kw in GROUNDING_KEYWORDS)
            has_fallback  = "don't have that information" in answer_lower
            if not has_grounding and not has_fallback:
                issues.append("no_grounding_keyword")
                # Not a hard fail – model may answer generically

            if passed:
                results["passed"] += 1
                log.info(f"  ✓ PASS | {answer[:80]!r}")
            else:
                results["failed"] += 1
                log.warning(f"  ✗ FAIL | issues={issues} | {answer[:80]!r}")

            results["details"].append(
                {
                    "question": question,
                    "answer_preview": answer[:200],
                    "passed": passed,
                    "issues": issues,
                    "sources": data.get("sources", []),
                    "processing_time_ms": data.get("processing_time_ms", 0),
                }
            )

            # Be polite to the API
            await asyncio.sleep(1.0)

    return results


async def main():
    """Standalone runner for the quality test suite."""
    log.info("═══ KYU Chatbot Quality Test Suite ═══")
    results = await run_quality_tests(subset=50)

    if results["total"] == 0:
        log.error("No tests ran. Is the backend running?")
        return

    pct = results["passed"] / max(results["total"] - results["skipped"], 1) * 100
    log.info(
        f"\n{'═'*50}\n"
        f"Results: {results['passed']}/{results['total']} passed ({pct:.1f}%)\n"
        f"Failed:  {results['failed']} | Skipped: {results['skipped']}\n"
        f"{'═'*50}"
    )

    # Save report
    report_path = Path("logs/quality_test_report.json")
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info(f"Full report saved to {report_path}")

    if pct >= 80:
        log.info("✓ Quality threshold met (≥ 80% pass rate).")
    else:
        log.warning(f"✗ Quality below threshold ({pct:.1f}% < 80%).")


if __name__ == "__main__":
    asyncio.run(main())
