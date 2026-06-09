"""Load raw text from every source listed in documents/sources.json.

This script is intentionally *only* the loading step. It does not strip
boilerplate, normalize whitespace, or otherwise clean — those steps belong to
the chunker. We just want every document, regardless of origin, written to disk
in the same shape so downstream cleaning has a uniform input.

For URL sources: GET the page, decode as UTF-8 (via requests' apparent encoding
when the server omits a charset), and extract visible text with
BeautifulSoup's `get_text(separator="\\n")`. Script/style/noscript tags are
removed because their contents are not visible page text — keeping them would
pollute the "raw" file with JS source.

For local sources (url == "manual-sample"): read the existing file under
documents/ verbatim.

Output:
  documents/raw/<source_id>.txt   raw text for each source, with a small
                                  provenance header so the file is
                                  self-describing.
  documents/raw/manifest.json     per-source metadata (url, fetched_at,
                                  byte size, source_type).

Run: python -m src.load_documents
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "documents"
SOURCES_FILE = DOCS_DIR / "sources.json"
RAW_DIR = DOCS_DIR / "raw"
MANIFEST_FILE = RAW_DIR / "manifest.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
# Non-visible tags whose contents are never page text.
NON_TEXT_TAGS = ("script", "style", "noscript", "template")


@dataclass
class LoadedDoc:
    source_id: str
    title: str
    url: str
    tier: str
    source_type: str  # "url" or "local"
    fetched_at: str
    raw_path: str
    char_count: int


def fetch_url_text(url: str) -> str:
    """GET a URL and return visible page text. No chrome stripping."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    encoding = resp.apparent_encoding or "utf-8"
    html = resp.content.decode(encoding, errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag_name in NON_TEXT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    body = soup.body or soup
    # separator="\n" keeps block-level structure (one line per element) so the
    # cleaner downstream can detect paragraph breaks.
    return body.get_text(separator="\n", strip=False)


def load_local_text(file_name: str) -> str:
    return (DOCS_DIR / file_name).read_text(encoding="utf-8")


def write_raw(source_id: str, header: dict, body: str) -> Path:
    """Write the raw text with a small provenance header so each file is
    self-describing without needing the manifest."""
    out = RAW_DIR / f"{source_id}.txt"
    head_lines = [
        f"# source_id: {source_id}",
        f"# title: {header['title']}",
        f"# url: {header['url']}",
        f"# source_type: {header['source_type']}",
        f"# fetched_at: {header['fetched_at']}",
        f"# tier: {header['tier']}",
        "# --- begin raw text ---",
        "",
    ]
    out.write_text("\n".join(head_lines) + body, encoding="utf-8")
    return out


def main() -> int:
    RAW_DIR.mkdir(exist_ok=True)
    sources = json.loads(SOURCES_FILE.read_text())["sources"]

    loaded: list[LoadedDoc] = []
    failures: list[str] = []

    for src in sources:
        source_id = Path(src["file"]).stem
        url = src["url"]
        is_url = url.startswith(("http://", "https://"))
        source_type = "url" if is_url else "local"
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            print(f"loading {source_id}  ({source_type})…")
            body = fetch_url_text(url) if is_url else load_local_text(src["file"])
        except Exception as exc:  # noqa: BLE001 — surface any fetch/read error
            failures.append(f"{source_id}: {exc}")
            print(f"  FAILED: {exc}", file=sys.stderr)
            continue

        header = {
            "title": src["title"],
            "url": url,
            "source_type": source_type,
            "fetched_at": fetched_at,
            "tier": src["tier"],
        }
        path = write_raw(source_id, header, body)
        loaded.append(
            LoadedDoc(
                source_id=source_id,
                title=src["title"],
                url=url,
                tier=src["tier"],
                source_type=source_type,
                fetched_at=fetched_at,
                raw_path=str(path.relative_to(ROOT)),
                char_count=len(body),
            )
        )
        print(f"  wrote {path.name}  ({len(body):,} chars)")

    MANIFEST_FILE.write_text(
        json.dumps({"documents": [asdict(d) for d in loaded]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(loaded)} raw documents to {RAW_DIR}/")
    print(f"Manifest: {MANIFEST_FILE.relative_to(ROOT)}")

    if failures:
        print("\nFailures:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
