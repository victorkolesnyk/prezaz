"""
Build ChromaDB vector index from PDF files in the data/books/ directory.

Usage:
    python knowledge_base/build_index.py [--books-dir data/books] [--db-dir data/chroma_db]
"""

import argparse
import hashlib
import logging
import os
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "herbal_knowledge")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))


def read_pdf(path: Path) -> str:
    try:
        import PyPDF2

        text_parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        raise


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\sЀ-ӿ.,;:!?()\-–—\"'«»]", "", text)
    return text.strip()


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current_len + sentence_len > chunk_size and current:
            chunks.append(" ".join(current))
            overlap_words = " ".join(current).split()[-overlap:]
            current = [" ".join(overlap_words)]
            current_len = len(current[0])
        current.append(sentence)
        current_len += sentence_len + 1

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if len(c.strip()) > 50]


def chunk_id(source: str, index: int, text: str) -> str:
    digest = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{Path(source).stem}_{index}_{digest}"


def build_index(books_dir: str, db_dir: str) -> None:
    books_path = Path(books_dir)
    db_path = Path(db_dir)
    db_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(books_path.glob("**/*.pdf")) + list(books_path.glob("**/*.txt"))
    if not pdf_files:
        logger.warning("No PDF or TXT files found in %s", books_dir)
        return

    logger.info("Found %d files to index", len(pdf_files))

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    chroma_client = chromadb.PersistentClient(path=str(db_path))

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    total_chunks = 0

    for file_path in pdf_files:
        logger.info("Processing: %s", file_path.name)

        if file_path.suffix.lower() == ".pdf":
            raw_text = read_pdf(file_path)
        else:
            raw_text = file_path.read_text(encoding="utf-8", errors="ignore")

        text = clean_text(raw_text)
        if not text:
            logger.warning("Empty text in %s, skipping", file_path.name)
            continue

        chunks = split_into_chunks(text)
        logger.info("  → %d chunks", len(chunks))

        ids = [chunk_id(str(file_path), i, chunk) for i, chunk in enumerate(chunks)]
        metadatas = [{"source": file_path.name, "chunk_index": i} for i in range(len(chunks))]

        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=ids[start:end],
                documents=chunks[start:end],
                metadatas=metadatas[start:end],
            )

        total_chunks += len(chunks)

    logger.info("Index built: %d total chunks across %d files", total_chunks, len(pdf_files))
    logger.info("Collection '%s' has %d documents", COLLECTION_NAME, collection.count())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ChromaDB index from books")
    parser.add_argument("--books-dir", default="data/books", help="Directory with PDF/TXT books")
    parser.add_argument("--db-dir", default="data/chroma_db", help="ChromaDB storage directory")
    args = parser.parse_args()

    build_index(args.books_dir, args.db_dir)


if __name__ == "__main__":
    main()
