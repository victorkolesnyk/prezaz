"""Google News RSS: пошук за запитом у кількох мовних редакціях.

Формат: https://news.google.com/rss/search?q=...&hl=uk&gl=UA&ceid=UA:uk
Посилання ведуть на news.google.com (перенаправлення), тому домен видання
беремо з елемента <source url="...">.
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import query_is_strong
from ..textutil import domain_of, guess_language, strip_html
from .rss import parse_feed

log = logging.getLogger(__name__)
NAME = "google_news"


def build_url(query: str, hl: str, gl: str, ceid: str, when: str | None) -> str:
    q = f"{query} when:{when}" if when else query
    return (f"https://news.google.com/rss/search?q={quote_plus(q)}"
            f"&hl={hl}&gl={gl}&ceid={ceid}")


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    when = None if ctx.get("backfill") else cfg.get("when")
    out: list[RawMention] = []
    for ed in cfg.get("editions", []):
        lang = ed.get("hl", "").split("-")[0] or None
        for query in ed.get("queries", []):
            url = build_url(query, ed["hl"], ed["gl"], ed["ceid"], when)
            try:
                items = parse_feed(client.get(url).body)
            except Exception as e:  # одне джерело не валить увесь прогін
                ctx["errors"].append(f"{NAME} [{ed['ceid']}] «{query}»: {e}")
                continue
            for it in items:
                snippet = strip_html(it.description)
                # Опис у Google News зазвичай дублює заголовок і назву видання.
                if snippet.startswith(it.title[:40]):
                    snippet = ""
                out.append(RawMention(
                    url=it.link,
                    title=it.title,
                    source=NAME,
                    query=f"{query} [{ed['ceid']}]",
                    snippet=snippet,
                    source_name=it.source_name,
                    domain=domain_of(it.source_url) if it.source_url else "",
                    published_at=it.published_at,
                    language=guess_language(it.title, lang),
                    query_has_strong_term=query_is_strong(query),
                ))
    return out
