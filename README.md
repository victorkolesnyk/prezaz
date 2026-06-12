# 🌿 Жива Аптека

**Персональний фіто-помічник** на основі українських лікарських книг.  
Telegram-бот із RAG-архітектурою: ChromaDB + Sentence Transformers.

---

## Що це таке?

«Жива Аптека» — це Telegram-бот, який відповідає на запитання про лікарські рослини, народну медицину та фітотерапію. Бот шукає відповіді **семантично** — він розуміє сенс вашого запиту, а не просто збігається за ключовими словами.

Технологія **RAG (Retrieval-Augmented Generation)**:
1. Тексти з книг та посібників зберігаються у векторній базі ChromaDB
2. При запиті бот знаходить найближчі за змістом фрагменти
3. Формує структуровану відповідь з посиланням на джерела

---

## Структура проєкту

```
zhyva-apteka/
├── bot/                   # Telegram-бот (python-telegram-bot v20+)
│   ├── __init__.py
│   ├── main.py            # Точка входу, реєстрація обробників
│   ├── handlers.py        # Обробники команд та повідомлень
│   └── keyboards.py       # Інлайн-клавіатури
│
├── rag/                   # RAG-система
│   ├── __init__.py
│   ├── embeddings.py      # sentence-transformers (багатомовна модель)
│   ├── vectorstore.py     # Клієнт ChromaDB, add_documents, query
│   └── retriever.py       # Пошук релевантних фрагментів, формування відповіді
│
├── scripts/               # Службові скрипти
│   ├── __init__.py
│   ├── ingest.py          # Завантаження книг у векторну базу
│   └── process_text.py    # Очищення та розбиття тексту на чанки
│
├── config/                # Конфігурація
│   ├── __init__.py
│   └── settings.py        # Pydantic Settings, завантаження з .env
│
├── data/
│   ├── books/             # ← Сюди кладіть ваші .txt або .pdf книги
│   ├── chroma_db/         # Векторна база (генерується автоматично)
│   └── processed/         # Проміжні оброблені файли
│
├── .env.example           # Шаблон конфігурації
├── requirements.txt       # Python-залежності
├── Dockerfile             # Docker-образ (Python 3.11 slim)
└── docker-compose.yml     # Запуск бота та інгест-сервіс
```

---

## Швидкий старт

### Передумови

- Python 3.11+
- Токен Telegram-бота від [@BotFather](https://t.me/BotFather)

### 1. Клонуйте та налаштуйте середовище

```bash
git clone <repo-url>
cd zhyva-apteka

python -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

### 2. Налаштуйте змінні середовища

```bash
cp .env.example .env
```

Відкрийте `.env` та вкажіть обов'язкове значення:

```env
TELEGRAM_TOKEN=1234567890:AABBCCddEEFF...
```

Інші змінні мають розумні значення за замовчуванням.

### 3. Додайте книги

Покладіть файли `.txt` або `.pdf` з текстами про лікарські рослини до директорії `data/books/`.

```
data/books/
├── fitoterapiya_ukraine.txt
├── likarski_roslyny.pdf
└── narodni_recepti.txt
```

### 4. Завантажте тексти у векторну базу

```bash
python scripts/ingest.py
```

Опції:
```bash
python scripts/ingest.py --reset              # Очистити базу і завантажити заново
python scripts/ingest.py --chunk-size 1024    # Змінити розмір чанку
python scripts/ingest.py --books-path /path   # Вказати інший шлях до книг
```

### 5. Запустіть бота

```bash
python bot/main.py
```

---

## Запуск через Docker

```bash
# Збудуйте образ та запустіть бота
docker-compose up -d

# Завантажте дані у базу (одноразово)
docker-compose run --rm ingest

# Перегляд логів
docker-compose logs -f zhyva-apteka-bot
```

---

## Команди бота

| Команда   | Опис                          |
|-----------|-------------------------------|
| `/start`  | Головне меню та привітання    |
| `/help`   | Довідка з прикладами запитів  |
| `/stats`  | Статистика векторної бази     |

---

## Приклади запитів

Бот розуміє природну українську мову:

- *Ромашка при застуді*
- *Як заварити звіробій*
- *Трави від безсоння*
- *Валеріана протипоказання*
- *Лікування болю в шлунку народними засобами*
- *Властивості меліси*
- *Рецепт відвару від кашлю*

---

## Технічні деталі

| Компонент           | Рішення                                      |
|---------------------|----------------------------------------------|
| Telegram бот        | python-telegram-bot v20+ (asyncio)           |
| Векторна база       | ChromaDB (персистентний клієнт)              |
| Модель ембедингів   | `paraphrase-multilingual-mpnet-base-v2`      |
| Метрика схожості    | Косинусна відстань (HNSW index)              |
| Мова                | Підтримка української та слов'янських мов    |
| Конфігурація        | pydantic-settings + .env                     |

---

## Конфігурація (.env)

| Змінна                | Опис                                      | Значення за замовч.               |
|-----------------------|-------------------------------------------|-----------------------------------|
| `TELEGRAM_TOKEN`      | Токен бота від @BotFather                 | *обов'язково*                     |
| `CHROMA_DB_PATH`      | Шлях до ChromaDB                          | `data/chroma_db`                  |
| `COLLECTION_NAME`     | Назва колекції                            | `herbal_medicine_ua`              |
| `BOOKS_PATH`          | Шлях до книг                              | `data/books`                      |
| `EMBEDDING_MODEL`     | Модель sentence-transformers              | `paraphrase-multilingual-mpnet-base-v2` |
| `CHUNK_SIZE`          | Розмір чанку (символів)                   | `512`                             |
| `CHUNK_OVERLAP`       | Перекриття між чанками                    | `64`                              |
| `TOP_K_RESULTS`       | К-сть результатів із ChromaDB             | `5`                               |
| `SIMILARITY_THRESHOLD`| Мінімальний поріг схожості (0.0–1.0)      | `0.3`                             |

---

> ⚠️ **Застереження:** Інформація, яку надає бот, має виключно довідковий та освітній характер. Бот не замінює консультацію лікаря. Перед застосуванням лікарських рослин обов'язково проконсультуйтеся з кваліфікованим медичним спеціалістом.
