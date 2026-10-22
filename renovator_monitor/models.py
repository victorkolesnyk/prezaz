"""Сира знахідка з джерела до запису в реєстр."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawMention:
    url: str
    title: str
    source: str              # ідентифікатор конектора: google_news, gdelt, ...
    query: str               # запит, за яким знайдено
    snippet: str = ""
    source_name: str = ""    # назва видання або каналу
    domain: str = ""         # домен видання (не агрегатора)
    published_at: str | None = None
    language: str | None = None
    # True, якщо пошуковий рушій сам шукав термін у повному тексті:
    # знахідка є свідченням згадки, навіть коли в заголовку терміна немає.
    query_has_strong_term: bool = False
    extra: dict = field(default_factory=dict)
