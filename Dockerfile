FROM python:3.11-slim

WORKDIR /app

# Встановлюємо системні залежності для sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Створюємо директорії для даних
RUN mkdir -p data/books data/chroma_db data/processed

CMD ["python", "bot/main.py"]
