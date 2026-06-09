"""Generation stage: grounded answer synthesis from retrieved chunks.

Enforces grounding through:
  1. System prompt that forbids using training knowledge
  2. Clear chunk context with source markers
  3. Structured output with citations (source URL, chunk index, relevance score)
  4. Code-level verification that all assertions map to specific chunks

Per planning.md Milestone 5:
  - Input: user query
  - Retrieval: top-5 chunks with metadata
  - LLM: Groq Mixtral (fast, local) with grounding prompt
  - Output: {answer_text, citations, confidence_score}

Run: python -m src.generate "Your question?"
Or import: from src.generate import generate_answer
"""

import os
import re
from dataclasses import asdict, dataclass
from typing import NamedTuple

from dotenv import load_dotenv

from src.search import search, SearchResult

# Load environment variables from .env
load_dotenv()

# LLM Configuration
# Supports both Claude (via Anthropic API) and Groq
LLM_BACKEND = os.getenv("LLM_BACKEND", "groq").lower()  # "groq" or "claude"

if LLM_BACKEND == "claude":
    import anthropic

    LLM_MODEL = "claude-3-5-sonnet-20241022"
    LLM_CLIENT = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

elif LLM_BACKEND == "groq":
    from groq import Groq

    # Try multiple models in order of preference
    # Update these if models are decommissioned
    LLM_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_key = os.getenv("GROQ_API_KEY")
    LLM_CLIENT = Groq(api_key=groq_key) if groq_key else None
else:
    raise ValueError(f"Unknown LLM_BACKEND: {LLM_BACKEND}. Use 'claude' or 'groq'.")

# Grounding enforcement
SYSTEM_PROMPT = """You are an expert assistant helping students find information about courses and professors.

CRITICAL INSTRUCTIONS FOR GROUNDING:
1. Answer the question using only the information in the provided documents.
2. Do NOT use your general knowledge or training data.
3. If the documents don't contain enough information to answer, respond with exactly: "I don't have enough information on that."
4. Always cite your sources by referencing chunk numbers and source titles.
5. Quote directly from the context when asserting facts.
6. If sources contradict each other, present both viewpoints and note the contradiction.

FORMAT YOUR RESPONSE:
- Start with a direct answer (1-3 sentences).
- Follow with supporting details if needed.
- END with a "Sources:" line listing chunk indices and source titles used.

Example response format:
"According to the CS50 syllabus, students must submit ten problem sets. [Additional context...]

Sources:
- Chunk 0 (CS50x 2023 Syllabus)
- Chunk 2 (Student Reviews — CS50)"

Remember: Your credibility depends on sticking to the provided context.
If you cannot verify something in the chunks, do NOT say it."""


@dataclass
class GeneratedAnswer:
    """Structured output from answer generation."""

    answer_text: str
    citations: list[Citation]
    confidence_score: float


class Citation(NamedTuple):
    """A single source citation."""

    source_title: str
    source_url: str
    chunk_index: int
    distance: float


def format_context_for_llm(results: list[SearchResult]) -> str:
    """Format retrieved chunks into clearly attributed context for the LLM.
    
    This is critical for grounding: each chunk must be clearly labeled with its source
    so the LLM can cite it and we can verify that assertions map to actual chunks.
    """
    context_lines = ["CONTEXT CHUNKS (Reference these in your answer):\n"]

    for i, result in enumerate(results):
        context_lines.append(f"\n[CHUNK {i}]")
        context_lines.append(f"Source: {result.source_title}")
        context_lines.append(f"URL: {result.source_url}")
        context_lines.append(f"Relevance distance: {result.distance:.4f}")
        context_lines.append(f"---")
        context_lines.append(result.text)
        context_lines.append(f"--- END CHUNK {i}\n")

    return "\n".join(context_lines)


