"""
Модуль RAG-ретривера для "Живої Аптеки".
Отримує запит користувача, шукає релевантні чанки в ChromaDB
та формує структуровану відповідь.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from config.settings import settings
from rag.vectorstore import get_vector_store

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """Один знайдений текстовий фрагмент із метаданими."""
    text: str
    source: str
    chunk_index: int
    distance: float
    similarity: float  # 1 - distance (для косинусної відстані)

    @classmethod
    def from_chromadb_result(
        cls,
        text: str,
        metadata: Dict[str, Any],
        distance: float,
    ) -> "RetrievedChunk":
        return cls(
            text=text,
            source=metadata.get("source", "невідомо"),
            chunk_index=metadata.get("chunk_index", 0),
            distance=distance,
            similarity=max(0.0, 1.0 - distance),
        )


@dataclass
class RAGResponse:
    """Структурована відповідь від RAG-системи."""
    query: str
    answer: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    has_relevant_results: bool = False
    sources: List[str] = field(default_factory=list)

    def format_for_telegram(self, max_length: int = 4096) -> str:
        """
        Форматує відповідь для відправки в Telegram.

        Args:
            max_length: Максимальна довжина повідомлення

        Returns:
            Відформатований рядок
        """
        if not self.has_relevant_results:
            return self.answer

        # Формуємо повідомлення з текстом та джерелами
        message_parts = [self.answer]

        if self.sources:
            unique_sources = list(dict.fromkeys(self.sources))  # Зберігаємо порядок
            sources_text = "\n".join(f"  • {src}" for src in unique_sources[:3])
            message_parts.append(f"\n\n📚 *Джерела:*\n{sources_text}")

        full_message = "\n".join(message_parts)

        # Обрізаємо, якщо перевищує ліміт Telegram
        if len(full_message) > max_length:
            truncation_notice = "\n\n_...відповідь скорочено_"
            cut_at = max_length - len(truncation_notice)
            full_message = full_message[:cut_at] + truncation_notice

        return full_message


class HerbalRetriever:
    """
    RAG-ретривер для пошуку інформації про лікарські рослини.
    Використовує ChromaDB для пошуку релевантних фрагментів тексту.
    """

    # Шаблони відповідей
    NO_RESULTS_TEMPLATE = (
        "На жаль, я не знайшов інформації за вашим запитом у базі знань. "
        "Спробуйте переформулювати питання або уточніть назву рослини чи захворювання.\n\n"
        "Наприклад:\n"
        "• _Ромашка від болю в животі_\n"
        "• _Лікування застуди травами_\n"
        "• _Які трави допомагають при безсонні_"
    )

    LOW_CONFIDENCE_TEMPLATE = (
        "Я знайшов деяку інформацію, але вона може бути не зовсім точною "
        "для вашого запиту. Ось що вдалося знайти:\n\n{answer}\n\n"
        "⚠️ _Рекомендую проконсультуватися з фахівцем перед застосуванням._"
    )

    ANSWER_TEMPLATE = (
        "🌿 *Інформація з бази знань:*\n\n"
        "{answer}\n\n"
        "⚠️ _Ця інформація носить довідковий характер. "
        "Перед застосуванням лікарських рослин проконсультуйтеся з лікарем._"
    )

    def __init__(
        self,
        top_k: int = None,
        similarity_threshold: float = None,
    ):
        self.top_k = top_k or settings.top_k_results
        self.similarity_threshold = similarity_threshold or settings.similarity_threshold
        self._vector_store = get_vector_store()

    def retrieve(self, query: str) -> RAGResponse:
        """
        Основний метод ретривера. Приймає запит і повертає RAGResponse.

        Args:
            query: Запит користувача (природна мова, переважно українська)

        Returns:
            RAGResponse з відповіддю та метаданими
        """
        logger.info(f"Запит до RAG: '{query[:100]}...'")

        # Перевіряємо стан бази
        stats = self._vector_store.get_collection_stats()
        if stats["total_documents"] == 0:
            logger.warning("База знань порожня")
            return RAGResponse(
                query=query,
                answer=(
                    "⚠️ База знань порожня. Адміністратор ще не завантажив дані.\n"
                    "Будь ласка, зв'яжіться з підтримкою або спробуйте пізніше."
                ),
                has_relevant_results=False,
            )

        # Виконуємо пошук в ChromaDB
        try:
            raw_results = self._vector_store.query(
                query_text=query,
                n_results=self.top_k,
            )
        except Exception as e:
            logger.error(f"Помилка при запиті до ChromaDB: {e}")
            return RAGResponse(
                query=query,
                answer="Виникла технічна помилка при пошуку. Спробуйте ще раз.",
                has_relevant_results=False,
            )

        # Парсимо результати
        chunks = self._parse_results(raw_results)

        if not chunks:
            return RAGResponse(
                query=query,
                answer=self.NO_RESULTS_TEMPLATE,
                has_relevant_results=False,
            )

        # Фільтруємо за порогом схожості
        relevant_chunks = [
            c for c in chunks if c.similarity >= self.similarity_threshold
        ]

        if not relevant_chunks:
            logger.info(
                f"Знайдено {len(chunks)} чанків, але жоден не пройшов поріг "
                f"схожості {self.similarity_threshold}. "
                f"Найкраща схожість: {chunks[0].similarity:.3f}"
            )
            return RAGResponse(
                query=query,
                answer=self.NO_RESULTS_TEMPLATE,
                has_relevant_results=False,
                chunks=chunks,
            )

        # Формуємо відповідь
        answer = self._synthesize_answer(query, relevant_chunks)
        sources = list(dict.fromkeys(c.source for c in relevant_chunks))

        logger.info(
            f"Знайдено {len(relevant_chunks)} релевантних чанків. "
            f"Джерела: {sources}"
        )

        return RAGResponse(
            query=query,
            answer=answer,
            chunks=relevant_chunks,
            has_relevant_results=True,
            sources=sources,
        )

    def _parse_results(
        self,
        raw_results: Dict[str, Any],
    ) -> List[RetrievedChunk]:
        """
        Перетворює сирі результати ChromaDB на список RetrievedChunk.

        Args:
            raw_results: Результати з chromadb collection.query()

        Returns:
            Список RetrievedChunk, відсортований за спаданням схожості
        """
        chunks = []

        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        for text, metadata, distance in zip(documents, metadatas, distances):
            if text and text.strip():
                chunk = RetrievedChunk.from_chromadb_result(
                    text=text,
                    metadata=metadata or {},
                    distance=distance,
                )
                chunks.append(chunk)

        # Сортуємо за спаданням схожості
        chunks.sort(key=lambda c: c.similarity, reverse=True)
        return chunks

    def _synthesize_answer(
        self,
        query: str,
        chunks: List[RetrievedChunk],
    ) -> str:
        """
        Синтезує відповідь із знайдених чанків.

        Оскільки ми не використовуємо LLM для генерації, формуємо
        відповідь безпосередньо зі знайдених фрагментів тексту.

        Args:
            query: Оригінальний запит
            chunks: Відфільтровані релевантні чанки

        Returns:
            Готовий текст відповіді
        """
        # Беремо найбільш релевантні унікальні фрагменти
        seen_texts = set()
        unique_chunks = []

        for chunk in chunks:
            # Дедублікація: перевіряємо, чи не є цей текст підрядком вже доданого
            normalized = chunk.text.strip().lower()
            if not any(
                normalized in seen or seen in normalized
                for seen in seen_texts
            ):
                seen_texts.add(normalized)
                unique_chunks.append(chunk)

        if not unique_chunks:
            return self.NO_RESULTS_TEMPLATE

        # Будуємо основний текст відповіді
        answer_parts = []
        for i, chunk in enumerate(unique_chunks[:3], 1):  # Беремо топ-3 чанки
            text = chunk.text.strip()
            # Додаємо роздільник між фрагментами, якщо їх декілька
            if len(unique_chunks) > 1:
                answer_parts.append(f"*{i}.* {text}")
            else:
                answer_parts.append(text)

        combined_answer = "\n\n".join(answer_parts)

        # Формуємо фінальне повідомлення за шаблоном
        avg_similarity = sum(c.similarity for c in unique_chunks) / len(unique_chunks)

        if avg_similarity < 0.5:
            return self.LOW_CONFIDENCE_TEMPLATE.format(answer=combined_answer)
        else:
            return self.ANSWER_TEMPLATE.format(answer=combined_answer)

    def get_stats(self) -> Dict[str, Any]:
        """Повертає статистику ретривера та векторної бази."""
        store_stats = self._vector_store.get_collection_stats()
        return {
            **store_stats,
            "top_k": self.top_k,
            "similarity_threshold": self.similarity_threshold,
        }


# Глобальний екземпляр ретривера
_retriever: Optional[HerbalRetriever] = None


def get_retriever() -> HerbalRetriever:
    """
    Повертає глобальний кешований екземпляр ретривера.
    Створює його при першому виклику.
    """
    global _retriever
    if _retriever is None:
        _retriever = HerbalRetriever()
    return _retriever
