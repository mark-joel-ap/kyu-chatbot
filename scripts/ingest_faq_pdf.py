"""
scripts/ingest_faq_pdf.py
──────────────────────────
Parse Q&A pairs from data/FAQs.pdf and upsert them into ChromaDB.

Each pair is stored as one chunk (no splitting) for best FAQ retrieval.

Usage:
    python scripts/ingest_faq_pdf.py
    python scripts/ingest_faq_pdf.py --pdf data/FAQs.pdf
"""

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    CLEANED_DIR,
    DATA_DIR,
    EMBEDDING_MODEL,
    LOGS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "faq_ingest.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("faq_ingest")

DEFAULT_PDF = DATA_DIR / "FAQs.pdf"
SOURCE_NAME = "faqs_pdf"

_SKIP_QUESTION = re.compile(
    r"want me to add|check the kyambogo|read \d+ web pages|that's \d+ basic",
    re.I,
)
_SKIP_ANSWER = re.compile(
    r"^i've checked the kyambogo|^here are the accurate|^want me to add",
    re.I,
)

# Official application fee structure (overrides conflicting PDF entries)
APPLICATION_FEE_OVERRIDES = [
    {
        "question": "What are the Kyambogo University application fees?",
        "answer": (
            "Application fees depend on programme level:\n\n"
            "Undergraduate Programmes (Direct Entry / A-Level):\n"
            "• Ugandans and East African Nationals: UGX 55,000\n"
            "• International Applicants: UGX 115,000\n\n"
            "Graduate Programmes (Postgraduate Diplomas, Masters, PhD):\n"
            "• Ugandans and East African Nationals: UGX 50,000\n"
            "• International Applicants: UGX 75,000\n\n"
            "Bank charges are extra."
        ),
    },
    {
        "question": "What is the application fee for undergraduate programmes?",
        "answer": (
            "Undergraduate Programmes (Direct Entry / A-Level):\n"
            "• Ugandans and East African Nationals: UGX 55,000\n"
            "• International Applicants: UGX 115,000\n\n"
            "Bank charges are extra."
        ),
    },
    {
        "question": "What is the application fee for graduate programmes?",
        "answer": (
            "Graduate Programmes (Postgraduate Diplomas, Masters, PhD):\n"
            "• Ugandans and East African Nationals: UGX 50,000\n"
            "• International Applicants: UGX 75,000\n\n"
            "Bank charges are extra."
        ),
    },
]

_FEE_QUESTION = re.compile(
    r"application fee|pay the application fee|cost to apply",
    re.I,
)


def _normalize(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return _normalize("\n".join(pages))


def parse_qa_pairs(text: str) -> list[dict]:
    """Split document into question/answer pairs."""
    pairs: list[dict] = []
    matches = re.findall(r"Q:\s*(.+?)\s*A:\s*(.+?)(?=\s*Q:|\Z)", text, re.DOTALL)

    for i, (question, answer) in enumerate(matches, start=1):
        question = _normalize(question)
        answer = _normalize(answer)

        if len(question) < 8 or len(answer) < 15:
            continue
        if _SKIP_QUESTION.search(question) or _SKIP_ANSWER.search(answer):
            continue
        if question.endswith("?"):
            pass
        elif not question.endswith("?"):
            question = question.rstrip(".") + "?"

        pairs.append(
            {
                "qa_id": i,
                "question": question,
                "answer": answer,
                "text": f"Q: {question}\nA: {answer}",
            }
        )

    return pairs


def apply_fee_overrides(pairs: list[dict]) -> list[dict]:
    """Replace conflicting application-fee Q&As with official fee structure."""
    filtered = [p for p in pairs if not _FEE_QUESTION.search(p["question"])]
    overrides: list[dict] = []
    for i, item in enumerate(APPLICATION_FEE_OVERRIDES, start=1):
        question = item["question"]
        answer = item["answer"]
        overrides.append(
            {
                "qa_id": 9000 + i,
                "question": question,
                "answer": answer,
                "text": f"Q: {question}\nA: {answer}",
                "is_override": True,
            }
        )
    log.info(f"Applied {len(overrides)} official application-fee overrides")
    return overrides + filtered


def save_cleaned_markdown(pairs: list[dict], out_path: Path) -> None:
    lines = [
        "<!-- source: data/FAQs.pdf -->",
        "<!-- title: KYU Admissions FAQs (PDF) -->",
        "",
        "# Kyambogo University Admissions FAQs",
        "",
    ]
    for item in pairs:
        lines.append(f"## {item['question']}")
        lines.append("")
        lines.append(item["answer"])
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Saved cleaned FAQ markdown → {out_path}")


def pairs_to_chunks(pairs: list[dict]) -> list[dict]:
    chunks = []
    for item in pairs:
        if item.get("is_override"):
            id_seed = f"{SOURCE_NAME}:override:{item['question']}"
        else:
            id_seed = f"{SOURCE_NAME}:{item['qa_id']}:{item['question']}"
        chunk_id = hashlib.sha256(id_seed.encode()).hexdigest()[:20]
        chunks.append(
            {
                "id": chunk_id,
                "text": item["text"],
                "source": SOURCE_NAME,
                "filename": "FAQs.pdf",
                "chunk_index": item["qa_id"],
            }
        )
    return chunks


def delete_faq_chunks(collection) -> int:
    """Remove all existing FAQ vectors before a full re-ingest."""
    result = collection.get(where={"source": SOURCE_NAME}, include=[])
    ids = result.get("ids") or []
    if ids:
        collection.delete(ids=ids)
        log.info(f"Deleted {len(ids)} existing FAQ vectors")
    return len(ids)


def upsert_chunks(chunks: list[dict], *, replace: bool = False) -> int:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    if replace:
        delete_faq_chunks(collection)
        to_embed = chunks
    else:
        existing_ids = set(collection.get(include=[])["ids"])
        to_embed = [c for c in chunks if c["id"] not in existing_ids]

    if not to_embed:
        log.info("FAQ chunks already in ChromaDB — nothing new to embed.")
        return 0

    log.info(f"Embedding {len(to_embed)} FAQ chunks with {EMBEDDING_MODEL} …")
    model = SentenceTransformer(EMBEDDING_MODEL)

    batch_size = 64
    for start in range(0, len(to_embed), batch_size):
        batch = to_embed[start : start + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        ).tolist()

        collection.upsert(
            ids=[c["id"] for c in batch],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "source": c["source"],
                    "filename": c["filename"],
                    "chunk_index": c["chunk_index"],
                    "content_type": "faq",
                }
                for c in batch
            ],
        )

    log.info(f"ChromaDB now has {collection.count()} vectors total.")
    return len(to_embed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FAQ PDF into ChromaDB")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing FAQ vectors and re-embed all pairs",
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.exists():
        log.error(f"PDF not found: {pdf_path}")
        sys.exit(1)

    log.info(f"Reading FAQ PDF: {pdf_path}")
    text = extract_text(pdf_path)
    pairs = parse_qa_pairs(text)
    pairs = apply_fee_overrides(pairs)
    log.info(f"Parsed {len(pairs)} Q&A pairs (after fee overrides)")

    if not pairs:
        log.error("No Q&A pairs found. Check PDF format (expected Q: / A: lines).")
        sys.exit(1)

    out_md = CLEANED_DIR / "faqs_kyu.md"
    save_cleaned_markdown(pairs, out_md)

    chunks = pairs_to_chunks(pairs)
    added = upsert_chunks(chunks, replace=args.replace)
    log.info(f"Done. Added {added} FAQ vectors to '{CHROMA_COLLECTION}'.")


if __name__ == "__main__":
    main()