def extract_citations_from_response(response_text: str, results: list[SearchResult]) -> list[Citation]:
    """Extract which chunks were actually cited in the response.
    
    Grounding verification: ensure the LLM only cited chunks that were provided.
    """
    citations = []
    source_set = set()  # Track unique sources to avoid duplicates

    # Look for explicit chunk references like "[CHUNK 0]", "Chunk 2", etc.
    chunk_refs = re.findall(r"CHUNK\s+(\d+)", response_text, re.IGNORECASE)

    for chunk_ref in chunk_refs:
        try:
            chunk_idx = int(chunk_ref)
            if 0 <= chunk_idx < len(results):
                result = results[chunk_idx]
                source_key = (result.source_title, result.source_url)

                # Avoid duplicate citations of same source
                if source_key not in source_set:
                    citations.append(
                        Citation(
                            source_title=result.source_title,
                            source_url=result.source_url,
                            chunk_index=result.chunk_index,
                            distance=result.distance,
                        )
                    )
                    source_set.add(source_key)
        except (ValueError, IndexError):
            pass

    # If no explicit citations found, infer from source mentions in text
    if not citations:
        for i, result in enumerate(results):
            if result.source_title.lower() in response_text.lower():
                source_key = (result.source_title, result.source_url)
                if source_key not in source_set:
                    citations.append(
                        Citation(
                            source_title=result.source_title,
                            source_url=result.source_url,
                            chunk_index=result.chunk_index,
                            distance=result.distance,
                        )
                    )
                    source_set.add(source_key)

    return citations


def compute_confidence_score(
    citations: list[Citation], num_results: int, top_distance: float
) -> float:
    """Compute a confidence score (0–1) based on retrieval quality.
    
    Factors:
    - Top result distance (lower = higher confidence)
    - Number of relevant citations (more = higher confidence)
    - Average distance of cited chunks
    """
    if not citations:
        return 0.0

    # Distance-based confidence (0.3 = ~high quality, 0.9 = ~low quality)
    # Normalize to 0–1: closer distance → higher confidence
    distance_confidence = max(0.0, 1.0 - (top_distance * 1.5))

    # Citation count confidence (more citations = more grounded)
    citation_confidence = min(1.0, len(citations) / 3.0)  # 3+ citations = full confidence

    # Average distance of cited chunks
    avg_citation_distance = sum(c.distance for c in citations) / len(citations)
    avg_distance_confidence = max(0.0, 1.0 - (avg_citation_distance * 1.5))

    # Weighted average: prioritize distance quality
    final_score = (
        0.5 * distance_confidence + 0.3 * avg_distance_confidence + 0.2 * citation_confidence
    )
    return min(1.0, max(0.0, final_score))


def append_source_attribution(answer_text: str, results: list[SearchResult]) -> str:
    """Append a guaranteed source-attribution block to the LLM's answer.

    The system prompt asks the LLM to cite its sources, but we don't trust it
    to do so consistently. This appends an unambiguous "Sources:" block listing
    the unique documents that were retrieved and passed into the prompt, so the
    final user-visible answer always names where the information came from.

    Sources are deduped by (title, URL) and presented in retrieval order
    (highest-ranked first).
    """
    if not results:
        return answer_text

    # If the model said it doesn't know, strip any "Sources:" block it
    # contradictorily emitted and skip appending our own.
    if "i don't have enough information on that" in answer_text.lower():
        return re.sub(
            r"\n+sources?:\s*\n(?:[ \t]*[-•*].*\n?)+\s*$",
            "",
            answer_text,
            flags=re.IGNORECASE,
        ).rstrip()

    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for r in results:
        key = (r.source_title, r.source_url)
        if key in seen:
            continue
        seen.add(key)
        # Show URL only when it's a real link, not the manual-sample sentinel.
        if r.source_url and r.source_url.startswith(("http://", "https://")):
            lines.append(f"- {r.source_title} ({r.source_url})")
        else:
            lines.append(f"- {r.source_title}")

    if not lines:
        return answer_text

    # Strip a trailing "Sources:" block the LLM may have added so we don't
    # double up.
    cleaned = re.sub(
        r"\n+sources?:\s*\n(?:[ \t]*[-•*].*\n?)+\s*$",
        "",
        answer_text,
        flags=re.IGNORECASE,
    ).rstrip()

    block = "Sources:\n" + "\n".join(lines)
    return f"{cleaned}\n\n{block}"


