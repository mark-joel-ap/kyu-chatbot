"""
backend/rag.py
───────────────
Phase 3: RAG pipeline – ties retriever + Groq LLM together.

The build_answer() function is the core interface for the backend API.

Interface contract (for Backend Dev):
    from backend.rag import build_answer

    result = await build_answer("What are the fees for Engineering?")
    # result = {"answer": "...", "sources": ["admissions_fees", ...]}
"""

import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
    TOP_K,
)

log = logging.getLogger("rag")

# ─── Prompt template ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful and accurate Kyambogo University Admissions Assistant.

Your role is to answer questions from prospective students about admissions, \
programmes, fees, requirements, and university life at Kyambogo University (KYU) \
in Uganda.

STRICT RULES:
1. Use ONLY the provided context to answer questions. Do not use external knowledge.
2. If the context does not contain enough information, say exactly:
   "I don't have that information. Please contact the Kyambogo University \
Admissions Office at admissions@kyu.ac.ug or call +256-41-4285001."
3. Never invent fees, dates, programme names, or requirements.
4. Be concise, professional, and friendly.
5. When listing fees or requirements, use bullet points or numbered lists for clarity.
6. Always mention the source page name when relevant (e.g., "According to the \
admissions page…").
"""

USER_PROMPT_TEMPLATE = """Context information from Kyambogo University website:
───────────────────────────────────────────
{context}
───────────────────────────────────────────

Student Question: {question}

Answer (based ONLY on the context above):"""


def build_context(chunks) -> str:
    """Format retrieved chunks into a single context string for the prompt."""
    if not chunks:
        return "No relevant information found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source {i}: {chunk.source}]\n{chunk.text}")
    return "\n\n".join(parts)


async def build_answer(
    question: str,
    top_k: int = TOP_K,
) -> dict:
    """
    Main RAG pipeline function.

    1. Retrieve relevant chunks from ChromaDB.
    2. Build a strict grounded prompt.
    3. Call Groq Llama 3 API with retry logic.
    4. Return answer + source metadata.

    Returns:
        {
            "answer": str,
            "sources": list[str],   # source page slugs
            "chunks_used": int,
        }
    """
    import httpx
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    # ── Step 1: Retrieve ──────────────────────────────────────────────────────
    try:
        from embedder.retriever import retrieve
        chunks = retrieve(question, top_k=top_k)
    except RuntimeError as e:
        log.error(f"Retrieval failed: {e}")
        return {
            "answer": (
                "The knowledge base is not ready yet. "
                "Please try again later or contact the admissions office."
            ),
            "sources": [],
            "chunks_used": 0,
        }

    context = build_context(chunks)
    sources = list({c.source for c in chunks})  # deduplicated source list

    # ── Step 2: Build prompt ──────────────────────────────────────────────────
    user_message = USER_PROMPT_TEMPLATE.format(
        context=context,
        question=question.strip(),
    )

    # ── Step 3: Call Groq with retry ─────────────────────────────────────────
    if not GROQ_API_KEY:
        log.error("GROQ_API_KEY is not set in environment.")
        return {
            "answer": "The AI service is not configured. Please contact support.",
            "sources": sources,
            "chunks_used": len(chunks),
        }

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
    )
    async def call_groq() -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_message},
                    ],
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    try:
        answer = await call_groq()
    except httpx.HTTPStatusError as e:
        log.error(f"Groq API HTTP error {e.response.status_code}: {e.response.text}")
        if e.response.status_code == 429:
            answer = (
                "The AI service is busy right now. "
                "Please try again in a moment, or contact the admissions office."
            )
        else:
            answer = (
                "An error occurred while generating the answer. "
                "Please contact the Kyambogo University Admissions Office."
            )
    except Exception as e:
        log.exception(f"Unexpected error calling Groq: {e}")
        answer = (
            "An unexpected error occurred. "
            "Please contact the Kyambogo University Admissions Office."
        )

    log.info(
        f"RAG complete | question_len={len(question)} | "
        f"chunks={len(chunks)} | answer_len={len(answer)}"
    )

    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(chunks),
    }
