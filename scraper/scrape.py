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
from urllib.parse import urlparse, urlunparse

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ADMISSION_URL_PATTERNS,
    KYU_HOSTS,
    LOGS_DIR,
    MIN_SCRAPED_PAGES,
    RAW_DIR,
    SEED_URLS,
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

_MD_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
_HREF_IN_MD = re.compile(r"https?://[^\s\)\]\"']+")


def url_to_slug(url: str) -> str:
    """Convert a URL to a safe filename slug."""
    parsed = urlparse(url)
    path = parsed.netloc + parsed.path
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", path).strip("_")
    if len(slug) > 80:
        h = hashlib.md5(slug.encode()).hexdigest()[:8]
        slug = slug[:72] + "_" + h
    return slug or "index"


def is_kyu_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in KYU_HOSTS or host.endswith(".kyu.ac.ug")


def normalize_url(url: str) -> str:
    """Strip fragments, normalize host casing, ensure consistent form."""
    url = url.strip().split("#")[0]
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    # Drop query strings (WordPress page_id URLs still work without them for crawling)
    return urlunparse((parsed.scheme, host, path, "", "", ""))


def is_relevant_url(url: str) -> bool:
    """
    Return True if the URL is on a KYU host and relates to admissions/student info.
    """
    if not is_kyu_url(url):
        return False

    url_lower = normalize_url(url).lower()
    path = urlparse(url_lower).path

    if path in ("", "/"):
        return True

    for seed in SEED_URLS:
        if url_lower.rstrip("/") == normalize_url(seed).lower().rstrip("/"):
            return True

    for pattern in ADMISSION_URL_PATTERNS:
        if pattern.lower() in url_lower:
            return True

    return False


def extract_links_from_markdown(text: str) -> set[str]:
    """Fallback link discovery from rendered Markdown."""
    found: set[str] = set()
    for match in _MD_LINK.finditer(text):
        found.add(normalize_url(match.group(1)))
    for match in _HREF_IN_MD.finditer(text):
        url = normalize_url(match.group(0).rstrip(".,;)"))
        if is_kyu_url(url):
            found.add(url)
    return found


async def crawl_with_crawl4ai(urls: list[str]) -> list[dict]:
    """
    Crawl a list of URLs using Crawl4AI and return list of
    {url, markdown, title} dicts.
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    except ImportError:
        log.error("crawl4ai is not installed. Run: pip install crawl4ai")
        raise

    results = []
    seen_urls: set[str] = set()
    config = CrawlerRunConfig(
        word_count_threshold=10,
        exclude_external_links=True,
        exclude_social_media_links=True,
        process_iframes=False,
        remove_overlay_elements=True,
    )

    async with AsyncWebCrawler(verbose=False) as crawler:
        for url in urls:
            norm = normalize_url(url)
            if norm in seen_urls:
                continue
            seen_urls.add(norm)

            log.info(f"Crawling: {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success and result.markdown:
                    content_len = len(result.markdown.strip())
                    if content_len < 80:
                        log.warning(f"  ✗ Too short ({content_len} chars): {url}")
                        continue
                    results.append(
                        {
                            "url": norm,
                            "markdown": result.markdown,
                            "title": result.metadata.get("title", ""),
                        }
                    )
                    log.info(
                        f"  ✓ {content_len:,} chars – "
                        f"{result.metadata.get('title', '')}"
                    )
                else:
                    log.warning(f"  ✗ Failed or empty: {url}")
            except Exception as exc:
                log.error(f"  ✗ Error crawling {url}: {exc}")

    return results


async def discover_urls() -> list[str]:
    """
    Discover admission-relevant URLs via:
      1. Configured seeds and target pages
      2. Crawl4AI internal link extraction
      3. Markdown link regex fallback from crawled hub pages
    """
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    except ImportError:
        log.error("crawl4ai not installed. Run: pip install crawl4ai")
        raise

    discovered: set[str] = set()

    for url in TARGET_URLS + SEED_URLS:
        discovered.add(normalize_url(url))

    log.info("Phase 1a: Discovering links from hub pages …")
    config = CrawlerRunConfig(word_count_threshold=5, exclude_external_links=True)

    hub_pages: list[str] = list(
        {
            normalize_url(u)
            for u in TARGET_URLS
            + SEED_URLS
            + [
                "https://kyu.ac.ug/about-admissions/",
                "https://kyu.ac.ug/undergraduate-programmes/",
            ]
        }
    )

    async with AsyncWebCrawler(verbose=False) as crawler:
        for base_url in hub_pages:
            try:
                result = await crawler.arun(url=base_url, config=config)
                if not result.success:
                    continue

                if result.links:
                    internal = result.links.get("internal", [])
                    for link in internal:
                        href = link.get("href", "")
                        if href:
                            norm = normalize_url(href)
                            if is_relevant_url(norm):
                                discovered.add(norm)

                if result.markdown:
                    for link in extract_links_from_markdown(result.markdown):
                        if is_relevant_url(link):
                            discovered.add(link)

            except Exception as exc:
                log.error(f"Link discovery failed for {base_url}: {exc}")

    relevant = sorted(discovered)
    log.info(f"Discovered {len(relevant)} relevant URLs")
    for url in relevant:
        log.debug(f"  • {url}")

    return relevant


async def discover_and_crawl() -> list[dict]:
    urls = await discover_urls()
    log.info("Phase 1b: Crawling all relevant pages …")
    return await crawl_with_crawl4ai(urls)


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

    if saved < MIN_SCRAPED_PAGES:
        log.warning(
            f"Only {saved} pages captured (target ≥ {MIN_SCRAPED_PAGES}). "
            "Some URLs may be unreachable — check logs/scraper.log."
        )
    else:
        log.info(f"✓ Verification passed: ≥ {MIN_SCRAPED_PAGES} pages captured.")


if __name__ == "__main__":
    asyncio.run(main())
