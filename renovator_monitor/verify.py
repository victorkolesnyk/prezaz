"""Перевірка сторінки: чи справді в статті є згадка, якої не видно в заголовку.

Для невизначених записів завантажуємо саму статтю і шукаємо термін у тексті.
Фрагмент навколо згадки зберігаємо як свідчення для людини і для оцінки.
"""

from __future__ import annotations

import re

from .fetch import HttpClient
from .registry import Registry, effective_status
from .relevance import CYR_WORD, LAT_WORD, detect_term
from .textutil import is_aggregator, strip_html, utcnow_iso


def excerpt(text: str, width: int = 220) -> str:
    m = CYR_WORD.search(text) or LAT_WORD.search(text)
    if not m:
        return ""
    start = max(0, m.start() - width)
    end = min(len(text), m.end() + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


MAX_ATTEMPTS = 3


def verify_pages(reg: Registry, client: HttpClient, limit: int, errors: list[str]) -> int:
    # Невизначені, а також «релевантні» без видимого терміна (лише за свідченням пошуку):
    # саме їх варто підтвердити текстом статті, перш ніж сповіщати.
    candidates = [
        r for r in reg.all()
        if not r.get("manual_status") and not r.get("page_checked_at")
        and (effective_status(r) == "uncertain"
             or (effective_status(r) == "relevant" and r.get("term") == "none"))
        and not is_aggregator(r["url"]) and r.get("domain") != "t.me"
        and r.get("page_check_attempts", 0) < MAX_ATTEMPTS
    ]
    candidates.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    done = 0
    for rec in candidates[:limit]:
        try:
            body = client.get(rec["url"], headers={"Accept": "text/html"}).text()
        except Exception as e:
            # Тимчасовий збій не ставить хрест на сторінці: повторимо наступним прогоном.
            rec["page_check_attempts"] = rec.get("page_check_attempts", 0) + 1
            errors.append(f"перевірка сторінки {rec['id']} (спроба {rec['page_check_attempts']}): {e}")
            continue
        text = strip_html(re.sub(r"(?is)<(header|footer|nav|aside)\b.*?</\1>", " ", body))
        rec["page_checked_at"] = utcnow_iso()
        rec["page_term"] = detect_term(text)
        rec["page_excerpt"] = excerpt(text)
        reg.rescore(rec)
        done += 1
    return done
