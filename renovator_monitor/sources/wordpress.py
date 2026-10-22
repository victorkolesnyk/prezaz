"""Пошукова RSS-стрічка сайтів на WordPress: https://site/?s=<запит>&feed=rss2

Це дає повнотекстовий пошук по конкретному виданню без API-ключів.
Чи працює стрічка на конкретному сайті, перевіряє команда `doctor`.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import query_is_strong
from ..textutil import domain_of, guess_language, strip_html
from .rss import parse_feed

NAME = "wordpress"


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    out: list[RawMention] = []
    for site in cfg.get("sites", []):
        base = site["url"].rstrip("/")
        for query in site.get("queries", cfg.get("queries", [])):
            url = f"{base}/?s={quote_plus(query)}&feed=rss2"
            try:
                items = parse_feed(client.get(url).body)
            except Exception as e:
                ctx["errors"].append(f"{NAME} {base} «{query}»: {e}")
                continue
            for it in items:
                snippet = strip_html(it.description)[:600]
                out.append(RawMention(
                    url=it.link,
                    title=it.title,
                    source=NAME,
                    query=f"{query} [{domain_of(base)}]",
                    snippet=snippet,
                    source_name=site.get("name", domain_of(base)),
                    domain=domain_of(it.link) or domain_of(base),
                    published_at=it.published_at,
                    language=guess_language(f"{it.title} {snippet}", site.get("lang")),
                    query_has_strong_term=query_is_strong(query),
                ))
    return out
