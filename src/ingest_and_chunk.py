"""Two-tier sentence-aware chunker for the Unofficial Guide.

Reads cleaned documents from documents/cleaned/*.txt (each file carries a
provenance header written by src.clean_documents) and splits each one per the
planning.md Chunking Strategy:
  - long tier:   1000 tokens / 200 overlap (syllabi, course hubs)
  - short tier:   300 tokens /  50 overlap (reviews, forum snippets)
  - documents shorter than the short-tier threshold (300 tokens) become a
    single chunk regardless of declared tier

Writes:
  chunks/chunks.jsonl   one Chunk record per line (text + metadata)
  chunks/inspection.md  per-source token stats, sentence-boundary spot check,
                        cap-violation count, overlap verification

Run: python -m src.ingest_and_chunk
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "documents" / "cleaned"
OUT_DIR = ROOT / "chunks"
OUT_JSONL = OUT_DIR / "chunks.jsonl"
OUT_INSPECT = OUT_DIR / "inspection.md"

# Mirrors the Chunking Strategy in planning.md. Do not change these numbers
# without updating planning.md to record the rationale.
TIER_CONFIG = {
    "long": {"chunk_tokens": 1000, "overlap_tokens": 200},
    "short": {"chunk_tokens": 300, "overlap_tokens": 50},
}
# Per planning.md: "When a document is shorter than the secondary threshold,
# keep it as a single chunk." That threshold is the short-tier chunk size.
SINGLE_CHUNK_THRESHOLD = TIER_CONFIG["short"]["chunk_tokens"]

ENCODER = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    source_id: str
    source_url: str
    source_title: str
    tier: str
    chunk_index: int
    char_start: int
    char_end: int
    token_count: int
    text: str


def n_tokens(text: str) -> int:
    return len(ENCODER.encode(text))


def normalize_whitespace(text: str) -> str:
    """Light whitespace pass. Substantive cleaning lives in src.clean_documents."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def parse_cleaned_file(path: Path) -> tuple[dict, str]:
    """Read a cleaned/<id>.txt file; return (provenance_meta, body_text)."""
    raw = path.read_text(encoding="utf-8")
    marker = "# --- begin cleaned text ---"
    if marker not in raw:
        return {"source_id": path.stem}, normalize_whitespace(raw)
    head, body = raw.split(marker, 1)
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if line.startswith("# ") and ": " in line:
            key, val = line[2:].split(": ", 1)
            meta[key.strip()] = val.strip()
    return meta, normalize_whitespace(body)


_SENT_BOUNDARY = re.compile(
    r"""
    (?<=[\.\!\?])              # sentence-ending punctuation
    (?=\s+[A-Z0-9\"\(\[#\-])   # followed by whitespace then capital/digit/markdown bullet
    |
    \n\n+                      # or a paragraph break
    |
    (?<=\n)(?=[#\-\*]\s)       # or start of a markdown heading/bullet line
    """,
    re.VERBOSE,
)


