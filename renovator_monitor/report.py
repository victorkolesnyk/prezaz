"""Вивантаження реєстру: CSV для Excel, HTML-сторінка, Markdown-дайджест."""

from __future__ import annotations

import csv
import html
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .registry import effective_status

STATUS_UK = {"relevant": "релевантна", "uncertain": "потребує перевірки", "irrelevant": "нерелевантна"}

CSV_COLUMNS = [
    ("id", "ID"), ("status", "Статус"), ("status_by", "Хто визначив"), ("score", "Оцінка"),
    ("published_at", "Опубліковано (UTC)"), ("first_seen_at", "Виявлено (UTC)"),
    ("source_name", "Видання/канал"), ("domain", "Домен"), ("language", "Мова"),
    ("title", "Заголовок"), ("url", "Посилання"), ("tone", "Тональність"),
    ("summary", "Суть (модель)"), ("context", "Контекст"), ("negative", "Негативні маркери"),
    ("found_via", "Знайдено через"), ("notes", "Примітки"),
]


def status_by(rec: dict) -> str:
    if rec.get("manual_status"):
        return "людина"
    if (rec.get("llm") or {}).get("verdict"):
        return "модель"
    return "правила"


def sort_key(rec: dict) -> tuple[str, str]:
    # ID як другий ключ: за однакових дат порядок не залежить від порядку вставки.
    return (rec.get("published_at") or rec.get("first_seen_at") or "", rec["id"])


def _csv_safe(value) -> str:
    """Захист від формульних ін'єкцій у Excel: =, +, -, @ на початку клітинки."""
    s = "" if value is None else str(value)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def row(rec: dict) -> dict:
    llm = rec.get("llm") or {}
    return {
        "id": rec["id"],
        "status": STATUS_UK[effective_status(rec)],
        "status_by": status_by(rec),
        "score": rec.get("score", ""),
        "published_at": rec.get("published_at") or "",
        "first_seen_at": rec.get("first_seen_at", ""),
        "source_name": rec.get("source_name", ""),
        "domain": rec.get("domain", ""),
        "language": rec.get("language") or "",
        "title": rec.get("title", ""),
        "url": rec.get("url", ""),
        "tone": llm.get("tone", ""),
        "summary": llm.get("summary_uk", ""),
        "context": ", ".join(rec.get("context", [])),
        "negative": ", ".join(rec.get("negative", [])),
        "found_via": "; ".join(rec.get("found_via", [])),
        "notes": rec.get("notes", ""),
    }


def write_csv(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM, щоб Excel розпізнав UTF-8
        w = csv.writer(f)
        w.writerow([label for _, label in CSV_COLUMNS])
        for rec in sorted(records, key=sort_key, reverse=True):
            r = row(rec)
            w.writerow([_csv_safe(r[k]) for k, _ in CSV_COLUMNS])


def _safe_href(url: str) -> str:
    return url if url.startswith(("https://", "http://")) else "#"


def write_html(records: list[dict], path: Path, generated_at: str) -> None:
    visible = [r for r in records if effective_status(r) != "irrelevant"]
    visible.sort(key=sort_key, reverse=True)
    counts = Counter(effective_status(r) for r in records)
    by_month = Counter((r.get("published_at") or r["first_seen_at"])[:7]
                       for r in records if effective_status(r) == "relevant")
    by_domain = Counter(r.get("domain") or "?" for r in records if effective_status(r) == "relevant")
    e = html.escape

    rows_html = []
    for rec in visible:
        st = effective_status(rec)
        llm = rec.get("llm") or {}
        rows_html.append(
            f'<tr class="{st}"><td>{e((rec.get("published_at") or rec["first_seen_at"])[:10])}</td>'
            f'<td><a href="{e(_safe_href(rec["url"]))}" rel="noopener noreferrer" target="_blank">'
            f'{e(rec.get("title") or rec["url"])}</a>'
            + (f'<div class="sum">{e(llm["summary_uk"])}</div>' if llm.get("summary_uk") else "")
            + (f'<div class="ex">{e(rec["page_excerpt"])}</div>' if rec.get("page_excerpt") else "")
            + f'</td><td>{e(rec.get("source_name") or rec.get("domain") or "")}</td>'
            f'<td>{e(rec.get("language") or "")}</td>'
            f'<td>{e(STATUS_UK[st])}<br><small>{e(status_by(rec))}, {rec.get("score", "")}</small></td>'
            f'<td><code>{e(rec["id"])}</code></td></tr>'
        )
    months = "".join(f"<li>{e(m)}: {n}</li>" for m, n in sorted(by_month.items(), reverse=True)[:12])
    top_domains = sorted(by_domain.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    domains = "".join(f"<li>{e(d)}: {n}</li>" for d, n in top_domains)

    page = f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Реєстр згадувань Реноватор</title>
<style>
:root {{ --bg:#fff; --fg:#1b1b1b; --muted:#666; --line:#ddd; --unc:#fff7e0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#e8e8e8; --muted:#9a9a9a; --line:#333; --unc:#2c2614; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1200px; padding:16px; }}
table {{ border-collapse:collapse; width:100%; }} td, th {{ border-bottom:1px solid var(--line); padding:6px; vertical-align:top; text-align:left; }}
tr.uncertain {{ background:var(--unc); }} .sum, .ex, small {{ color:var(--muted); font-size:13px; }}
a {{ color:inherit; }} .cols {{ display:flex; gap:32px; flex-wrap:wrap; }}
@media (max-width:700px) {{ td:nth-child(4), th:nth-child(4), td:nth-child(6), th:nth-child(6) {{ display:none; }} }}
</style></head><body>
<h1>Реєстр згадувань проєкту «Реноватор»</h1>
<p>Остання нова знахідка: {e(generated_at)} UTC. Записів усього: {len(records)}; релевантних: {counts["relevant"]};
на перевірку: {counts["uncertain"]}; відсіяно: {counts["irrelevant"]}.</p>
<div class="cols"><div><h2>Релевантні за місяцями</h2><ul>{months}</ul></div>
<div><h2>Найчастіші джерела</h2><ul>{domains}</ul></div></div>
<h2>Згадування (без відсіяних)</h2>
<table><thead><tr><th>Дата</th><th>Заголовок</th><th>Джерело</th><th>Мова</th><th>Статус</th><th>ID</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table>
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def digest_markdown(records: list[dict], days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = [r for r in records if r["first_seen_at"] >= since and effective_status(r) != "irrelevant"]
    fresh.sort(key=sort_key, reverse=True)
    rel = [r for r in fresh if effective_status(r) == "relevant"]
    unc = [r for r in fresh if effective_status(r) == "uncertain"]
    lines = [f"# Згадування «Реноватор» за {days} дн. (до {now:%Y-%m-%d})", "",
             f"Нових релевантних: {len(rel)}. На перевірку: {len(unc)}.", ""]
    for title, group in (("Релевантні", rel), ("Потребують перевірки", unc)):
        if not group:
            continue
        lines += [f"## {title}", ""]
        for r in group:
            date = (r.get("published_at") or r["first_seen_at"])[:10]
            src = r.get("source_name") or r.get("domain") or ""
            title = (r.get("title") or r["url"]).replace("[", "(").replace("]", ")")
            url = r["url"].replace(")", "%29").replace(" ", "%20")
            lines.append(f"- {date}, {src}: [{title}]({url}) `{r['id']}`")
        lines.append("")
    return "\n".join(lines)
