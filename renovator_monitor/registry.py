"""Реєстр згадувань у файлі JSON Lines.

Чому JSONL, а не база даних: обсяг для одного проєкту становить сотні або
тисячі записів, файл читається людиною, кожна зміна видна в git diff, а git
стає журналом аудиту реєстру.

Запис ніколи не видаляється автоматично. Нерелевантні знахідки лишаються зі
статусом irrelevant, щоб при наступному прогоні їх не показувати як нові.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .models import RawMention
from .relevance import score_text
from .textutil import (canonical_url, domain_of, is_aggregator, short_hash,
                       strip_tracking, title_key, utcnow_iso)

STATUSES = ("relevant", "uncertain", "irrelevant")


def effective_status(rec: dict) -> str:
    """Ручне рішення переважує модель, модель переважує правила."""
    if rec.get("manual_status"):
        return rec["manual_status"]
    llm = rec.get("llm") or {}
    if llm.get("verdict") in STATUSES:
        return llm["verdict"]
    return rec.get("auto_status", "uncertain")


class Registry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: dict[str, dict] = {}
        self._by_url: dict[str, str] = {}
        self._by_title: dict[tuple[str, str], str] = {}
        if self.path.exists():
            self._load()

    # ---------- завантаження і збереження ----------

    def _load(self) -> None:
        with self.path.open(encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{self.path}:{n}: пошкоджений рядок реєстру: {e}") from e
                self._index(rec)

    def _index(self, rec: dict) -> None:
        self.records[rec["id"]] = rec
        for u in [rec.get("url", "")] + rec.get("alt_urls", []):
            if u:
                self._by_url[canonical_url(u)] = rec["id"]
        if rec.get("title_key") and rec.get("domain"):
            self._by_title[(rec["domain"], rec["title_key"])] = rec["id"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(self.records.values(), key=lambda r: (r["first_seen_at"], r["id"]))
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".registry-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)  # mkstemp створює 0600, а реєстр читають інші процеси
            os.replace(tmp, self.path)  # атомарна заміна: файл не буває напівзаписаним
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---------- злиття знахідок ----------

    def find(self, m: RawMention) -> dict | None:
        rid = self._by_url.get(canonical_url(m.url))
        if rid:
            return self.records[rid]
        domain = m.domain or ("" if is_aggregator(m.url) else domain_of(m.url))
        tk = title_key(m.title, m.source_name)
        # У Telegram «заголовок» є першим рядком допису: «Головне за день» у різних
        # дописах однаковий, тому дописи зливаємо лише за URL.
        if domain and tk and domain != "t.me":
            rid = self._by_title.get((domain, tk))
            if rid and _close_dates(self.records[rid].get("published_at"), m.published_at):
                return self.records[rid]
        return None

    def upsert(self, m: RawMention, now: str | None = None) -> tuple[dict, bool]:
        """Додає або оновлює запис. Повертає (запис, чи_новий)."""
        now = now or utcnow_iso()
        if not is_aggregator(m.url):
            m.url = strip_tracking(m.url)
        domain = m.domain or ("" if is_aggregator(m.url) else domain_of(m.url))
        tk = title_key(m.title, m.source_name)
        via = f"{m.source}: {m.query}"
        rec = self.find(m)
        is_new = rec is None
        if is_new:
            rid = short_hash(domain or domain_of(m.url), tk or canonical_url(m.url))
            while rid in self.records:  # надзвичайно малоймовірна колізія
                rid = short_hash(rid, m.url)
            rec = {
                "id": rid,
                "url": m.url,
                "alt_urls": [],
                "title": m.title,
                "title_key": tk,
                "snippet": m.snippet,
                "source_name": m.source_name,
                "domain": domain,
                "language": m.language,
                "published_at": m.published_at,
                "first_seen_at": now,
                # Лише дата: інакше кожен прогін змінював би файл і плодив коміти.
                "last_seen_at": now[:10],
                "found_via": [via],
                "query_strong": m.query_has_strong_term,
                "query_strong_literal": m.query_has_strong_term and m.literal_search,
                "manual_status": None,
                "notes": "",
                "llm": None,
                "notified": False,
            }
        else:
            rec["last_seen_at"] = now[:10]
            if via not in rec["found_via"]:
                rec["found_via"].append(via)
            # Пряме посилання на видання краще за посилання агрегатора.
            if m.url and canonical_url(m.url) != canonical_url(rec["url"]):
                if is_aggregator(rec["url"]) and not is_aggregator(m.url):
                    rec["alt_urls"].append(rec["url"])
                    rec["url"] = m.url
                elif canonical_url(m.url) not in {canonical_url(u) for u in rec["alt_urls"]}:
                    rec["alt_urls"].append(m.url)
            if len(m.snippet) > len(rec.get("snippet") or ""):
                rec["snippet"] = m.snippet
            for key in ("published_at", "language", "source_name"):
                if not rec.get(key) and getattr(m, key):
                    rec[key] = getattr(m, key)
            if not rec.get("domain") and domain:
                rec["domain"] = domain
            if not rec.get("title_key") and tk:
                rec["title_key"] = tk
            rec["query_strong"] = rec.get("query_strong") or m.query_has_strong_term
            rec["query_strong_literal"] = (rec.get("query_strong_literal")
                                           or (m.query_has_strong_term and m.literal_search))
        self.rescore(rec)
        self._index(rec)
        return rec, is_new

    def rescore(self, rec: dict) -> None:
        text = " ".join(filter(None, [rec.get("title"), rec.get("snippet"), rec.get("page_excerpt")]))
        s = score_text(text, query_strong=bool(rec.get("query_strong")),
                       query_literal=bool(rec.get("query_strong_literal")),
                       page_term=rec.get("page_term"), domain=rec.get("domain") or "")
        rec["score"] = s.score
        rec["auto_status"] = s.status
        rec["term"] = s.term
        rec["context"] = s.context
        rec["negative"] = s.negative

    # ---------- ручна робота з реєстром ----------

    def set_manual(self, rid: str, status: str | None, note: str | None = None) -> dict:
        rec = self._resolve(rid)
        if status is not None and status not in STATUSES:
            raise ValueError(f"статус має бути одним із {STATUSES}")
        rec["manual_status"] = status
        if status is not None:
            rec["notified"] = True  # людина вже бачила запис, сповіщати про нього зайве
        if note is not None:
            rec["notes"] = note
        return rec

    def _resolve(self, rid: str) -> dict:
        if rid in self.records:
            return self.records[rid]
        matches = [k for k in self.records if k.startswith(rid)]
        if len(matches) == 1:
            return self.records[matches[0]]
        raise KeyError(f"запис «{rid}» не знайдено" if not matches else f"префікс «{rid}» неоднозначний")

    def all(self) -> list[dict]:
        return list(self.records.values())


def _close_dates(a: str | None, b: str | None, days: int = 3) -> bool:
    """Однаковий заголовок на тому ж сайті з різницею в місяці є іншою статтею (напр. «Підсумки тижня»)."""
    if not a or not b:
        return True
    try:
        da = datetime.fromisoformat(a.replace("Z", "+00:00"))
        db = datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return True
    return abs((da - db).total_seconds()) <= days * 86400


@contextmanager
def locked(path: str | Path):
    """Не дає двом прогонам одночасно переписувати реєстр."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = lock_path.open("w")
    try:
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:  # Windows: блокування пропускаємо
            pass
        except BlockingIOError as e:
            raise RuntimeError("інший прогін уже працює з реєстром") from e
        yield
    finally:
        f.close()
