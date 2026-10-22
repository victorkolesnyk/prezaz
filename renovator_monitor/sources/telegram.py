"""Публічні Telegram-канали через веб-перегляд https://t.me/s/<канал>?q=<запит>.

Глобального пошуку по Telegram без облікового запису немає, тому список
каналів задається в конфігурації. Працює лише для публічних каналів з
увімкненим веб-переглядом.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import quote_plus

from ..fetch import HttpClient
from ..models import RawMention
from ..relevance import detect_term, query_is_strong
from ..textutil import collapse_ws, guess_language, parse_date

NAME = "telegram"


class _ChannelParser(HTMLParser):
    """Витягує повідомлення: data-post, текст, дату."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.messages: list[dict] = []
        self._cur: dict | None = None
        self._text_depth = 0       # глибина div усередині тексту повідомлення
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "div" and "tgme_widget_message" in cls and a.get("data-post"):
            self._flush()
            self._cur = {"post": a["data-post"], "text": "", "date": None}
            return
        if self._cur is None:
            return
        if self._text_depth:
            if tag == "div":
                self._text_depth += 1
            if tag == "br":
                self._text_parts.append("\n")
            return
        if tag == "div" and "tgme_widget_message_text" in cls:
            self._text_depth = 1
            self._text_parts = []
        elif tag == "time" and a.get("datetime") and not self._cur["date"]:
            self._cur["date"] = a["datetime"]

    def handle_endtag(self, tag):
        if self._text_depth and tag == "div":
            self._text_depth -= 1
            if not self._text_depth and self._cur is not None:
                raw = "".join(self._text_parts)
                self._cur["text"] = "\n".join(
                    collapse_ws(line) for line in raw.split("\n") if line.strip())

    def handle_data(self, data):
        if self._text_depth:
            self._text_parts.append(data)

    def _flush(self):
        if self._cur is not None:
            self.messages.append(self._cur)
        self._cur = None
        self._text_depth = 0

    def close(self):
        super().close()
        self._flush()


def parse_channel(html_text: str) -> list[dict]:
    p = _ChannelParser()
    p.feed(html_text)
    p.close()
    return p.messages


def collect(client: HttpClient, cfg: dict, ctx: dict) -> list[RawMention]:
    out: list[RawMention] = []
    for channel in cfg.get("channels", []):
        handle = channel.lstrip("@").strip()
        if not handle:
            continue
        for query in cfg.get("queries", []):
            url = f"https://t.me/s/{handle}?q={quote_plus(query)}"
            try:
                messages = parse_channel(client.get(url).text())
            except Exception as e:
                ctx["errors"].append(f"{NAME} @{handle} «{query}»: {e}")
                continue
            for m in messages:
                text = m["text"]
                # Бот бачить увесь текст допису: без терміна в ньому це не згадка.
                if not text or detect_term(text) == "none":
                    continue
                first_line = text.split("\n", 1)[0]
                out.append(RawMention(
                    url=f"https://t.me/{m['post']}",
                    title=first_line[:200],
                    source=NAME,
                    query=f"{query} [@{handle}]",
                    snippet=text[:1000],
                    source_name=f"t.me/{handle}",  # не «@...»: Excel сприймає @ як формулу
                    domain="t.me",
                    published_at=parse_date(m["date"]),
                    language=guess_language(text),
                    query_has_strong_term=query_is_strong(query),
                    literal_search=True,
                ))
    return out
