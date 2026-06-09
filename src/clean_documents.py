"""Clean each raw document into substantive content only.

Reads:  documents/raw/<source_id>.txt   (produced by src.load_documents)
Writes: documents/cleaned/<source_id>.txt

What the cleaner removes:
  - HTML entities (&amp;, &nbsp;, ...) decoded via html.unescape
  - Repeated nav/footer/sidebar chrome (de-duped per document, last-seen wins)
  - Known boilerplate strings (site-wide chrome that appears on every page)
  - Material icon font names that leak through OCW's text extraction
    (e.g. "notes", "theaters", "assignment_turned_in")
  - "Show more" / "Show less" / "Read more" UI toggles, including the
    truncated text-preview line that ends with an ellipsis
  - Multi-line site disclaimers and footer paragraphs
  - Image attribution fragments
  - Excessive blank-line runs (collapsed to a single paragraph break)

What the cleaner keeps:
  - Course descriptions, instructor names, learning resource types
  - Student-review text (reviews_*.txt pass through almost unchanged)
  - Section headings (Course Description, Topics, etc.)

Run: python -m src.clean_documents
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "documents" / "raw"
CLEAN_DIR = ROOT / "documents" / "cleaned"
MANIFEST_FILE = RAW_DIR / "manifest.json"

# Exact-match lines to strip (case-insensitive).
BOILERPLATE_EXACT = {
    # OCW sidebar/footer
    "browse course material",
    "course info",
    "download course",
    "menu",
    "search",
    "close",
    "show more",
    "show less",
    "give now",
    "about ocw",
    "help & faqs",
    "contact us",
    "accessibility",
    "creative commons license",
    "terms and conditions",
    "stay here",
    "continue",
    "proud member of:",
    "as taught in",
    "level",
    "departments",
    "instructors",
    # OCW sidebar page links (single-occurrence on course-root pages, never
    # appear in the substantive content blocks of the same page).
    "syllabus",
    "instructor insights",
    "readings",
    "lecture slides and code",
    "in-class questions and video solutions",
    "lecture 1", "lecture 2", "lecture 3", "lecture 4", "lecture 5",
    "lecture 6", "lecture 7", "lecture 8", "lecture 9",
    "lecture 10", "lecture 11", "lecture 12",
    "assignments",
    "calendar",
    "resource index",
    # Year/season fragments split awkwardly from "As Taught In: Fall 2016".
    "fall", "spring", "summer", "winter",
    # OCW material icon font names that leak as text
    "notes",
    "theaters",
    "assignment",
    "assignment_turned_in",
    "grading",
    # Open Syllabus chrome
    "explore",
    "latest posts",
    "the blog",
    "more",
    "about",
    "terms",
    "people",
    "share syllabi",
    "questions?",
    # Generic web chrome
    "read more",
    "learn more",
    "share",
    "tweet",
    "facebook",
    "twitter",
    "linkedin",
    "subscribe",
    "newsletter",
    "cookie policy",
    "privacy policy",
    # CS50 site-wide nav (per-course pages, community list, footer links).
    "this is cs50",
    "cs50’s introduction to computer science",
    "opencourseware",
    "donate",
    "zoom meetings",
    "cs50.ai",
    "ed discussion",
    "for q&a",
    "visual studio code",
    "cs50 educator workshop",
    "cs50x puzzle day",
    "what’s new for 2023?",
    "gallery of final projects",
    "seminars",
    "shorts",
    "cs50 certificate",
    "faqs",
    "gradebook",
    "staff",
    "apple tv",
    "edx",
    "freecodecamp",
    "google tv",
    "harvard extension school",
    "harvard summer school",
    "roku",
    "new",
    "manual pages",
    "style guide",
    "status page",
    "communities",
    "bluesky",
    "clubhouse",
    "discord",
    "ed",
    "facebook group",
    "facebook page",
    "github",
    "gitter",
    "instagram",
    "linkedin group",
    "linkedin page",
    "medium",
    "quora",
    "reddit",
    "slack",
    "snapchat",
    "soundcloud",
    "stack exchange",
    "q&a",
    "telegram",
    "tiktok",
    "threads",
    "x account",
    "x community",
    "youtube",
    "courses",
    "cs50x",
    "cs50 ai",
    "cs50 business",
    "cs50 cybersecurity",
    "cs50 for lawyers",
    "cs50 python",
    "cs50 r",
    "cs50 scratch",
    "cs50 sql",
    "cs50 web",
    "license",
    "cybersecurity",
    # CS50 weekly index ("Week 0", "Week 1", ... with topic on next line).
    "week 0", "week 1", "week 2", "week 3", "week 4", "week 5",
    "week 6", "week 7", "week 8", "week 9", "week 10",
    "scratch", "c", "arrays", "algorithms", "memory", "data structures",
    "python", "sql", "html, css, javascript", "flask", "emoji",
    # Open Syllabus nav.
    "sites",
    "analytics",
    "course matcher",
    "co-assignment galaxy",
    "print store",
    "about os analytics",
    "accounts and subscriptions",
    "team",
    "contact:",
    "[email protected]",
    "find us on facebook",
    "find us on twitter",
    "blog",
    "contact",
}

# Substrings that, if found in a line, mark the whole line as boilerplate.
BOILERPLATE_CONTAINS = (
    "all rights reserved",
    "follow us on",
    "this site uses cookies",
    "we use cookies",
)

# Regex patterns: copyright lines, multi-line disclaimer fragments.
BOILERPLATE_PATTERNS = (
    re.compile(r"^©\s*\d{4}"),
    re.compile(r"^\(c\)\s*\d{4}", re.IGNORECASE),
    re.compile(r"^including license rights", re.IGNORECASE),
    re.compile(r"^for any content on third party", re.IGNORECASE),
    re.compile(r"^of those sites and/or their content", re.IGNORECASE),
    re.compile(r"^nor does a link suggest", re.IGNORECASE),
)

# Junk-only lines (single digits, pure punctuation).
JUNK_PATTERNS = (
    re.compile(r"^\d{1,3}$"),
    re.compile(r"^[\W_]+$"),
)

# Whole-paragraph drop triggers: if any of these phrases appears anywhere in a
# paragraph (block separated by a blank line), drop the entire paragraph.
PARAGRAPH_DROP_MARKERS = (
    "you are leaving",
    "please be advised that external sites",
    "freely sharing knowledge",
    "over 2,500 courses",
    "licensed cc-by",
)

# Standalone 4-digit years on their own line are OCW "As Taught In" fragments.
YEAR_ONLY = re.compile(r"^(19|20)\d{2}$")


def strip_provenance_header(text: str) -> tuple[dict, str]:
    """Pull the `# key: value` header lines off the top, return (meta, body)."""
    marker = "# --- begin raw text ---"
    if marker not in text:
        return {}, text
    head, body = text.split(marker, 1)
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if line.startswith("# ") and ": " in line:
            key, val = line[2:].split(": ", 1)
            meta[key.strip()] = val.strip()
    return meta, body.lstrip("\n")


def is_boilerplate(line: str) -> bool:
    norm = line.lower().strip()
    if norm in BOILERPLATE_EXACT:
        return True
    if any(p in norm for p in BOILERPLATE_CONTAINS):
        return True
    if any(p.match(line) for p in BOILERPLATE_PATTERNS):
        return True
    return any(p.match(norm) for p in JUNK_PATTERNS)


def filter_line(ln: str) -> str:
    if not ln:
        return ""
    if is_boilerplate(ln):
        return ""
    # OCW "Show more" truncation preview always ends in an ellipsis.
    if ln.endswith("…") or ln.endswith("..."):
        return ""
    # Image-attribution fragments leaked from OCW course-card captions.
    if ln.startswith("(") or "licensed CC-BY" in ln:
        return ""
    # Year-only fragment ("As Taught In: Fall 2016" renders as "Fall\n2016\n").
    if YEAR_ONLY.match(ln):
        return ""
    return ln


NAV_RUN_THRESHOLD = 10  # consecutive short single-line paragraphs => sidebar
NAV_PARA_MAX_CHARS = 60


def is_navlike_paragraph(p: str) -> bool:
    """Short paragraph (joined to one line) with no internal sentence break.

    We join multi-line paragraphs first because HTML extraction sometimes
    splits a single label across lines (e.g. CS107's "12: Disclosure,
    Partiality, Generics and<br>void *" becomes a 2-line paragraph that's
    still semantically one nav entry).
    """
    joined = " ".join(p.split())
    if not joined:
        return False
    if len(joined) > NAV_PARA_MAX_CHARS:
        return False
    return not re.search(r"\.\s+\w", joined)


def strip_leading_navlike_run(paragraphs: list[str]) -> list[str]:
    """Drop a leading run of NAV_RUN_THRESHOLD+ nav-like paragraphs at the top
    of the document only.

    Mid-document lists (Topics, Learning Resource Types, etc.) can also look
    nav-like in isolation but carry real meaning, so we leave them alone.
    """
    j = 0
    while j < len(paragraphs) and is_navlike_paragraph(paragraphs[j]):
        j += 1
    if j >= NAV_RUN_THRESHOLD:
        return paragraphs[j:]
    return paragraphs


def clean_text(raw: str) -> tuple[dict, str]:
    meta, body = strip_provenance_header(raw)

    # 1. Decode HTML entities (&amp;, &nbsp;, &#8211; ...).
    body = html.unescape(body)
    # 2. NBSP -> space.
    body = body.replace(" ", " ")

    # 3a. Paragraph-level drops (multi-line chrome blocks).
    paragraphs = re.split(r"\n\s*\n", body)
    paragraphs = [
        p for p in paragraphs
        if not any(m in p.lower() for m in PARAGRAPH_DROP_MARKERS)
    ]
    # 3b. Drop a long leading nav-like paragraph run (e.g. CS107 sidebar).
    paragraphs = strip_leading_navlike_run(paragraphs)
    body = "\n\n".join(paragraphs)

    # 4. Per-line filter + strip.
    lines = [filter_line(ln.strip()) for ln in body.split("\n")]

    # 5. Dedupe identical non-empty lines; last-seen wins so the latest
    # occurrence (typically the one near actual section headers) survives.
    last_idx: dict[str, int] = {}
    for idx, ln in enumerate(lines):
        if ln:
            last_idx[ln] = idx
    deduped: list[str] = []
    for idx, ln in enumerate(lines):
        if not ln:
            deduped.append("")
            continue
        if last_idx.get(ln) != idx:
            continue
        deduped.append(ln)

    # 6. Collapse blank-line runs.
    collapsed: list[str] = []
    prev_blank = True
    for ln in deduped:
        if not ln:
            if not prev_blank:
                collapsed.append("")
                prev_blank = True
            continue
        collapsed.append(ln)
        prev_blank = False

    cleaned = "\n".join(collapsed).strip() + "\n"
    return meta, cleaned


def render_with_header(meta: dict, body: str) -> str:
    head = [
        f"# source_id: {meta.get('source_id', '')}",
        f"# title: {meta.get('title', '')}",
        f"# url: {meta.get('url', '')}",
        f"# tier: {meta.get('tier', '')}",
        f"# fetched_at: {meta.get('fetched_at', '')}",
        "# --- begin cleaned text ---",
        "",
    ]
    return "\n".join(head) + body


def main() -> int:
    CLEAN_DIR.mkdir(exist_ok=True)
    manifest = json.loads(MANIFEST_FILE.read_text())
    summary: list[dict] = []

    for entry in manifest["documents"]:
        raw_path = ROOT / entry["raw_path"]
        raw = raw_path.read_text(encoding="utf-8")
        meta, cleaned = clean_text(raw)

        out = CLEAN_DIR / f"{entry['source_id']}.txt"
        out.write_text(render_with_header(meta, cleaned), encoding="utf-8")

        summary.append(
            {
                "source_id": entry["source_id"],
                "raw_chars": entry["char_count"],
                "cleaned_chars": len(cleaned),
                "reduction_pct": round(
                    100 * (1 - len(cleaned) / max(1, entry["char_count"])), 1
                ),
            }
        )
        print(
            f"  {entry['source_id']:32s}  "
            f"{entry['char_count']:>7,} -> {len(cleaned):>6,} chars  "
            f"(-{summary[-1]['reduction_pct']}%)"
        )

    (CLEAN_DIR / "summary.json").write_text(
        json.dumps({"documents": summary}, indent=2) + "\n"
    )
    print(f"\nWrote {len(summary)} cleaned documents to {CLEAN_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
