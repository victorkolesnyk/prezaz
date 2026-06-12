# Data Directory

## Structure

```
data/
├── books/        # Place your PDF/TXT book files here
├── chroma_db/    # ChromaDB vector index (auto-generated, gitignored)
└── processed/    # Intermediate processed files (gitignored)
```

## Books

Place your Ukrainian herbal medicine books in `data/books/`:

- Кархут — "Ліки навколо нас"
- Носаль — "Лікарські рослини і способи їх застосування в народі"
- Довідник з фітотерапії
- Дари лісу

Supported formats: **PDF**, **TXT**

## Building the Index

After placing books in `data/books/`, run:

```bash
python knowledge_base/build_index.py
```

Or with custom paths:

```bash
python knowledge_base/build_index.py --books-dir data/books --db-dir data/chroma_db
```

## Notes

- `data/books/` and `data/chroma_db/` are gitignored — add your own files locally
- The index is built once and reused by the bot
- Re-run `build_index.py` after adding new books to update the index
