"""
embedder/retriever.py
──────────────────────
Phase 2: Retriever function – the interface contract between the
vector DB and the backend RAG pipeline.

Interface contract (for Backend Dev):
────────────────────────────────────
    from embedder.retriever import retrieve

    results = retrieve(query="What are the fees for Engineering?", top_k=5)
    # Returns: List[RetrievedChunk]
    # Each chunk has: .text (str), .source (str), .score (float)

The retriever is stateful (caches model + collection at import time)
to avoid reloading on every request.
"""

import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    TOP_K,
)

log = logging.getLogger("retriever")


@dataclass
class RetrievedChunk:
    """A single retrieved document chunk with metadata."""
    text: str
    source: str        # human-readable source filename (without .md)
    score: float       # cosine similarity distance (lower = more similar)
    chunk_index: int


@lru_cache(maxsize=1)
def _load_resources():
    """
    Load embedding model and ChromaDB collection once and cache.
    Thread-safe via lru_cache; avoids reloading on every request.
    """
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    log.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    log.info(f"Connecting to ChromaDB at {CHROMA_DIR}")
    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    collection = client.get_collection(name=CHROMA_COLLECTION)
    log.info(f"Collection '{CHROMA_COLLECTION}' loaded ({collection.count()} vectors)")

    return model, collection


def retrieve(
    query: str,
    top_k: int = TOP_K,
    min_score_threshold: Optional[float] = None,
) -> list[RetrievedChunk]:
    """
    Retrieve the top-k most relevant chunks for a given query.

    Args:
        query:               The user's question / search string.
        top_k:               Number of chunks to return (default from config).
        min_score_threshold: Optional max distance (lower = more similar).
                             Chunks with distance > threshold are filtered out.
                             None = return all top_k regardless of score.

    Returns:
        List of RetrievedChunk objects, sorted by relevance (best first).

    Raises:
        RuntimeError: If ChromaDB collection doesn't exist (embedder not run).
    """
    if not query.strip():
        return []

    try:
        model, collection = _load_resources()
    except Exception as exc:
        log.error(f"Failed to load retriever resources: {exc}")
        raise RuntimeError(
            "Vector store not ready. Run embedder/embed.py first."
        ) from exc

    # Embed the query
    query_embedding = model.encode(
        [query.strip()],
        normalize_embeddings=True,
    ).tolist()

    # Query ChromaDB (retry once if collection was rebuilt while server was running)
    try:
        n_results = min(top_k, collection.count())
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        if "does not exist" not in str(exc):
            raise
        log.warning("Stale ChromaDB collection handle – reloading …")
        _load_resources.cache_clear()
        model, collection = _load_resources()
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

    chunks: list[RetrievedChunk] = []

    documents  = results.get("documents",  [[]])[0]
    metadatas  = results.get("metadatas",  [[]])[0]
    distances  = results.get("distances",  [[]])[0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        # Apply optional score filter
        if min_score_threshold is not None and dist > min_score_threshold:
            continue
        chunks.append(
            RetrievedChunk(
                text=doc,
                source=meta.get("source", "unknown"),
                score=round(float(dist), 4),
                chunk_index=int(meta.get("chunk_index", 0)),
            )
        )

    log.debug(f"Retrieved {len(chunks)} chunks for query: {query!r}")
    return chunks


if __name__ == "__main__":
    # Quick smoke test
    logging.basicConfig(level=logging.INFO)
    sample_query = "What is the tuition fee for Bachelor of Engineering?"
    print(f"\nQuery: {sample_query}\n{'─'*60}")
    try:
        chunks = retrieve(sample_query, top_k=3)
        for i, chunk in enumerate(chunks, 1):
            print(f"\n[Chunk {i}] Source: {chunk.source} | Score: {chunk.score}")
            print(chunk.text[:300], "…" if len(chunk.text) > 300 else "")
        if chunks:
            print("\n✓ Retriever verification passed.")
        else:
            print("\n⚠ No chunks returned – check that the embedder has been run.")
    except RuntimeError as e:
        print(f"\n✗ {e}")
