"""
Модуль для роботи з векторною базою даних ChromaDB.
Забезпечує персистентне зберігання ембедингів та пошук за схожістю.
"""

import logging
import os
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from config.settings import settings
from rag.embeddings import get_embedding_function

logger = logging.getLogger(__name__)


class HerbalVectorStore:
    """
    Клас для роботи з векторним сховищем ChromaDB.
    Зберігає та індексує чанки текстів про лікарські рослини.
    """

    def __init__(
        self,
        db_path: str = None,
        collection_name: str = None,
    ):
        self.db_path = db_path or settings.chroma_db_path
        self.collection_name = collection_name or settings.collection_name

        # Переконуємось, що директорія існує
        os.makedirs(self.db_path, exist_ok=True)

        # Ініціалізуємо персистентний клієнт ChromaDB
        logger.info(f"Ініціалізація ChromaDB за шляхом: {self.db_path}")
        self._client = chromadb.PersistentClient(
            path=self.db_path,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Завантажуємо функцію ембедингів
        self._embedding_fn = get_embedding_function()

        # Завантажуємо або створюємо колекцію
        self._collection = self._get_or_create_collection()
        logger.info(
            f"Колекція '{self.collection_name}' готова. "
            f"Документів у базі: {self._collection.count()}"
        )

    def _get_or_create_collection(self):
        """Завантажує існуючу колекцію або створює нову."""
        try:
            collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._embedding_fn,
                metadata={
                    "description": "Колекція текстів про українські лікарські рослини",
                    "hnsw:space": "cosine",  # Використовуємо косинусну відстань
                },
            )
            return collection
        except Exception as e:
            logger.error(f"Помилка при роботі з колекцією: {e}")
            raise

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        """
        Додає документи до векторного сховища.

        Args:
            documents: Список текстових чанків
            metadatas: Список метаданих для кожного чанку
            ids: Унікальні ідентифікатори для кожного чанку
        """
        if not documents:
            logger.warning("Передано порожній список документів")
            return

        if len(documents) != len(metadatas) or len(documents) != len(ids):
            raise ValueError(
                "Розміри списків documents, metadatas та ids мають співпадати"
            )

        # Додаємо документи пакетами для уникнення проблем з пам'яттю
        batch_size = 100
        total_added = 0

        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]

            try:
                # upsert — оновить, якщо id вже існує
                self._collection.upsert(
                    documents=batch_docs,
                    metadatas=batch_meta,
                    ids=batch_ids,
                )
                total_added += len(batch_docs)
                logger.info(
                    f"Додано {total_added}/{len(documents)} чанків до ChromaDB..."
                )
            except Exception as e:
                logger.error(f"Помилка при додаванні чанків {i}-{i+batch_size}: {e}")
                raise

        logger.info(f"Успішно додано {total_added} чанків до колекції '{self.collection_name}'")

    def query(
        self,
        query_text: str,
        n_results: int = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Виконує пошук найближчих документів за запитом.

        Args:
            query_text: Текст запиту від користувача
            n_results: Кількість результатів (за замовчуванням з settings)
            where: Фільтр метаданих (опціонально)

        Returns:
            Словник з результатами: documents, metadatas, distances, ids
        """
        n_results = n_results or settings.top_k_results

        # Перевіряємо, чи є документи в базі
        total_docs = self._collection.count()
        if total_docs == 0:
            logger.warning("Векторна база порожня! Спочатку запустіть scripts/ingest.py")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

        # Обмежуємо n_results кількістю документів у базі
        n_results = min(n_results, total_docs)

        try:
            query_params = {
                "query_texts": [query_text],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_params["where"] = where

            results = self._collection.query(**query_params)
            return results

        except Exception as e:
            logger.error(f"Помилка при запиті до ChromaDB: {e}")
            raise

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Повертає статистику колекції.

        Returns:
            Словник зі статистикою: кількість документів, назва колекції тощо
        """
        count = self._collection.count()
        return {
            "collection_name": self.collection_name,
            "total_documents": count,
            "db_path": self.db_path,
            "embedding_model": settings.embedding_model,
        }

    def delete_collection(self) -> None:
        """Видаляє колекцію з бази даних (використовувати обережно!)."""
        logger.warning(f"Видалення колекції '{self.collection_name}'...")
        self._client.delete_collection(self.collection_name)
        # Відтворюємо порожню колекцію
        self._collection = self._get_or_create_collection()
        logger.info("Колекцію видалено та відтворено порожньою")

    def document_exists(self, doc_id: str) -> bool:
        """
        Перевіряє, чи існує документ з таким id.

        Args:
            doc_id: Ідентифікатор документа

        Returns:
            True, якщо документ існує
        """
        try:
            result = self._collection.get(ids=[doc_id])
            return len(result["ids"]) > 0
        except Exception:
            return False

    @property
    def collection(self):
        """Повертає об'єкт колекції ChromaDB."""
        return self._collection

    @property
    def client(self):
        """Повертає клієнт ChromaDB."""
        return self._client


# Глобальний екземпляр векторного сховища (ініціалізується при першому імпорті)
_vector_store: Optional[HerbalVectorStore] = None


def get_vector_store() -> HerbalVectorStore:
    """
    Повертає глобальний кешований екземпляр векторного сховища.
    Створює його при першому виклику.
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = HerbalVectorStore()
    return _vector_store
