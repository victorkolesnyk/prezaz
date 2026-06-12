"""
Скрипт інгесту книг у векторну базу ChromaDB.

Використання:
    python scripts/ingest.py
    python scripts/ingest.py --books-path data/books --reset
"""

import sys
import os
import logging
import argparse
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from typing import List, Tuple, Dict, Any

from config.settings import settings
from rag.vectorstore import get_vector_store
from scripts.process_text import process_file

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".md"}


def generate_chunk_id(source: str, chunk_index: int, text: str) -> str:
    """Генерує детермінований унікальний ID для чанку."""
    content = f"{source}_{chunk_index}_{text[:50]}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def find_book_files(books_path: str) -> List[Path]:
    """Знаходить усі підтримувані файли в директорії."""
    path = Path(books_path)
    if not path.exists():
        logger.error(f"Директорія не існує: {books_path}")
        return []

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(path.rglob(f"*{ext}"))

    # Виключаємо .gitkeep та схожі файли-заглушки
    files = [f for f in files if f.stat().st_size > 100]
    logger.info(f"Знайдено {len(files)} файлів у {books_path}")
    return sorted(files)


def ingest_file(
    file_path: Path,
    vector_store,
    chunk_size: int,
    overlap: int,
) -> int:
    """
    Завантажує один файл до векторної бази.

    Returns:
        Кількість доданих чанків
    """
    logger.info(f"Обробка: {file_path.name}")

    chunks, source_name = process_file(
        str(file_path),
        chunk_size=chunk_size,
        overlap=overlap,
    )

    if not chunks:
        logger.warning(f"Файл '{file_path.name}' не дав жодного чанку, пропускаємо")
        return 0

    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    for i, chunk_text in enumerate(chunks):
        chunk_id = generate_chunk_id(source_name, i, chunk_text)

        # Пропускаємо, якщо такий чанк вже є в базі
        if vector_store.document_exists(chunk_id):
            continue

        documents.append(chunk_text)
        metadatas.append({
            "source": source_name,
            "file_name": file_path.name,
            "chunk_index": i,
            "total_chunks": len(chunks),
        })
        ids.append(chunk_id)

    if not documents:
        logger.info(f"'{file_path.name}' вже є в базі, пропускаємо")
        return 0

    vector_store.add_documents(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )
    logger.info(f"Додано {len(documents)} чанків із '{file_path.name}'")
    return len(documents)


def main():
    parser = argparse.ArgumentParser(description="Інгест книг у ChromaDB")
    parser.add_argument(
        "--books-path",
        default=settings.books_path,
        help="Шлях до директорії з книгами",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.chunk_size,
        help="Розмір чанку в символах",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=settings.chunk_overlap,
        help="Перекриття між чанками",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Очистити базу перед завантаженням",
    )
    args = parser.parse_args()

    logger.info("Ініціалізація векторного сховища...")
    vector_store = get_vector_store()

    if args.reset:
        logger.warning("Очищення бази даних...")
        vector_store.delete_collection()

    stats_before = vector_store.get_collection_stats()
    logger.info(f"Документів у базі до інгесту: {stats_before['total_documents']}")

    files = find_book_files(args.books_path)
    if not files:
        logger.warning(
            f"Файли не знайдено в '{args.books_path}'. "
            f"Підтримувані формати: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
        return

    total_chunks = 0
    for file_path in files:
        try:
            added = ingest_file(file_path, vector_store, args.chunk_size, args.overlap)
            total_chunks += added
        except Exception as e:
            logger.error(f"Помилка при обробці '{file_path.name}': {e}")

    stats_after = vector_store.get_collection_stats()
    logger.info(
        f"\n✅ Інгест завершено!\n"
        f"   Файлів оброблено: {len(files)}\n"
        f"   Нових чанків додано: {total_chunks}\n"
        f"   Всього в базі: {stats_after['total_documents']}"
    )


if __name__ == "__main__":
    main()
