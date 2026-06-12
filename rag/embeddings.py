"""
Модуль для роботи з ембедингами (векторними представленнями тексту).
Використовує sentence-transformers з багатомовною моделлю,
що підтримує українську мову.
"""

import logging
from typing import List
from functools import lru_cache

from sentence_transformers import SentenceTransformer
import chromadb.utils.embedding_functions as embedding_functions

from config.settings import settings

logger = logging.getLogger(__name__)


class UkrainianEmbeddingFunction(embedding_functions.EmbeddingFunction):
    """
    Власна функція ембедингів на базі sentence-transformers.
    Підтримує українську та інші слов'янські мови.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.embedding_model
        logger.info(f"Завантаження моделі ембедингів: {self.model_name}")
        self._model = SentenceTransformer(self.model_name)
        logger.info("Модель ембедингів успішно завантажена")

    def __call__(self, input: List[str]) -> List[List[float]]:
        """
        Генерує ембединги для списку текстів.

        Args:
            input: Список рядків для векторизації

        Returns:
            Список векторів (кожен вектор — список чисел float)
        """
        if not input:
            return []

        # Кодуємо тексти у вектори
        embeddings = self._model.encode(
            input,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,  # L2-нормалізація для кращої косинусної схожості
        )
        return embeddings.tolist()

    @property
    def model(self) -> SentenceTransformer:
        """Повертає завантажену модель."""
        return self._model

    def embed_query(self, text: str) -> List[float]:
        """
        Генерує ембединг для одного запиту.

        Args:
            text: Текст запиту

        Returns:
            Вектор ембедингу
        """
        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embedding.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Генерує ембединги для списку документів.

        Args:
            texts: Список текстів

        Returns:
            Список векторів
        """
        return self(texts)


@lru_cache(maxsize=1)
def get_embedding_function(model_name: str = None) -> UkrainianEmbeddingFunction:
    """
    Повертає кешований екземпляр функції ембедингів.
    Модель завантажується лише один раз.

    Args:
        model_name: Назва моделі (опціонально, за замовчуванням з settings)

    Returns:
        Екземпляр UkrainianEmbeddingFunction
    """
    effective_model = model_name or settings.embedding_model
    return UkrainianEmbeddingFunction(model_name=effective_model)
