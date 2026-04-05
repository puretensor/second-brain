#!/usr/bin/env python3
"""Embedding module for pureMind RAG.

Uses nomic-ai/nomic-embed-text-v1.5 (768-dim) via sentence-transformers.
Loads from HuggingFace cache (already downloaded on TC).

Usage:
    python3 embed.py "test query"              # Print embedding vector
    python3 embed.py --batch file1.txt file2.txt  # Batch embed from files
"""

import json
import sys
from functools import lru_cache

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
MODEL_REVISION = "e5cf08aadaa33385f5990def41f7a23405aec398"  # Pinned for reproducibility
EMBED_DIM = 768


@lru_cache(maxsize=1)
def _load_model():
    """Load the sentence-transformers model (cached singleton)."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME, trust_remote_code=True, revision=MODEL_REVISION)
        return model
    except ImportError:
        print("ERROR: sentence-transformers not installed. Run: pip3 install --user sentence-transformers", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to load embedding model '{MODEL_NAME}': {e}", file=sys.stderr)
        sys.exit(1)



def embed_query(text: str) -> list[float]:
    """Embed a single query. Uses 'search_query: ' prefix for nomic model."""
    model = _load_model()
    vec = model.encode([f"search_query: {text}"], show_progress_bar=False, normalize_embeddings=True)
    return vec[0].tolist()


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed documents for indexing. Uses 'search_document: ' prefix."""
    if not texts:
        return []
    model = _load_model()
    prefixed = [f"search_document: {t}" for t in texts]
    embeddings = model.encode(prefixed, show_progress_bar=False, normalize_embeddings=True)
    return [vec.tolist() for vec in embeddings]


def embedding_to_pgvector(vec: list[float]) -> str:
    """Convert embedding list to pgvector literal string."""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


def main():
    if len(sys.argv) < 2:
        print("Usage: embed.py <text>", file=sys.stderr)
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    vec = embed_query(text)
    print(f"Dimension: {len(vec)}")
    print(f"First 5: {vec[:5]}")
    print(f"Norm: {sum(v*v for v in vec):.6f}")


if __name__ == "__main__":
    main()
