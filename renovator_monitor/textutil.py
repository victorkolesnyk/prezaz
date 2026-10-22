"""Нормалізація тексту, URL і дат, спільна для всіх джерел."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Параметри, які не змінюють зміст сторінки і лише заважають дедуплікації.
_TRACKING_PARAMS = {
    "fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src",
    "oc", "ocid", "cmpid", "spm", "s_cid", "at_medium", "at_campaign",
}

# Агрегатори: їхні посилання гірші за пряме посилання на видання.
AGGREGATOR_HOSTS = ("news.google.com", "bing.com", "msn.com")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "template"}
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def strip_html(value: str | None) -> str:
    """HTML у звичайний текст з одинарними пробілами."""
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = "".join(parser.parts)
    except Exception:  # пошкоджений HTML не має зупиняти збір
        text = re.sub(r"<[^>]+>", " ", value)
    return collapse_ws(html.unescape(text))


def collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def fold(value: str) -> str:
    """Регістронезалежна форма для пошуку збігів: NFKC, casefold, ґ/ё не чіпаємо."""
    return unicodedata.normalize("NFKC", value).casefold()


def title_key(title: str, source_name: str = "") -> str:
    """Ключ заголовка для дедуплікації між агрегаторами.

    Google News додає « - Назва видання» в кінець заголовка, тому хвіст
    із назвою джерела відрізаємо.
    """
    t = collapse_ws(title)
    if source_name:
        for sep in (" - ", " – ", " — ", " | "):
            suffix = f"{sep}{source_name}"
            if t.endswith(suffix):
                t = t[: -len(suffix)]
                break
    t = fold(t)
    t = re.sub(r"[^\w]+", " ", t)
    return collapse_ws(t)


def canonical_url(url: str) -> str:
    """Канонічний URL: https, без www, без фрагмента і трекінгових параметрів."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def strip_tracking(url: str) -> str:
    """Прибирає utm_* та подібні параметри, не чіпаючи хост і схему (на відміну від canonical_url)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    if not parts.query:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def domain_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_aggregator(url: str) -> bool:
    host = domain_of(url)
    return any(host == h or host.endswith("." + h) for h in AGGREGATOR_HOSTS)


def short_hash(*parts: str, length: int = 12) -> str:
    h = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return h[:length]


def parse_date(value: str | None) -> str | None:
    """Будь-який із поширених форматів дати у ISO 8601 UTC або None."""
    if not value:
        return None
    value = value.strip()
    dt: datetime | None = None
    try:
        dt = parsedate_to_datetime(value)  # RFC 822 з RSS
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value.replace("+00:00", "+0000") if "%z" in fmt else value, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_UK_LETTERS = set("іїєґ")
_CYR = re.compile(r"[Ѐ-ӿ]")
_LAT = re.compile(r"[A-Za-z]")


def guess_language(text: str, hint: str | None = None) -> str:
    """Груба оцінка мови за алфавітом і діакритикою.

    Підказка джерела (hl= у Google News) уточнює латинські мови, але не
    переважує очевидну розбіжність алфавіту: в українській редакції
    трапляються англомовні статті.
    """
    low = text.lower()
    cyr = len(_CYR.findall(low))
    lat = len(_LAT.findall(low))
    if cyr > lat:
        return "uk" if any(ch in _UK_LETTERS for ch in low) or hint == "uk" else "cyrillic"
    if lat and hint and hint not in ("uk",):
        return hint
    if any(ch in low for ch in "āēīļņķģ"):
        return "lv"
    if any(ch in low for ch in "ąęėįų"):
        return "lt"
    if any(ch in low for ch in "æø"):
        return "no"
    if "ä" in low or "ö" in low:
        return "sv"
    return "en" if lat else "unknown"
