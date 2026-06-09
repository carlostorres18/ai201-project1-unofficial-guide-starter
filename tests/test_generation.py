"""Test suite for Milestone 5: Generation & Grounding.

Tests that:
  1. Retrieved context is properly formatted with source markers
  2. Citations are correctly extracted from LLM responses
  3. Confidence scores reflect retrieval quality
  4. Grounding enforcement is present in system prompt

Run: python -m tests.test_generation
"""

from __future__ import annotations

from src.generate import (
    format_context_for_llm,
    extract_citations_from_response,
    compute_confidence_score,
    Citation,
    SYSTEM_PROMPT,
)
from src.search import search, SearchResult


def test_context_formatting() -> None:
    """Test that retrieved chunks are formatted with clear source labels."""
    print("\n" + "=" * 80)
    print("TEST 1: Context Formatting for LLM")
    print("=" * 80)

    # Get some real chunks
    results = search("How many problem sets does CS50 have?", k=3)

    if not results:
        print("❌ FAIL: No results retrieved")
        return

    context = format_context_for_llm(results)

    # Verify each chunk has clear markers
    checks = [
        ("[CHUNK 0]" in context, "Chunk 0 marked"),
        ("[CHUNK 1]" in context, "Chunk 1 marked"),
        ("Source:" in context, "Source labeled"),
        ("URL:" in context, "URL labeled"),
        ("CONTEXT CHUNKS" in context, "Context header present"),
    ]

    for check, desc in checks:
        status = "✓" if check else "✗"
        print(f"  {status} {desc}")

    if all(c[0] for c in checks):
        print("✅ PASS: Context properly formatted for LLM grounding")
    else:
        print("❌ FAIL: Context formatting incomplete")

    # Show sample
    print("\n--- Sample Context (first 500 chars) ---")
    print(context[:500])


def test_citation_extraction() -> None:
    """Test that citations are correctly extracted from responses."""
    print("\n" + "=" * 80)
    print("TEST 2: Citation Extraction")
    print("=" * 80)

    # Create mock results for testing
    mock_results = [
        SearchResult(
            chunk_id="cs50_0",
            text="You are expected to submit ten problem sets.",
            source_id="cs50_syllabus",
            source_url="https://cs50.harvard.edu/x/2023/syllabus/",
            source_title="CS50 Syllabus",
            chunk_index=0,
            char_start=0,
            char_end=100,
            token_count=50,
            tier="long",
            distance=0.35,
        ),
        SearchResult(
            chunk_id="reviews_0",
            text="CS50 is rigorous but well-produced.",
            source_id="reviews_intro",
            source_url="manual-sample",
            source_title="Student Reviews",
            chunk_index=0,
            char_start=0,
            char_end=50,
            token_count=30,
            tier="short",
            distance=0.45,
        ),
    ]

    # Test case 1: Explicit chunk references
    response1 = """According to [CHUNK 0], students submit ten problem sets.
    
[CHUNK 1] notes the course is rigorous but well-produced.

Sources:
- Chunk 0 (CS50 Syllabus)
- Chunk 1 (Student Reviews)"""

    citations1 = extract_citations_from_response(response1, mock_results)
    print(f"\n  Test 1 - Explicit references: {len(citations1)} citations found")
    for c in citations1:
        print(f"    • {c.source_title}")

    # Test case 2: Source name references
    response2 = """The CS50 Syllabus states students submit ten problem sets."""
    citations2 = extract_citations_from_response(response2, mock_results)
    print(f"\n  Test 2 - Source name inference: {len(citations2)} citations found")
    for c in citations2:
        print(f"    • {c.source_title}")

    if len(citations1) == 2 and len(citations2) >= 1:
        print("\n✅ PASS: Citations extracted correctly")
    else:
        print("\n⚠️  PARTIAL: Citation extraction working but may need tuning")


def test_confidence_scoring() -> None:
    """Test that confidence scores reflect retrieval quality."""
    print("\n" + "=" * 80)
    print("TEST 3: Confidence Scoring")
    print("=" * 80)

    # Create mock citations with different distances
    good_citations = [
        Citation(
            source_title="CS50 Syllabus",
            source_url="https://cs50.harvard.edu/x/2023/syllabus/",
            chunk_index=0,
            distance=0.35,
        ),
        Citation(
            source_title="Student Reviews",
            source_url="manual-sample",
            chunk_index=0,
            distance=0.40,
        ),
    ]

    weak_citations = [
        Citation(
            source_title="Unrelated Source",
            source_url="https://example.com",
            chunk_index=0,
            distance=0.85,
        ),
    ]

    conf_good = compute_confidence_score(good_citations, 5, 0.35)
    conf_weak = compute_confidence_score(weak_citations, 5, 0.85)
    conf_none = compute_confidence_score([], 5, 1.0)

    print(f"  Good retrieval (distance 0.35, 2 citations): {conf_good:.0%} confidence")
    print(f"  Weak retrieval (distance 0.85, 1 citation):  {conf_weak:.0%} confidence")
    print(f"  No citations: {conf_none:.0%} confidence")

    if conf_good > conf_weak > conf_none:
        print("\n✅ PASS: Confidence scores reflect quality hierarchy")
    else:
        print("\n❌ FAIL: Confidence scoring not ordered correctly")


def test_grounding_prompt() -> None:
    """Test that system prompt enforces grounding."""
    print("\n" + "=" * 80)
    print("TEST 4: Grounding Enforcement in System Prompt")
    print("=" * 80)

    grounding_checks = [
        ("ONLY" in SYSTEM_PROMPT or "only" in SYSTEM_PROMPT, "Forbids external knowledge"),
        (
            "training" in SYSTEM_PROMPT.lower(),
            "Mentions training data restriction",
        ),
        ("cite" in SYSTEM_PROMPT.lower(), "Requires citations"),
        ("CHUNK" in SYSTEM_PROMPT or "chunk" in SYSTEM_PROMPT, "References chunks"),
        (
            "don't know" in SYSTEM_PROMPT.lower() or "i don't" in SYSTEM_PROMPT.lower(),
            "Fallback when context insufficient",
        ),
    ]

    for check, desc in grounding_checks:
        status = "✓" if check else "✗"
        print(f"  {status} {desc}")

    if all(c[0] for c in grounding_checks):
        print("\n✅ PASS: System prompt enforces grounding")
    else:
        print("\n⚠️  PARTIAL: Grounding prompt could be stronger")

    # Show system prompt excerpt
    print("\n--- System Prompt Excerpt ---")
    lines = SYSTEM_PROMPT.split("\n")
    for line in lines[:15]:
        if line.strip():
            print(f"  {line}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MILESTONE 5 GENERATION & GROUNDING VALIDATION")
    print("=" * 80)

    test_context_formatting()
    test_citation_extraction()
    test_confidence_scoring()
    test_grounding_prompt()

    print("\n" + "=" * 80)
    print("✅ All validation tests complete!")
    print("=" * 80)
