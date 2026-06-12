# 🌿 Жива Аптека

**Персональний фіто-помічник** на основі українських лікарських книг.  
Telegram-бот із RAG-архітектурою: ChromaDB + Claude API (Anthropic).

---

## Що це таке?

«Жива Аптека» — це Telegram-бот, який відповідає на запитання про лікарські рослини, народну медицину та фітотерапію. Бот розуміє природну українську мову, а відповіді генерує **Claude** (Anthropic) на основі реального тексту з українських лікарських книг.

Технологія **RAG (Retrieval-Augmented Generation)**:
1. Тексти з книг зберігаються у векторній базі ChromaDB
2. При запиті бот знаходить найближчі за змістом фрагменти
3. Claude отримує ці фрагменти як контекст і формулює грамотну відповідь
4. Підтримує фото рослин — Claude визначає рослину та надає фітотерапевтичну інформацію

---

## Структура проєкту

```
zhyva-apteka/
├── bot/                        # Telegram-бот (python-telegram-bot v20+)
│   ├── bot.py                  # Головний бот: Claude API + RAG
│   ├── requirements.txt        # Залежності для bot/
│   ├── Procfile                # Railway/Heroku: web: python bot.py
│   ├── main.py                 # Альтернативна точка входу (без Claude)
│   ├── handlers.py             # Обробники (legacy)
│   └── keyboards.py            # Інлайн-клавіатури
│
├── knowledge_base/             # Інтерфейс до векторної бази
│   ├── build_index.py          # PDF/TXT → ChromaDB (побудова індексу)
│   └── search.py               # Семантичний пошук по колекції
│
├── rag/                        # RAG-система (низькорівнева)
│   ├── embeddings.py           # sentence-transformers
│   ├── vectorstore.py          # Клієнт ChromaDB
│   └── retriever.py            # Пошук фрагментів
│
├── scripts/                    # Службові скрипти
│   ├── ingest.py               # Завантаження книг у ChromaDB
│   └── process_text.py         # Очищення та чанкування тексту
│
├── config/
│   └── settings.py             # Pydantic Settings (.env)
│
├── data/
│   ├── books/                  # ← Сюди кладіть .pdf або .txt книги
│   ├── chroma_db/              # Векторна база (генерується автоматично)
│   └── README.md               # Інструкції по даним
│
├── .env.example                # Шаблон конфігурації
├── requirements.txt            # Python-залежності (повний список)
├── Dockerfile
└── docker-compose.yml
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

Відкрийте `.env` та вкажіть обов'язкові значення:

```env
TELEGRAM_TOKEN=1234567890:AABBCCddEEFF...
ANTHROPIC_API_KEY=sk-ant-...
```

Решта змінних мають розумні значення за замовчуванням.

### 3. Додайте книги

Покладіть файли `.txt` або `.pdf` з текстами про лікарські рослини до директорії `data/books/`.

```
data/books/
├── fitoterapiya_ukraine.txt
├── likarski_roslyny.pdf
└── narodni_recepti.txt
```

### 4. Побудуйте векторний індекс

```bash
python knowledge_base/build_index.py
```

Опції:
```bash
python knowledge_base/build_index.py --books-dir data/books --db-dir data/chroma_db
```

Або через legacy-скрипт:
```bash
python scripts/ingest.py --reset
```

### 5. Запустіть бота

```bash
python bot/bot.py
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
| LLM генерація       | Claude `claude-opus-4-8` (Anthropic)         |
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
| `ANTHROPIC_API_KEY`   | API ключ Anthropic (claude.ai/console)    | *обов'язково*                     |
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