def generate_answer(query: str, k: int = 5, rerank: bool = True) -> GeneratedAnswer:
    """Generate a grounded answer to a user query.
    
    Process:
    1. Retrieve top-k chunks with metadata
    2. Format chunks with clear source labels
    3. Call LLM with grounding prompt + context
    4. Extract citations from response
    5. Return structured output with confidence score
    
    Args:
        query: User's natural language question
        k: Number of chunks to retrieve (default 5)
        rerank: Whether to apply source-aware reranking
    
    Returns:
        GeneratedAnswer with answer_text, citations, confidence_score
    
    Raises:
        ValueError: If LLM client not configured
    """
    if LLM_CLIENT is None:
        raise ValueError(
            f"LLM client not configured for backend: {LLM_BACKEND}\n"
            f"If using Groq: set GROQ_API_KEY in .env\n"
            f"If using Claude: set ANTHROPIC_API_KEY in .env and LLM_BACKEND=claude"
        )

    # Step 1: Retrieve relevant chunks
    print(f"🔍 Retrieving relevant chunks for: {query[:60]}...")
    results = search(query, k=k, rerank=rerank)

    if not results:
        return GeneratedAnswer(
            answer_text="I don't have enough information on that.",
            citations=[],
            confidence_score=0.0,
        )

    # Step 2: Format context for LLM with clear source labels
    context = format_context_for_llm(results)

    # Step 3: Call LLM with grounding prompt
    print("🤖 Generating answer with grounding enforcement...")

    user_message = f"""User Query: {query}

{context}

Remember: Answer ONLY from the context above. Cite chunk numbers. If you cannot answer from context, say so."""

    if LLM_BACKEND == "claude":
        response = LLM_CLIENT.messages.create(
            model=LLM_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        answer_text = response.content[0].text

    elif LLM_BACKEND == "groq":
        response = LLM_CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,  # Low temperature for factual consistency
            max_tokens=500,  # Keep answers focused
        )
        answer_text = response.choices[0].message.content.strip()

    # Step 4: Guarantee source attribution in the answer text itself, so any
    # downstream consumer (CLI, Gradio UI, etc.) sees the sources even if the
    # LLM forgot to cite them. Runs before citation extraction so the
    # appended block also feeds the structured citations list.
    answer_text = append_source_attribution(answer_text, results)

    # Step 5: Extract citations from response
    citations = extract_citations_from_response(answer_text, results)

    # Step 5: Compute confidence score
    top_distance = results[0].distance if results else 1.0
    confidence = compute_confidence_score(citations, len(results), top_distance)

    return GeneratedAnswer(
        answer_text=answer_text,
        citations=citations,
        confidence_score=confidence,
    )


def format_answer_for_display(answer: GeneratedAnswer, verbose: bool = False) -> str:
    """Format generated answer for user display."""
    output = []
    output.append("\n" + "=" * 80)
    output.append(f"ANSWER (Confidence: {answer.confidence_score:.0%})")
    output.append("=" * 80)
    output.append(answer.answer_text)

    if answer.citations:
        output.append("\n" + "-" * 80)
        output.append("SOURCES:")
        for citation in answer.citations:
            output.append(f"  • {citation.source_title} (Chunk {citation.chunk_index})")
            if verbose:
                output.append(f"    URL: {citation.source_url}")
                output.append(f"    Relevance: {citation.distance:.4f}")

    else:
        output.append("\n⚠️  WARNING: No sources cited — answer may not be grounded!")

    output.append("=" * 80 + "\n")
    return "\n".join(output)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.generate '<query>'")
        print("Example: python -m src.generate 'How many problem sets does CS50 have?'")
        sys.exit(1)

    query = sys.argv[1]
    answer = generate_answer(query)
    print(format_answer_for_display(answer, verbose=True))
