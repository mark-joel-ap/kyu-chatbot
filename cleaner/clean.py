"""
cleaner/clean.py
─────────────────
Phase 1, Step 3: Clean raw scraped Markdown files.

Responsibilities:
  - Remove duplicate headers/footers and navigation menus.
  - Strip irrelevant links and scripts.
  - Normalise whitespace and special characters.
  - Output clean Markdown files per page to data/cleaned/.

Usage:
    python cleaner/clean.py

Input:  data/raw/*.md
Output: data/cleaned/*.md
"""

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CLEANED_DIR, LOGS_DIR, RAW_DIR

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "cleaner.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("cleaner")

# ─── Regex patterns for noise removal ─────────────────────────────────────────
# Navigation-like lines (short lines that are just links)
_NAV_LINE = re.compile(r"^\s*\[([^\]]{1,40})\]\(https?://[^\)]+\)\s*$")

# Bare URLs on their own line (likely leftover nav/footer links)
_BARE_URL = re.compile(r"^\s*https?://\S+\s*$", re.MULTILINE)

# Markdown image syntax (not useful for text Q&A)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^\)]*\)")

# HTML comments (including our injected source/title comments)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Cookie / GDPR banners (common repeated text)
_COOKIE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"we use cookies.*?accept",
        r"privacy policy.*?learn more",
        r"this website uses cookies",
        r"by continuing.*?you agree",
    ]
]

# Repeated whitespace / excessive blank lines
_MULTI_BLANK = re.compile(r"\n{3,}")

# Unicode noise: zero-width spaces, non-breaking spaces, etc.
_UNICODE_NOISE = re.compile(r"[\u00a0\u200b\u200c\u200d\ufeff]")

# Social media share links
_SOCIAL = re.compile(
    r"\[(Share|Tweet|Facebook|WhatsApp|LinkedIn|Instagram|YouTube)[^\]]*\]\([^\)]*\)",
    re.IGNORECASE,
)

# "Skip to content" / accessibility helper links
_SKIP_LINKS = re.compile(
    r"\[(Skip to [^\]]+|Back to top|Jump to [^\]]*)\]\([^\)]*\)",
    re.IGNORECASE,
)

# Very short lines that are likely navigation crumbs
_CRUMB = re.compile(r"^[\s»›>|·•\-–—/\\]+$")


def remove_nav_footer_noise(text: str) -> str:
    """Remove lines that look like navigation menu items or footer links."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Skip cookie notice lines
        if any(p.search(line) for p in _COOKIE_PATTERNS):
            continue
        # Skip lines that are purely nav links
        if _NAV_LINE.match(line):
            continue
        # Skip social share links
        if _SOCIAL.search(line):
            continue
        # Skip skip-nav links
        if _SKIP_LINKS.search(line):
            continue
        # Skip breadcrumb-only lines
        if _CRUMB.match(line) and len(line.strip()) < 20:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def deduplicate_headings(text: str) -> str:
    """
    Remove consecutive duplicate lines (common when scrapers hit
    repeated site headers like the university name / tagline).
    """
    lines = text.splitlines()
    seen_headings: set[str] = set()
    result = []
    for line in lines:
        stripped = line.strip()
        # Only dedup heading lines (start with #)
        if stripped.startswith("#"):
            key = stripped.lower()
            if key in seen_headings:
                continue
            seen_headings.add(key)
        result.append(line)
    return "\n".join(result)


def normalise_whitespace(text: str) -> str:
    """Collapse excessive blank lines and strip trailing spaces."""
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Collapse 3+ blank lines → 2 blank lines
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def remove_unicode_noise(text: str) -> str:
    """Replace zero-width and non-breaking spaces with regular spaces."""
    text = _UNICODE_NOISE.sub(" ", text)
    # Normalise smart quotes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "--")
    return text


def clean_markdown(raw: str) -> str:
    """Full cleaning pipeline for one Markdown document."""
    # 1. Strip HTML comments (our source annotations)
    text = _HTML_COMMENT.sub("", raw)

    # 2. Remove image syntax (not useful for RAG)
    text = _MD_IMAGE.sub("", text)

    # 3. Remove bare URLs
    text = _BARE_URL.sub("", text)

    # 4. Remove nav / footer noise
    text = remove_nav_footer_noise(text)

    # 5. Deduplicate repeated headings
    text = deduplicate_headings(text)

    # 6. Fix unicode
    text = remove_unicode_noise(text)

    # 7. Normalise whitespace
    text = normalise_whitespace(text)

    return text


def is_content_rich_enough(text: str, min_words: int = 50) -> bool:
    """Return True if the cleaned text has enough content to be useful."""
    words = len(text.split())
    return words >= min_words


def clean_all() -> None:
    raw_files = sorted(RAW_DIR.glob("*.md"))
    if not raw_files:
        log.error(f"No .md files found in {RAW_DIR}. Run the scraper first.")
        sys.exit(1)

    log.info(f"Cleaning {len(raw_files)} files …")
    kept = skipped = 0

    for raw_path in raw_files:
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_markdown(raw_text)

        if not is_content_rich_enough(cleaned):
            log.debug(f"Skipping (too short after cleaning): {raw_path.name}")
            skipped += 1
            continue

        out_path = CLEANED_DIR / raw_path.name
        out_path.write_text(cleaned, encoding="utf-8")
        log.info(f"  ✓ {raw_path.name} ({len(cleaned):,} chars)")
        kept += 1

    log.info(
        f"Done. {kept} files cleaned → {CLEANED_DIR} | {skipped} skipped (too short)"
    )


if __name__ == "__main__":
    clean_all()
