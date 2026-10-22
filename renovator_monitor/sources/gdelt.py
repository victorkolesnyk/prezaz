"""GDELT DOC 2.0 API: світовий індекс онлайн-новин, оновлення кожні 15 хвилин.

https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json
GDELT просить не частіше одного запиту на 5 секунд; інтервал задано в конфігурації HTTP.
За некоректного запиту API відповідає звичайним текстом, а не JSON.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import query_is_strong
from ..textutil import guess_language, parse_date

NAME = "gdelt"

_LANG = {
    "english": "en", "ukrainian": "uk", "latvian": "lv", "lithuanian": "lt",
    "norwegian": "no", "swedish": "sv", "polish": "pl", "german": "de", "french": "fr",
}


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    timespan = "3months" if ctx.get("backfill") else cfg.get("timespan", "1w")
    maxrecords = int(cfg.get("maxrecords", 250))
    out: list[RawMention] = []
    for query in cfg.get("queries", []):
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote(query)
               + f"&mode=artlist&format=json&sort=datedesc&maxrecords={maxrecords}"
               + f"&timespan={timespan}")
        try:
            resp = client.get(url)
            text = resp.text().strip()
            if not text:
                continue  # GDELT повертає порожнє тіло, коли збігів немає
            data = json.loads(text)
        except json.JSONDecodeError:
            ctx["errors"].append(f"{NAME} «{query}»: не JSON: {text[:160]}")
            continue
        except Exception as e:
            ctx["errors"].append(f"{NAME} «{query}»: {e}")
            continue
        for art in data.get("articles", []) or []:
            lang = _LANG.get(str(art.get("language", "")).lower())
            out.append(RawMention(
                url=art.get("url", ""),
                title=art.get("title", "") or "",
                source=NAME,
                query=query,
                source_name=art.get("domain", ""),
                domain=(art.get("domain") or "").lower().removeprefix("www."),
                published_at=parse_date(art.get("seendate")),
                language=guess_language(art.get("title", ""), lang),
                query_has_strong_term=query_is_strong(query),
                literal_search=True,
                extra={"sourcecountry": art.get("sourcecountry", "")},
            ))
    return out
