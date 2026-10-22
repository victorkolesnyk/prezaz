"""Bing News RSS: https://www.bing.com/news/search?q=...&format=rss

Посилання мають вигляд bing.com/news/apiclick.aspx?...&url=<справжній URL>,
справжню адресу видання дістаємо з параметра url.
"""

from __future__ import annotations

from urllib.parse import parse_qs, quote_plus, urlsplit

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import query_is_strong
from ..textutil import domain_of, guess_language, is_aggregator, strip_html
from .rss import parse_feed

NAME = "bing_news"


def unwrap(link: str) -> str:
    if not is_aggregator(link):
        return link
    target = parse_qs(urlsplit(link).query).get("url")
    return target[0] if target else link


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    out: list[RawMention] = []
    for market in cfg.get("markets", []):
        for query in market.get("queries", []):
            url = (f"https://www.bing.com/news/search?q={quote_plus(query)}"
                   f"&format=rss&setlang={market['setlang']}&cc={market['cc']}")
            try:
                items = parse_feed(client.get(url).body)
            except Exception as e:
                ctx["errors"].append(f"{NAME} [{market['cc']}] «{query}»: {e}")
                continue
            for it in items:
                real = unwrap(it.link)
                out.append(RawMention(
                    url=real,
                    title=it.title,
                    source=NAME,
                    query=f"{query} [{market['cc']}]",
                    snippet=strip_html(it.description),
                    source_name=it.source_name,
                    domain=domain_of(real) if not is_aggregator(real) else "",
                    published_at=it.published_at,
                    language=guess_language(f"{it.title} {it.description}",
                                            market.get("setlang")),
                    query_has_strong_term=query_is_strong(query),
                ))
    return out
