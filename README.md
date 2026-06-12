# 🌿 Жива Аптека

Персональний фіто-помічник на основі українських лікарських книг.  
Telegram-бот із RAG-архітектурою: ChromaDB + sentence-transformers.

## Як це працює

1. Тексти українських лікарських книг завантажуються у ChromaDB через скрипт `scripts/ingest.py`
2. При запиті користувача бот шукає найрелевантніші фрагменти за векторною схожістю
3. Відповідь формується з найбільш релевантних уривків із зазначенням джерел

## Структура проекту

```
zhyva-apteka/
├── bot/                  # Telegram-бот
│   ├── main.py           # Точка входу
│   ├── handlers.py       # Обробники повідомлень
│   └── keyboards.py      # Інлайн-клавіатури
├── rag/                  # RAG-система
│   ├── vectorstore.py    # ChromaDB клієнт
│   ├── embeddings.py     # sentence-transformers
│   └── retriever.py      # Пошук та формування відповіді
├── scripts/
│   ├── ingest.py         # Завантаження книг у базу
│   └── process_text.py   # Обробка та чанкування тексту
├── config/
│   └── settings.py       # Налаштування через .env
├── data/
│   ├── books/            # Сюди кладіть книги (.txt, .pdf)
│   ├── chroma_db/        # Векторна база (генерується автоматично)
│   └── processed/        # Проміжні файли
├── .env.example
├── requirements.txt
└── docker-compose.yml
```

## Швидкий старт

### 1. Клонуйте репозиторій та налаштуйте середовище

```bash
git clone <repo-url>
cd zhyva-apteka
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Налаштуйте змінні середовища

```bash
cp .env.example .env
# Відредагуйте .env — вкажіть TELEGRAM_TOKEN
```

### 3. Додайте книги та завантажте у базу

```bash
# Покладіть .txt або .pdf файли у data/books/
python scripts/ingest.py
```

### 4. Запустіть бота

```bash
python bot/main.py
```

### Docker

```bash
docker-compose up -d
```

## Команди бота

| Команда | Опис |
|---------|------|
| `/start` | Головне меню |
| `/help` | Довідка |
| `/stats` | Статистика бази знань |

## Приклади запитів

- _Ромашка при застуді_
- _Як заварити звіробій_
- _Трави від безсоння_
- _Валеріана протипоказання_
- _Лікування шлунку народними засобами_

---

> ⚠️ Інформація носить довідковий характер. Перед застосуванням лікарських рослин проконсультуйтеся з лікарем.
