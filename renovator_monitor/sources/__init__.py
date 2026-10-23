"""Конектори джерел. Кожен повертає список RawMention і не пише в реєстр."""

from __future__ import annotations

from typing import Callable

from ..fetch import HttpClient
from ..models import RawMention
from . import bing_news, gdelt, google_news, govuk, telegram, wordpress

Collector = Callable[[HttpClient, dict, dict], list[RawMention]]

# Порядок має значення: перші джерела дають кращі прямі URL для злиття дублікатів.
COLLECTORS: dict[str, Collector] = {
    "gdelt": gdelt.collect,
    "wordpress": wordpress.collect,
    "govuk": govuk.collect,
    "telegram": telegram.collect,
    "bing_news": bing_news.collect,
    "google_news": google_news.collect,
}
