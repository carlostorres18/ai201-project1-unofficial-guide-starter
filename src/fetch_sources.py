"""Fetch raw HTML for the five static course pages and save plaintext exports.

Replaces the WebFetch-based extraction (which returned AI-summarized markdown)
with a direct requests + BeautifulSoup pipeline. We strip nav/footer/script/style
tags, prefer the main content container when available, and write reasonably
clean plaintext that preserves paragraph structure.

Run: python -m src.fetch_sources
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "documents"
SOURCES_FILE = DOCS_DIR / "sources.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

# Tags whose contents are pure boilerplate / non-content.
STRIP_TAGS = ["script", "style", "noscript", "iframe", "svg", "form", "button"]
# Tags that almost always wrap site chrome.
STRIP_ROLE_TAGS = ["nav", "header", "footer", "aside"]
# Class/id substrings that signal site chrome rather than article body.
STRIP_CLASS_HINTS = (
    "nav",
    "menu",
    "footer",
    "header",
    "breadcrumb",
    "cookie",
    "social",
    "share",
    "subscribe",
    "newsletter",
    "sidebar",
    "advert",
)


@dataclass
class FetchTarget:
    file: str
    url: str
    title: str
    main_selectors: tuple[str, ...] = ()  # CSS selectors to prefer for main content


TARGETS: list[FetchTarget] = [
    FetchTarget(
        file="cs50_syllabus.txt",
        url="https://cs50.harvard.edu/x/2023/syllabus/",
        title="CS50x 2023 Syllabus (Harvard)",
        main_selectors=("main", "article", "div.content"),
    ),
    FetchTarget(
        file="cs107_stanford.txt",
        url="https://web.stanford.edu/class/cs107/",
        title="CS107: Computer Organization & Systems (Stanford)",
        main_selectors=("main", "#content", "div.container"),
    ),
    FetchTarget(
        file="mit_6_0001.txt",
        url="https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/",
        title="MIT OCW 6.0001 — Introduction to CS and Programming in Python (Fall 2016)",
        main_selectors=("main", "#course-content", "article"),
    ),
    FetchTarget(
        file="mit_6_006.txt",
        url="https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/",
        title="MIT OCW 6.006 — Introduction to Algorithms (Spring 2020)",
        main_selectors=("main", "#course-content", "article"),
    ),
    FetchTarget(
        file="open_syllabus.txt",
        url="https://opensyllabus.org/",
        title="Open Syllabus — Homepage",
        main_selectors=("main", "article", "section"),
    ),
]


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # requests falls back to ISO-8859-1 when Content-Type lacks a charset,
    # which mangles UTF-8 punctuation on pages like MIT OCW. Trust the bytes:
    # prefer the meta-detected encoding, then UTF-8.
    encoding = resp.apparent_encoding or "utf-8"
    return resp.content.decode(encoding, errors="replace")


def looks_like_chrome(tag) -> bool:
    """Heuristic: True if a tag's class/id/role suggests site chrome."""
    # Decomposed tags have attrs=None; nothing to inspect.
    if getattr(tag, "attrs", None) is None:
        return False
    if tag.name in STRIP_ROLE_TAGS:
        return True
    attrs = " ".join(
        str(v).lower()
        for v in (tag.get("class") or []) + [tag.get("id", ""), tag.get("role", "")]
    )
    return any(hint in attrs for hint in STRIP_CLASS_HINTS)


def extract_main(soup: BeautifulSoup, selectors: tuple[str, ...]) -> BeautifulSoup:
    """Return the most promising content container; fall back to <body>."""
    for sel in selectors:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 200:
            return node
    return soup.body or soup


def html_to_text(html: str, main_selectors: tuple[str, ...]) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Drop comments.
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    # Drop noise tags entirely.
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    main = extract_main(soup, main_selectors)

    # Within main, remove obvious chrome. Skip tags whose parent was already
    # decomposed (their attrs become None).
    for tag in list(main.find_all(True)):
        if getattr(tag, "attrs", None) is None:
            continue
        if looks_like_chrome(tag):
            tag.decompose()

    # Walk and serialize: keep headings/paragraphs/lists/code blocks as
    # newline-delimited plain text.
    lines: list[str] = []
    block_tags = {
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "li", "pre", "blockquote", "tr", "div",
    }
    seen: set[int] = set()

    for el in main.find_all(True):
        if el.name not in block_tags:
            continue
        # Skip if an ancestor block already emitted this content.
        if any(id(a) in seen for a in el.parents):
            continue
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name.startswith("h") and el.name[1:].isdigit():
            level = int(el.name[1])
            lines.append("\n" + "#" * level + " " + text)
        elif el.name == "li":
            lines.append("- " + text)
        else:
            lines.append(text)
        seen.add(id(el))

    raw = "\n".join(lines)
    # Normalize whitespace.
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def update_sources_manifest(retrieved_on: str = "2026-06-09") -> None:
    """Refresh sources.json so retrieval method reflects the new fetcher."""
    data = json.loads(SOURCES_FILE.read_text())
    by_file = {s["file"]: s for s in data["sources"]}
    for tgt in TARGETS:
        if tgt.file in by_file:
            by_file[tgt.file]["method"] = "requests + BeautifulSoup (raw HTML extraction)"
    data["retrieved_on"] = retrieved_on
    SOURCES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def main() -> int:
    DOCS_DIR.mkdir(exist_ok=True)
    failures: list[str] = []
    for tgt in TARGETS:
        try:
            print(f"fetching {tgt.url} …")
            html = fetch_html(tgt.url)
            text = html_to_text(html, tgt.main_selectors)
            header = f"# {tgt.title}\n\nSource URL: {tgt.url}\n\n"
            (DOCS_DIR / tgt.file).write_text(header + text + "\n", encoding="utf-8")
            print(f"  wrote {tgt.file}  ({len(text):,} chars)")
        except Exception as exc:  # noqa: BLE001 — surface any fetch error
            failures.append(f"{tgt.file}: {exc}")
            print(f"  FAILED: {exc}", file=sys.stderr)

    update_sources_manifest()

    if failures:
        print("\nFailures:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
