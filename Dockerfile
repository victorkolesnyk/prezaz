FROM python:3.11-slim

# Метадані образу
LABEL maintainer="Жива Аптека" \
      description="Ukrainian Herbal Medicine Telegram Bot with RAG + ChromaDB"

WORKDIR /app

# Встановлюємо системні залежності для sentence-transformers та chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо та встановлюємо Python-залежності (окремим шаром для кешування)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копіюємо вихідний код
COPY . .

# Створюємо директорії для даних (у випадку якщо volumes не примонтовано)
RUN mkdir -p data/books data/chroma_db data/processed

# Не запускаємо від root
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Перевірка здоров'я — чи запущено Python-процес
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Точка входу
CMD ["python", "bot/main.py"]
