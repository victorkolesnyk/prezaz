"""Пошуковий API GOV.UK: офіційні публікації уряду Великої Британії (провідна країна одного з центрів).

https://www.gov.uk/api/search.json?q=...&order=-public_timestamp
"""

from __future__ import annotations

import json
from urllib.parse import quote_plus

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import query_is_strong
from ..textutil import parse_date

NAME = "govuk"
FIELDS = "title,description,link,public_timestamp,format"


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    out: list[RawMention] = []
    for query in cfg.get("queries", []):
        url = (f"https://www.gov.uk/api/search.json?q={quote_plus(query)}"
               f"&count={int(cfg.get('count', 50))}&order=-public_timestamp"
               + "".join(f"&fields={f}" for f in FIELDS.split(",")))
        try:
            data = json.loads(client.get(url).text())
        except Exception as e:
            ctx["errors"].append(f"{NAME} «{query}»: {e}")
            continue
        for r in data.get("results", []) or []:
            link = r.get("link", "")
            if link.startswith("/"):
                link = "https://www.gov.uk" + link
            out.append(RawMention(
                url=link,
                title=r.get("title", "") or "",
                source=NAME,
                query=query,
                snippet=r.get("description", "") or "",
                source_name="GOV.UK",
                domain="gov.uk",
                published_at=parse_date(r.get("public_timestamp")),
                language="en",
                query_has_strong_term=query_is_strong(query),
                literal_search=True,
            ))
    return out