def split_sentences(text: str) -> list[str]:
    """Sentence/paragraph splitter that preserves bullets and markdown headings."""
    parts = _SENT_BOUNDARY.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_by_tokens(
    sentences: list[str],
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Greedy sentence packer. Each chunk stays under chunk_tokens; overlap is
    realized by re-seeding the next chunk with trailing sentences whose
    combined token count covers overlap_tokens."""
    if not sentences:
        return []

    sent_tokens = [n_tokens(s) for s in sentences]
    chunks: list[str] = []
    i = 0
    n = len(sentences)

    while i < n:
        # A sentence over the cap is emitted alone (rare in this corpus).
        if sent_tokens[i] >= chunk_tokens:
            chunks.append(sentences[i])
            i += 1
            continue

        current: list[str] = []
        j = i
        while j < n:
            candidate = " ".join(current + [sentences[j]])
            if n_tokens(candidate) > chunk_tokens:
                break
            current.append(sentences[j])
            j += 1

        # Ensure at least one sentence per chunk (over-cap sentences are
        # handled by the early-return branch above).
        if not current:
            current = [sentences[i]]
            j = i + 1

        chunks.append(" ".join(current))

        if j >= n:
            break

        # Build overlap window by walking back through trailing sentences.
        if overlap_tokens > 0 and len(current) > 1:
            tail_tokens = 0
            k = len(current) - 1
            tail_start_global = j - 1
            while k >= 0 and tail_tokens < overlap_tokens:
                tail_tokens += sent_tokens[i + k]
                tail_start_global = i + k
                k -= 1
            next_i = tail_start_global
            if next_i <= i:  # guarantee forward progress
                next_i = i + max(1, len(current) - 1)
            i = next_i
        else:
            i = j

    return chunks


def locate_span(haystack: str, needle: str, start_hint: int) -> tuple[int, int]:
    """Find needle in haystack at/after start_hint; fall back to a 40-char
    prefix probe if exact match fails (whitespace can shift slightly)."""
    pos = haystack.find(needle, start_hint)
    if pos == -1:
        pos = haystack.find(needle[:40], start_hint)
        if pos == -1:
            pos = max(0, start_hint)
    return pos, pos + len(needle)


def chunk_document(
    source_id: str,
    title: str,
    url: str,
    tier: str,
    body: str,
) -> list[Chunk]:
    cfg = TIER_CONFIG[tier]
    total_tokens = n_tokens(body)

    # Spec: documents under the short-tier threshold stay as a single chunk.
    if total_tokens <= SINGLE_CHUNK_THRESHOLD:
        return [
            Chunk(
                source_id=source_id,
                source_url=url,
                source_title=title,
                tier=tier,
                chunk_index=0,
                char_start=0,
                char_end=len(body),
                token_count=total_tokens,
                text=body,
            )
        ]

    sentences = split_sentences(body)
    raw_chunks = chunk_by_tokens(
        sentences,
        chunk_tokens=cfg["chunk_tokens"],
        overlap_tokens=cfg["overlap_tokens"],
    )

    chunks: list[Chunk] = []
    cursor = 0
    for idx, text in enumerate(raw_chunks):
        start, end = locate_span(body, text, max(0, cursor - 200))
        chunks.append(
            Chunk(
                source_id=source_id,
                source_url=url,
                source_title=title,
                tier=tier,
                chunk_index=idx,
                char_start=start,
                char_end=end,
                token_count=n_tokens(text),
                text=text,
            )
        )
        cursor = end
    return chunks


def longest_common_substring_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    m, k = len(a), len(b)
    prev = [0] * (k + 1)
    best = 0
    for i in range(1, m + 1):
        curr = [0] * (k + 1)
        for j in range(1, k + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best:
                    best = curr[j]
        prev = curr
    return best


def write_inspection_report(chunks: list[Chunk]) -> None:
    by_source: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_source.setdefault(c.source_id, []).append(c)

    lines: list[str] = []
    lines.append("# Chunk Inspection Report\n")
    lines.append(f"Total chunks: **{len(chunks)}**\n")
    lines.append(f"Sources: **{len(by_source)}**\n")
    lines.append("\n## Per-source summary\n")
    lines.append("| Source | Tier | Chunks | Avg tokens | Min | Max | Cap |")
    lines.append("|---|---|---|---|---|---|---|")
    for src_id, items in by_source.items():
        toks = [c.token_count for c in items]
        tier = items[0].tier
        cap = TIER_CONFIG[tier]["chunk_tokens"]
        lines.append(
            f"| {src_id} | {tier} | {len(items)} | "
            f"{sum(toks) // len(toks)} | {min(toks)} | {max(toks)} | {cap} |"
        )

    violations = [c for c in chunks if c.token_count > TIER_CONFIG[c.tier]["chunk_tokens"]]
    lines.append(f"\n## Token cap violations: {len(violations)}\n")
    for c in violations:
        lines.append(f"- {c.source_id}#{c.chunk_index}: {c.token_count} tokens")

    lines.append("\n## Sentence boundary spot check (5 random chunks)\n")
    sample = random.sample(chunks, min(5, len(chunks)))
    for c in sample:
        first = c.text[:120].replace("\n", " ")
        last = c.text[-120:].replace("\n", " ")
        lines.append(f"### {c.source_id} chunk {c.chunk_index} ({c.token_count} tok)")
        lines.append(f"- starts: `{first}…`")
        lines.append(f"- ends:   `…{last}`\n")

    lines.append("\n## Overlap verification\n")
    lines.append("Adjacent chunks in the same source should share trailing/leading text.")
    lines.append("")
    lines.append("| Source | Pair | Shared chars (≥) |")
    lines.append("|---|---|---|")
    for src_id, items in by_source.items():
        items_sorted = sorted(items, key=lambda c: c.chunk_index)
        for a, b in zip(items_sorted, items_sorted[1:]):
            # Window must exceed the expected overlap (~5-7 chars per token)
            # so LCS catches the full overlap region, not just its tail.
            window = TIER_CONFIG[a.tier]["overlap_tokens"] * 7
            shared = longest_common_substring_len(a.text[-window:], b.text[:window])
            lines.append(f"| {src_id} | {a.chunk_index}->{b.chunk_index} | {shared} |")

    OUT_INSPECT.write_text("\n".join(lines))


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    all_chunks: list[Chunk] = []

    for path in sorted(CLEAN_DIR.glob("*.txt")):
        meta, body = parse_cleaned_file(path)
        source_id = meta.get("source_id") or path.stem
        tier = meta.get("tier", "long")
        if tier not in TIER_CONFIG:
            tier = "long"
        chunks = chunk_document(
            source_id=source_id,
            title=meta.get("title", source_id),
            url=meta.get("url", ""),
            tier=tier,
            body=body,
        )
        all_chunks.extend(chunks)
        print(
            f"  {source_id:32s}  tier={tier:5s}  "
            f"chunks={len(chunks):3d}  total_tokens={sum(c.token_count for c in chunks)}"
        )

    with OUT_JSONL.open("w") as fh:
        for c in all_chunks:
            fh.write(json.dumps(asdict(c)) + "\n")

    write_inspection_report(all_chunks)

    print(f"\nWrote {len(all_chunks)} chunks to {OUT_JSONL}")
    print(f"Wrote inspection report to {OUT_INSPECT}")


if __name__ == "__main__":
    random.seed(0)
    main()
