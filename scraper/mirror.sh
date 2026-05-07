#!/usr/bin/env bash
# scraper/mirror.sh
# ──────────────────
# Phase 1: Mirror KYU websites for local hosting (GitHub Pages / local file server).
#
# Usage:
#   chmod +x scraper/mirror.sh
#   ./scraper/mirror.sh
#
# Requires:
#   - wget  (usually pre-installed on Linux/macOS; Windows: https://eternallybored.org/misc/wget/)
#   - OR httrack (apt install httrack / brew install httrack)
#
# Output:
#   mirror/kyu.ac.ug/       – full static copy of the main site
#   mirror/admissions.kyu/  – full static copy of admissions subdomain

set -euo pipefail

MIRROR_DIR="$(pwd)/mirror"
mkdir -p "$MIRROR_DIR"

echo "════════════════════════════════════════"
echo " KYU Website Mirror Script"
echo "════════════════════════════════════════"

# ── Method A: wget (more portable) ───────────────────────────────────────────
mirror_with_wget() {
    local url="$1"
    local out_dir="$2"
    echo "[wget] Mirroring $url → $out_dir"
    wget \
        --mirror \
        --convert-links \
        --adjust-extension \
        --page-requisites \
        --no-parent \
        --no-check-certificate \
        --timeout=30 \
        --tries=3 \
        --wait=1 \
        --random-wait \
        --user-agent="Mozilla/5.0 (compatible; KYU-Mirror-Bot/1.0)" \
        --directory-prefix="$out_dir" \
        "$url" \
        2>&1 | tee -a logs/mirror.log
    echo "[wget] Done: $url"
}

# ── Method B: httrack (better for complex sites) ─────────────────────────────
mirror_with_httrack() {
    local url="$1"
    local out_dir="$2"
    echo "[httrack] Mirroring $url → $out_dir"
    httrack "$url" \
        -O "$out_dir" \
        -r4 \
        --depth=4 \
        --ext-depth=2 \
        --connection-per-second=2 \
        --sockets=4 \
        --keep-links=4 \
        --robots=0 \
        2>&1 | tee -a logs/mirror.log
    echo "[httrack] Done: $url"
}

# ── Choose tool ───────────────────────────────────────────────────────────────
if command -v httrack &>/dev/null; then
    echo "Using httrack …"
    mirror_with_httrack "https://www.kyu.ac.ug/"        "$MIRROR_DIR/kyu.ac.ug"
    mirror_with_httrack "https://admissions.kyu.ac.ug/" "$MIRROR_DIR/admissions.kyu"
elif command -v wget &>/dev/null; then
    echo "Using wget …"
    mirror_with_wget "https://www.kyu.ac.ug/"        "$MIRROR_DIR"
    mirror_with_wget "https://admissions.kyu.ac.ug/" "$MIRROR_DIR"
else
    echo "ERROR: Neither httrack nor wget found."
    echo "  Linux:  sudo apt install httrack wget"
    echo "  macOS:  brew install httrack wget"
    echo "  Windows: https://www.httrack.com/page/2/"
    exit 1
fi

echo ""
echo "════════════════════════════════════════"
echo " Mirror complete → $MIRROR_DIR"
echo " To serve locally:"
echo "   cd $MIRROR_DIR && python -m http.server 8080"
echo " Then open: http://localhost:8080"
echo "════════════════════════════════════════"
