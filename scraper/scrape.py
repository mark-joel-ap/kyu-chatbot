"""
scraper/scrape.py
─────────────────
Phase 1: Intelligent web scraping using Crawl4AI.

Crawls KYU admission-relevant pages and saves each as a clean Markdown file
in data/raw/. Designed to be run by the Data Engineer.

Usage:
    python scraper/scrape.py

Outputs:
    data/raw/<slug>.md  – one file per crawled page
"""

import asyncio
import hashlib
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ADMISSION_URL_PATTERNS,
    LOGS_DIR,
    RAW_DIR,
    TARGET_URLS,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("scraper")


def url_to_slug(url: str) -> str:
    """Convert a URL to a safe filename slug."""
    parsed = urlparse(url)
    path = parsed.netloc + parsed.path
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", path).strip("_")
    # Truncate + hash suffix to avoid filesystem limits
    if len(slug) > 80:
        h = hashlib.md5(slug.encode()).hexdigest()[:8]
        slug = slug[:72] + "_" + h
    return slug or "index"


def is_relevant_url(url: str) -> bool:
    """
    Return True if the URL matches one of the admission-relevant path patterns.
    We always include the root pages to capture the homepage.
    """
    for base in TARGET_URLS:
        if url.startswith(base):
            path = url[len(base):]
            if not path or path == "/":
                return True
            for pattern in ADMISSION_URL_PATTERNS:
                if pattern.lower() in url.lower():
                    return True
    return False


async def crawl_with_crawl4ai(urls: list[str]) -> list[dict]:
    """
    Crawl a list of URLs using Crawl4AI and return list of
    {url, markdown, title} dicts.
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    except ImportError:
        log.error(
            "crawl4ai is not installed. Run: pip install crawl4ai"
        )
        raise

    results = []
    config = CrawlerRunConfig(
        word_count_threshold=10,       # skip near-empty pages
        exclude_external_links=True,
        exclude_social_media_links=True,
        process_iframes=False,
        remove_overlay_elements=True,
    )

    async with AsyncWebCrawler(verbose=False) as crawler:
        for url in urls:
            log.info(f"Crawling: {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success and result.markdown:
                    results.append(
                        {
                            "url": url,
                            "markdown": result.markdown,
                            "title": result.metadata.get("title", ""),
                        }
                    )
                    log.info(
                        f"  ✓ {len(result.markdown):,} chars – {result.metadata.get('title','')}"
                    )
                else:
                    log.warning(f"  ✗ Failed or empty: {url}")
            except Exception as exc:
                log.error(f"  ✗ Error crawling {url}: {exc}")

    return results


async def discover_and_crawl() -> list[dict]:
    """
    Step 1: Crawl the root pages to discover internal links.
    Step 2: Filter links to admission-relevant ones.
    Step 3: Crawl those filtered links.
    Returns all crawled page results.
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    except ImportError:
        log.error("crawl4ai not installed. Run: pip install crawl4ai")
        raise

    discovered_urls: set[str] = set(TARGET_URLS)

    # ── Discover links from root pages ──────────────────────────────────────
    log.info("Phase 1a: Discovering links from root pages …")
    config = CrawlerRunConfig(word_count_threshold=5, exclude_external_links=True)

    async with AsyncWebCrawler(verbose=False) as crawler:
        for base_url in TARGET_URLS:
            try:
                result = await crawler.arun(url=base_url, config=config)
                if result.success and result.links:
                    internal = result.links.get("internal", [])
                    for link in internal:
                        href = link.get("href", "")
                        if href and is_relevant_url(href):
                            discovered_urls.add(href.split("#")[0])  # strip anchors
            except Exception as exc:
                log.error(f"Link discovery failed for {base_url}: {exc}")

    log.info(f"Discovered {len(discovered_urls)} relevant URLs")

    # ── Crawl all discovered URLs ────────────────────────────────────────────
    log.info("Phase 1b: Crawling all relevant pages …")
    all_results = await crawl_with_crawl4ai(sorted(discovered_urls))

    return all_results


def save_results(results: list[dict]) -> int:
    """Save crawled Markdown to data/raw/. Returns count of saved files."""
    saved = 0
    for item in results:
        slug = url_to_slug(item["url"])
        out_path = RAW_DIR / f"{slug}.md"
        content = f"<!-- source: {item['url']} -->\n"
        content += f"<!-- title: {item.get('title', '')} -->\n\n"
        content += item["markdown"]
        out_path.write_text(content, encoding="utf-8")
        log.info(f"Saved → {out_path.name}")
        saved += 1
    return saved


async def main():
    log.info("═══ KYU Scraper starting ═══")
    results = await discover_and_crawl()

    if not results:
        log.error("No pages were crawled. Check network connectivity and URLs.")
        sys.exit(1)

    saved = save_results(results)
    log.info(f"═══ Done. {saved} pages saved to {RAW_DIR} ═══")

    # Quick verification
    if saved < 20:
        log.warning(
            f"Only {saved} pages captured (target ≥ 20). "
            "Consider running httrack as a fallback (see mirror.sh)."
        )
    else:
        log.info("✓ Verification passed: ≥ 20 pages captured.")


if __name__ == "__main__":
    asyncio.run(main())
