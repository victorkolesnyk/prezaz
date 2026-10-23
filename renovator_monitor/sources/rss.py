"""Розбір RSS 2.0 і Atom без сторонніх бібліотек."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..textutil import collapse_ws, parse_date, strip_html


@dataclass
class FeedItem:
    title: str
    link: str
    description: str
    published_at: str | None
    source_name: str
    source_url: str


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()) if el is not None else ""


def parse_feed(data: bytes | str) -> list[FeedItem]:
    if isinstance(data, str):
        data = data.encode("utf-8")
    # DOCTYPE у стрічці новин не потрібен; відкидаємо, щоб не обробляти сутності.
    if b"<!DOCTYPE" in data[:2048].upper() or b"<!ENTITY" in data:
        raise ValueError("стрічка містить DOCTYPE/ENTITY, відхилено")
    root = ET.fromstring(data)
    items: list[FeedItem] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "item":
            # Google News: <source url=...>; Bing: <News:Source>.
            src = _child(el, "source")
            if src is None:  # Element без дітей хибний у bool, тому лише is None
                src = _child(el, "Source")
            items.append(FeedItem(
                title=collapse_ws(strip_html(_text(_child(el, "title")))),
                link=collapse_ws(_text(_child(el, "link"))),
                description=_text(_child(el, "description")) or _text(_child(el, "encoded")),
                published_at=parse_date(_text(_child(el, "pubDate")) or _text(_child(el, "date"))),
                source_name=collapse_ws(_text(src)),
                source_url=(src.get("url", "") if src is not None else ""),
            ))
        elif name == "entry":
            link = ""
            for c in el:
                if _local(c.tag) == "link" and c.get("rel", "alternate") == "alternate":
                    link = c.get("href", "")
                    break
            items.append(FeedItem(
                title=collapse_ws(strip_html(_text(_child(el, "title")))),
                link=link,
                description=_text(_child(el, "summary")) or _text(_child(el, "content")),
                published_at=parse_date(_text(_child(el, "published")) or _text(_child(el, "updated"))),
                source_name="",
                source_url="",
            ))
    return items
