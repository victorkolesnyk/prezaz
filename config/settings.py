"""
Налаштування проєкту "Жива Аптека".
Всі змінні завантажуються з файлу .env через pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class Settings(BaseSettings):
    """Головний клас налаштувань бота."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    telegram_token: str = Field(
        ...,
        description="Токен Telegram-бота від @BotFather",
    )

    # ChromaDB
    chroma_db_path: str = Field(
        default="data/chroma_db",
        description="Шлях до директорії з базою ChromaDB",
    )
    collection_name: str = Field(
        default="herbal_medicine_ua",
        description="Назва колекції в ChromaDB",
    )

    # Шляхи до даних
    books_path: str = Field(
        default="data/books",
        description="Шлях до директорії з книгами та текстовими файлами",
    )
    processed_path: str = Field(
        default="data/processed",
        description="Шлях до директорії з обробленими файлами",
    )

    # Модель ембедингів
    embedding_model: str = Field(
        default="paraphrase-multilingual-mpnet-base-v2",
        description="Назва моделі sentence-transformers для ембедингів",
    )

    # Параметри чанкування тексту
    chunk_size: int = Field(
        default=512,
        description="Розмір одного текстового чанку (в символах)",
    )
    chunk_overlap: int = Field(
        default=64,
        description="Розмір перекриття між чанками (в символах)",
    )

    # RAG параметри
    top_k_results: int = Field(
        default=5,
        description="Кількість найближчих результатів для повернення з ChromaDB",
    )
    similarity_threshold: float = Field(
        default=0.3,
        description="Мінімальний поріг схожості для відповідей (0.0 - 1.0)",
    )

    # Загальні налаштування бота
    bot_name: str = Field(
        default="Жива Аптека",
        description="Назва бота",
    )
    max_message_length: int = Field(
        default=4096,
        description="Максимальна довжина повідомлення Telegram",
    )


# Глобальний екземпляр налаштувань
settings = Settings()
