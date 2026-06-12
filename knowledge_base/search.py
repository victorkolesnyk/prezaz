"""
Search ChromaDB vector index for relevant herbal knowledge.

Usage:
    python knowledge_base/search.py "ромашка лікувальні властивості"
"""

import argparse
import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "herbal_knowledge")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma_db")
TOP_K = int(os.getenv("TOP_K_RESULTS", "5"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))


def get_collection():
    try:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    except Exception:
        ef = embedding_functions.DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def search(query: str, top_k: int = TOP_K) -> list[dict]:
    collection = get_collection()

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1 - dist
        if similarity >= SIMILARITY_THRESHOLD:
            hits.append({"text": doc, "source": meta.get("source", ""), "similarity": similarity})

    return hits


def format_context(hits: list[dict]) -> str:
    if not hits:
        return ""
    parts = []
    for hit in hits:
        parts.append(f"[{hit['source']}]\n{hit['text']}")
    return "\n\n---\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search herbal knowledge base")
    parser.add_argument("query", help="Search query in Ukrainian")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()

    hits = search(args.query, args.top_k)
    if not hits:
        print("Нічого не знайдено.")
        return

    for i, hit in enumerate(hits, 1):
        print(f"\n{'='*60}")
        print(f"[{i}] {hit['source']} (схожість: {hit['similarity']:.2f})")
        print(hit["text"])


if __name__ == "__main__":
    main()
