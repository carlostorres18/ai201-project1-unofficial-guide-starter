"""Embedding stage: load chunks and store in ChromaDB.

Reads chunks from chunks/chunks.jsonl (produced by src.ingest_and_chunk),
embeds each one using sentence-transformers/all-MiniLM-L6-v2, and stores
vectors + metadata in ChromaDB for fast retrieval.

Per planning.md Retrieval Approach:
  - Model: sentence-transformers/all-MiniLM-L6-v2
  - Top-k: 5 retrieved chunks per query (with optional reranking)
  - Storage: ChromaDB for local vector index

ChromaDB is persisted to chroma_db/ (local SQLite + embeddings cache).

Run: python -m src.embed
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import chromadb
import chromadb.errors
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_JSONL = ROOT / "chunks" / "chunks.jsonl"
CHROMA_DIR = ROOT / "chroma_db"

# Per planning.md: lightweight, fast local model good for mixed formal + informal text
MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "course_reviews"


def load_chunks() -> list[dict]:
    """Load chunks from chunks.jsonl; each line is a Chunk record (JSON)."""
    if not CHUNKS_JSONL.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {CHUNKS_JSONL}\n"
            "Run: python -m src.ingest_and_chunk"
        )

    chunks = []
    with open(CHUNKS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def create_or_get_collection(client: chromadb.Client):
    """Create or retrieve the ChromaDB collection."""
    # Delete existing collection if it exists (clean slate for re-indexing)
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except (ValueError, chromadb.errors.NotFoundError):
        pass  # Collection doesn't exist yet

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def embed_and_store(chunks: list[dict]) -> None:
    """Embed chunks and store in ChromaDB with source metadata."""
    # Initialize client and collection
    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = create_or_get_collection(client)

    # Load embedding model
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    # Batch embed all chunks
    print(f"Embedding {len(chunks)} chunks...")
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True)

    # Store in ChromaDB with metadata
    print(f"Storing embeddings in ChromaDB collection '{COLLECTION_NAME}'...")
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Unique ID for this chunk (source_id + chunk_index)
        chunk_id = f"{chunk['source_id']}_chunk_{chunk['chunk_index']}"

        # Metadata (for filtering and source attribution)
        metadata = {
            "source_id": chunk["source_id"],
            "source_url": chunk["source_url"],
            "source_title": chunk["source_title"],
            "tier": chunk["tier"],
            "chunk_index": chunk["chunk_index"],
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
            "token_count": chunk["token_count"],
        }

        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding.tolist()],
            documents=[chunk["text"]],
            metadatas=[metadata],
        )

        if (i + 1) % 50 == 0:
            print(f"  Stored {i + 1} chunks...")

    print(f"✓ Indexed {len(chunks)} chunks in ChromaDB")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Embeddings: {embeddings.shape}")
    print(f"  ChromaDB storage: {CHROMA_DIR}")


if __name__ == "__main__":
    chunks = load_chunks()
    embed_and_store(chunks)
    print("\n✓ Embedding and indexing complete!")
