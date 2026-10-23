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
    # True для буквального повнотекстового пошуку (GDELT, WordPress, GOV.UK, Telegram);
    # False для нечіткого (Google News, Bing), що може повернути статтю й без терміна.
    literal_search: bool = False
    extra: dict = field(default_factory=dict)
