#!/usr/bin/env python3
"""
run_pipeline.py
────────────────
Convenience script to run all phases of the KYU chatbot pipeline
in sequence from a single command.

Usage:
    python run_pipeline.py [--phase PHASE]

    Phases:
        all      – run everything (default)
        scrape   – Phase 1: scrape + clean
        embed    – Phase 2: chunk + embed
        serve    – Phase 3: start backend server

Examples:
    python run_pipeline.py
    python run_pipeline.py --phase embed
    python run_pipeline.py --phase serve
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pipeline")


def run(cmd: list[str], desc: str) -> int:
    log.info(f"▶ {desc}")
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent))
    if result.returncode != 0:
        log.error(f"✗ Failed: {desc} (exit code {result.returncode})")
    else:
        log.info(f"✓ Done: {desc}")
    return result.returncode


def phase_scrape():
    log.info("═══ Phase 1: Scraping & Cleaning ═══")
    rc1 = run([sys.executable, "scraper/scrape.py"], "Scrape KYU websites")
    if rc1 != 0:
        log.warning("Scraper failed – check logs/scraper.log. Continuing with existing data.")
    rc2 = run([sys.executable, "cleaner/clean.py"], "Clean raw Markdown files")
    return rc2


def phase_embed():
    log.info("═══ Phase 2: Chunking & Embedding ═══")
    return run([sys.executable, "embedder/embed.py"], "Embed documents into ChromaDB")


def phase_verify():
    log.info("═══ Phase 2b: Retriever smoke test ═══")
    return run([sys.executable, "embedder/retriever.py"], "Run retriever smoke test")


def phase_serve():
    log.info("═══ Phase 3: Starting Backend Server ═══")
    log.info("Press Ctrl+C to stop.")
    return run(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ],
        "Start FastAPI server",
    )


def main():
    parser = argparse.ArgumentParser(description="KYU Chatbot Pipeline Runner")
    parser.add_argument(
        "--phase",
        choices=["all", "scrape", "embed", "verify", "serve"],
        default="all",
        help="Which phase to run (default: all)",
    )
    args = parser.parse_args()

    if args.phase in ("all", "scrape"):
        rc = phase_scrape()
        if rc != 0 and args.phase == "all":
            log.warning("Scrape/clean phase had issues; continuing anyway.")

    if args.phase in ("all", "embed"):
        rc = phase_embed()
        if rc != 0 and args.phase == "all":
            log.error("Embed phase failed. Cannot start server without vectors.")
            sys.exit(1)
        phase_verify()

    if args.phase in ("all", "serve"):
        phase_serve()

    if args.phase == "verify":
        phase_verify()


if __name__ == "__main__":
    main()
