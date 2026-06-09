"""Retrieval stage: semantic search over ChromaDB index.

Provides a search() function that:
  1. Performs top-k semantic search over embedded chunks
  2. Returns results with metadata for source attribution
  3. Optionally reranks results by relevance

Per planning.md Retrieval Approach:
  - Top-k: 5 retrieved chunks per query
  - Optional: simple lexical reranking to boost exact/substring matches

Use this module in Milestone 5 (generation) to retrieve context chunks for the LLM.

Example:
    from src.search import search
    results = search("what is CS50's workload like?", k=5, rerank=True)
    for result in results:
        print(f"Source: {result['source_title']} (chunk {result['chunk_index']})")
        print(f"Text: {result['text'][:200]}...")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_db"
MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "course_reviews"


class SearchResult(NamedTuple):
    """A single search result: chunk text + metadata."""

    chunk_id: str
    text: str
    source_id: str
    source_url: str
    source_title: str
    chunk_index: int
    char_start: int
    char_end: int
    token_count: int
    tier: str
    distance: float  # Euclidean / cosine distance (lower = more relevant)


def get_or_init_model() -> SentenceTransformer:
    """Lazy-load embedding model."""
    if not hasattr(get_or_init_model, "_model"):
        get_or_init_model._model = SentenceTransformer(MODEL_NAME)
    return get_or_init_model._model


def search(
    query: str,
    k: int = 5,
    rerank: bool = True,
    include_distances: bool = True,
) -> list[SearchResult]:
    """
    Semantic search over the embedded chunks.

    Args:
        query: User's natural language query.
        k: Number of top results to return (default: 5 per planning.md).
        rerank: If True, apply simple lexical reranking to boost exact/substring matches.
        include_distances: If True, include cosine distance in results (useful for confidence).

    Returns:
        List of SearchResult tuples sorted by relevance.

    Raises:
        FileNotFoundError: If ChromaDB index does not exist (run: python -m src.embed).
    """
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"ChromaDB index not found: {CHROMA_DIR}\n"
            "Run: python -m src.embed"
        )

    # Initialize client and get collection
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(name=COLLECTION_NAME)

    # Encode query
    model = get_or_init_model()
    query_embedding = model.encode(query)

    # Query ChromaDB (top-k * 2 to allow for reranking)
    query_k = k * 2 if rerank else k
    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=query_k,
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    # Parse results
    chunk_results = []
    for idx, (chunk_id, text, metadata, distance) in enumerate(
        zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ):
        chunk_results.append(
            SearchResult(
                chunk_id=chunk_id,
                text=text,
                source_id=metadata["source_id"],
                source_url=metadata["source_url"],
                source_title=metadata["source_title"],
                chunk_index=int(metadata["chunk_index"]),
                char_start=int(metadata["char_start"]),
                char_end=int(metadata["char_end"]),
                token_count=int(metadata["token_count"]),
                tier=metadata["tier"],
                distance=float(distance),
            )
        )

    # Optional reranking: boost chunks that contain exact/substring matches to the query
    if rerank:
        query_lower = query.lower()
        query_tokens = set(query.lower().split())

        def rerank_score(result: SearchResult) -> float:
            """Higher score = better; lower distance is better, bonus for token match."""
            text_lower = result.text.lower()
            source_lower = result.source_title.lower()
            
            # Token matching
            token_match_count = sum(1 for t in query_tokens if t in text_lower)
            exact_match_bonus = 0.5 if query_lower in text_lower else 0.0
            
            # Source-specific matching: if query mentions a specific course/source,
            # strongly prefer results from that source
            source_match_bonus = 0.0
            for token in query_tokens:
                if len(token) > 3 and (token in source_lower):  # "6.0001", "MIT", "CS107", etc.
                    source_match_bonus += 20.0

            # Penalize by distance, reward by token matches and source matches
            return (
                -result.distance * 100 
                + token_match_count * 5 
                + exact_match_bonus * 10
                + source_match_bonus
            )

        chunk_results.sort(key=rerank_score, reverse=True)

    # Return top-k
    return chunk_results[:k]


def format_search_results(results: list[SearchResult], show_full_text: bool = False) -> str:
    """Pretty-print search results."""
    if not results:
        return "No results found."

    output = []
    for i, result in enumerate(results, 1):
        output.append(f"\n--- Result {i} ---")
        output.append(f"Source: {result.source_title} ({result.source_id})")
        output.append(f"URL: {result.source_url}")
        output.append(f"Chunk: {result.chunk_index} | Tier: {result.tier}")
        output.append(f"Distance: {result.distance:.4f}")
        if show_full_text:
            output.append(f"Text:\n{result.text}")
        else:
            text_preview = result.text[:300].replace("\n", " ")
            output.append(f"Text (preview): {text_preview}...")
    return "\n".join(output)


if __name__ == "__main__":
    # Simple CLI for testing retrieval
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.search '<query>' [k] [--no-rerank]")
        print("Example: python -m src.search 'how hard is CS50?' 5 --rerank")
        sys.exit(1)

    query = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5
    rerank = "--no-rerank" not in sys.argv

    print(f"Query: {query}")
    print(f"Top-k: {k}, Reranking: {rerank}\n")

    results = search(query, k=k, rerank=rerank)
    print(format_search_results(results, show_full_text=False))
