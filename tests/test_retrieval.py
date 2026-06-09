"""Test suite for Milestone 4: Embedding & Retrieval.

Tests that semantic search retrieves relevant chunks for the evaluation queries
defined in planning.md. Run this BEFORE moving to Milestone 5 (generation).

Usage:
    python -m tests.test_retrieval

Tests:
  1. Check that all evaluation queries return k=5 results
  2. Verify expected facts are present in top-k for each query
  3. Report precision@5 and average distance for each query
  4. Flag warnings for queries with weak retrieval
"""

from __future__ import annotations

from src.search import search


# Evaluation queries from planning.md
EVAL_QUERIES = [
    {
        "id": 1,
        "query": "How many problem sets does CS50 expect students to submit?",
        "expected_in_top_5": ["ten problem sets", "10 problem sets", "problem sets"],
        "sources": ["CS50"],
    },
    {
        "id": 2,
        "query": "Where does Stanford CS107 post course announcements?",
        "expected_in_top_5": ["Ed Discussion", "course page", "announcements"],
        "sources": ["CS107", "Stanford"],
    },
    {
        "id": 3,
        "query": "Who is MIT 6.0001 designed for?",
        "expected_in_top_5": [
            "little or no programming experience",
            "no prior coding experience",
            "beginners",
        ],
        "sources": ["6.0001", "MIT"],
    },
    {
        "id": 4,
        "query": "What resources does MIT 6.006 provide?",
        "expected_in_top_5": [
            "lecture notes",
            "problem sets",
            "exam",
            "videos",
            "learning resource",
        ],
        "sources": ["6.006", "MIT"],
    },
    {
        "id": 5,
        "query": "How many syllabi does Open Syllabus map?",
        "expected_in_top_5": ["32.9 million", "million syllabi", "curriculum"],
        "sources": ["Open Syllabus"],
    },
]


def check_expected_content(result_text: str, expected_phrases: list[str]) -> bool:
    """Check if any expected phrase appears in the result (case-insensitive)."""
    text_lower = result_text.lower()
    return any(phrase.lower() in text_lower for phrase in expected_phrases)


def test_retrieval() -> None:
    """Run retrieval tests against evaluation queries."""
    print("=" * 70)
    print("RETRIEVAL TEST SUITE (Milestone 4)")
    print("=" * 70)

    total_queries = len(EVAL_QUERIES)
    passed_queries = 0
    precision_sum = 0.0

    for query_info in EVAL_QUERIES:
        query_id = query_info["id"]
        query_text = query_info["query"]
        expected = query_info["expected_in_top_5"]
        sources = query_info["sources"]

        print(f"\n[Query {query_id}] {query_text}")
        print(f"  Expected sources: {', '.join(sources)}")
        print(f"  Expected content: {', '.join(expected)}")

        # Retrieve top-5
        results = search(query_text, k=5, rerank=True)

        if not results:
            print(f"  ❌ FAIL: No results returned")
            continue

        # Check result count
        if len(results) < 5:
            print(f"  ⚠️  WARNING: Only {len(results)} results (expected 5)")

        # Check for expected content in top results
        found_match = False
        avg_distance = sum(r.distance for r in results) / len(results)

        for i, result in enumerate(results, 1):
            match = check_expected_content(result.text, expected)
            source_match = any(src.lower() in result.source_title.lower() for src in sources)

            if match and source_match:
                found_match = True
                print(f"  ✓ Result {i}: Found expected content in {result.source_title}")
                print(f"    Distance: {result.distance:.4f}")
                break

        if found_match:
            print(f"  ✓ PASS: Expected content retrieved")
            passed_queries += 1
            precision = 1.0
        else:
            # Partial credit if expected content is in any result
            partial_match = False
            for result in results:
                if check_expected_content(result.text, expected):
                    partial_match = True
                    precision = 0.4
                    print(f"  ⚠️  PARTIAL: Found content but wrong source ({result.source_title})")
                    break

            if not partial_match:
                print(f"  ❌ FAIL: Expected content not in top-5")
                precision = 0.0

        precision_sum += precision
        print(f"  Top-5 avg distance: {avg_distance:.4f}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    avg_precision = precision_sum / total_queries if total_queries > 0 else 0
    print(f"Passed: {passed_queries}/{total_queries}")
    print(f"Avg Precision@5: {avg_precision:.2%}")

    if avg_precision >= 0.8:
        print("✓ Retrieval is READY for Milestone 5 (generation)")
    else:
        print("⚠️  Retrieval needs tuning before moving to generation")
        print("  Consider:")
        print("    - Increasing overlap in chunking (Chunking Strategy)")
        print("    - Adjusting k or reranking thresholds")
        print("    - Reviewing source document coverage")

    print("=" * 70)


if __name__ == "__main__":
    test_retrieval()
