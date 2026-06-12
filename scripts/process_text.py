"""
Попередня обробка тексту: очищення та розбиття на чанки з перекриттям.
"""

import re
import os
import logging
from typing import List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Очищує текст від зайвих символів."""
    # Видаляємо управляючі символи крім переносів рядка
    text = re.sub(r"[^\S\n]+", " ", text)
    # Більше двох переносів підряд → два
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Прибираємо пробіли на початку/кінці рядків
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()


def split_into_chunks(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[str]:
    """
    Розбиває текст на чанки за розміром з перекриттям.
    Намагається не розривати речення.
    """
    if not text:
        return []

    # Розбиваємо на речення (крапка/знак оклику/питання + пробіл або перенос)
    sentence_endings = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_endings.split(text)

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_len = len(sentence)

        # Якщо одне речення перевищує chunk_size — ділимо по символах
        if sentence_len > chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            for i in range(0, sentence_len, chunk_size - overlap):
                chunks.append(sentence[i : i + chunk_size])
            continue

        if current_len + sentence_len + 1 > chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            # Перекриття: залишаємо останні речення
            overlap_text = " ".join(current_chunk)
            if len(overlap_text) > overlap:
                overlap_text = overlap_text[-overlap:]
            current_chunk = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)

        current_chunk.append(sentence)
        current_len += sentence_len + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return [c for c in chunks if len(c.strip()) > 20]


def read_text_file(file_path: str) -> str:
    """Читає текстовий файл з автовизначенням кодування."""
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    logger.warning(f"Не вдалося прочитати {file_path} з жодним кодуванням")
    return ""


def read_pdf_file(file_path: str) -> str:
    """Читає текст з PDF-файлу за допомогою PyPDF2."""
    try:
        import PyPDF2

        text_parts = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        logger.error("PyPDF2 не встановлено. Встановіть: pip install PyPDF2")
        return ""
    except Exception as e:
        logger.error(f"Помилка читання PDF {file_path}: {e}")
        return ""


def process_file(
    file_path: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> Tuple[List[str], str]:
    """
    Читає файл, очищує та розбиває на чанки.

    Returns:
        (chunks, source_name)
    """
    path = Path(file_path)
    source_name = path.stem  # Ім'я файлу без розширення

    if path.suffix.lower() == ".pdf":
        raw_text = read_pdf_file(file_path)
    else:
        raw_text = read_text_file(file_path)

    if not raw_text:
        logger.warning(f"Порожній файл: {file_path}")
        return [], source_name

    clean = clean_text(raw_text)
    chunks = split_into_chunks(clean, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Файл '{source_name}': {len(chunks)} чанків")
    return chunks, source_name
