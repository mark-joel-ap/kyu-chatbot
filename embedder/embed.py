"""
embedder/embed.py
──────────────────
Phase 2: Chunk cleaned Markdown files, embed with sentence-transformers,
and store in a persistent ChromaDB collection.

Usage:
    python embedder/embed.py

Input:  data/cleaned/*.md
Output: chroma_db/  (persistent vector store)

Design notes:
  - We use all-MiniLM-L6-v2 (local, ~80 MB) rather than OpenAI embeddings
    to avoid API cost and latency. It scores well on semantic similarity
    benchmarks and is fast on CPU.
  - ChromaDB is chosen over FAISS because it supports persistent storage
    out of the box with metadata filtering, which simplifies the retriever
    layer and avoids re-embedding on every restart.
  - We check for an existing collection to avoid re-embedding unnecessarily.
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHROMA_COLLECTION,
    CHROMA_DIR,
    CLEANED_DIR,
    CHUNKS_DIR,
    EMBEDDING_MODEL,
    LOGS_DIR,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "embedder.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("embedder")


def chunk_documents(files: list[Path]) -> list[dict]:
    """
    Load cleaned Markdown files and split into overlapping chunks using
    LangChain's RecursiveCharacterTextSplitter.

    Returns a list of dicts:
        {"id": str, "text": str, "source": str, "filename": str}
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],  # prefer paragraph breaks
    )

    all_chunks: list[dict] = []

    for filepath in files:
        text = filepath.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            log.debug(f"Skipping empty file: {filepath.name}")
            continue

        splits = splitter.split_text(text)
        log.info(f"  {filepath.name}: {len(splits)} chunks")

        for i, chunk_text in enumerate(splits):
            # Stable ID: hash of source + chunk index
            chunk_id = hashlib.sha256(
                f"{filepath.name}:{i}".encode()
            ).hexdigest()[:16]

            all_chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text.strip(),
                    "source": filepath.name.replace(".md", ""),
                    "filename": filepath.name,
                    "chunk_index": i,
                }
            )

    return all_chunks


def get_or_create_collection():
    """
    Return a ChromaDB collection, creating it if it doesn't exist.
    Uses persistent storage so embeddings survive restarts.
    """
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},  # cosine similarity for text
    )
    return client, collection


def embed_and_store(chunks: list[dict], collection) -> None:
    """
    Generate embeddings with sentence-transformers and upsert into ChromaDB.
    Processes in batches to manage memory.
    """
    from sentence_transformers import SentenceTransformer

    log.info(f"Loading embedding model: {EMBEDDING_MODEL} …")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # Check which IDs already exist to avoid re-embedding
    existing_ids = set(collection.get(include=[])["ids"])
    new_chunks = [c for c in chunks if c["id"] not in existing_ids]

    if not new_chunks:
        log.info("All chunks already embedded. ChromaDB is up to date.")
        return

    log.info(f"Embedding {len(new_chunks)} new chunks …")

    BATCH_SIZE = 64
    for batch_start in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        # Encode: returns numpy array, chromadb accepts lists
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,  # unit vectors for cosine similarity
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
                }
                for c in batch
            ],
        )

        log.info(
            f"  Upserted batch {batch_start // BATCH_SIZE + 1} "
            f"({len(batch)} chunks)"
        )

    log.info(
        f"ChromaDB collection '{CHROMA_COLLECTION}' now has "
        f"{collection.count()} vectors."
    )


def save_chunks_json(chunks: list[dict]) -> None:
    """Persist chunks as JSON for debugging / inspection."""
    out = CHUNKS_DIR / "chunks.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    log.info(f"Chunks saved to {out}")


def main() -> None:
    log.info("═══ KYU Embedder starting ═══")

    cleaned_files = sorted(CLEANED_DIR.glob("*.md"))
    if not cleaned_files:
        log.error(f"No cleaned files found in {CLEANED_DIR}. Run cleaner first.")
        sys.exit(1)

    log.info(f"Found {len(cleaned_files)} cleaned files.")

    # 1. Chunk
    log.info("Chunking documents …")
    chunks = chunk_documents(cleaned_files)
    log.info(f"Total chunks: {len(chunks)}")
    save_chunks_json(chunks)

    # 2. Embed + Store
    _, collection = get_or_create_collection()
    embed_and_store(chunks, collection)

    log.info(f"═══ Done. Vector store ready at {CHROMA_DIR} ═══")


if __name__ == "__main__":
    main()
