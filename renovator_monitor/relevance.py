"""Оцінка релевантності згадки до проєкту НАТО «Реноватор».

Головна проблема предметної області: обидва написання багатозначні.
Англійське renovator означає майстра ремонту, мультитул, телешоу. Українське
«реноватор» у торгівлі є звичайною назвою осцилюючого багатофункціонального
інструмента («Реноватор акумуляторний ...»). Тому:

* фраза-назва («проєкт «Реноватор»», «Project Renovator», «NATO Renovator»,
  слово в лапках) важить більше за голе слово;
* голе слово без жодного контекстного маркера проєкту ніколи не стає
  релевантним, лише «потребує перевірки»;
* знахідка за запитом із сильним терміном є свідченням згадки в повному тексті,
  але повною мірою лише для джерел із буквальним повнотекстовим пошуком
  (GDELT, WordPress, GOV.UK, Telegram). Google News і Bing шукають нечітко,
  тому без видимого терміна їхня знахідка лишається «потребує перевірки»;
* маркери побутового ремонту, торгівлі інструментом і розваг знижують оцінку.

Оцінка прозора: у записі зберігається, що саме спрацювало.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import fold

_Q_OPEN = "«\"“„'"
_Q_CLOSE = "»\"”“'"

# Голе кириличне слово з будь-яким відмінковим закінченням.
CYR_WORD = re.compile(r"\bреноватор\w*", re.I)
# Кирилична фраза-назва: «проєкт Реноватор», НАТО «Реноватор», слово в лапках.
CYR_PHRASE = re.compile(
    rf"\b(?:проєкт\w*|проект\w*|ініціатив\w*|програм\w*|операці\w*|нато)\W{{0,3}}\s*[{_Q_OPEN}]?реноватор\w*"
    rf"|[{_Q_OPEN}]реноватор\w*[{_Q_CLOSE}]",
    re.I,
)
LAT_PHRASE = re.compile(
    r"\b(?:project|operation|programme|program|initiative|projekt\w*|prosjekt\w*)"
    rf"\s+[{_Q_OPEN}]?renovator\w*"
    r"|\brenovator\W{0,3}\s*(?:project|programme|initiative|projekt\w*|prosjekt\w*)\b"
    r"|\bnato\W{0,3}s?\s+renovator\b"
    rf"|[{_Q_OPEN}]renovator\w*[{_Q_CLOSE}]",
    re.I,
)
# \w* ловить литовські відмінки (Renovatoriaus) і англійську множину.
LAT_WORD = re.compile(r"\brenovator\w*", re.I)

CONTEXT: dict[str, re.Pattern] = {
    "nato": re.compile(r"\bnato\b|\bнато\b|\botan\b|\bальянс\w*|\balliance\b|\ballies\b|\bсоюзник\w*", re.I),
    "ukraine": re.compile(r"\bukrain\w*|\bукраїн\w*|\bзсу\b", re.I),
    "rehab": re.compile(
        r"\bреабіліт\w*|\brehabilit\w*|\brehabilitāc\w*|\breabilitac\w*|\bпоранен\w*|\bwounded\b"
        r"|\bprotez\w*|\bprosthe\w*|\bпротез\w*|\bфізіотерап\w*|\bphysiother\w*", re.I),
    "medical": re.compile(
        r"\bгоспітал\w*|\bшпитал\w*|\bhospital\w*|\bslimnīc\w*|\bligonin\w*|\bsykehus\w*|\bsjukhus\w*"
        r"|\bмедичн\w*|\bmedical\b|\bmedicin\w*|\bmedisin\w*|\bmedicīn\w*|\bмедик\w*|\bлікар\w*", re.I),
    "military": re.compile(
        r"\bвійськов\w*|\bзбройн\w*\s+сил\w*|\barmed forces\b|\bmilitary\b|\bmilitær\w*|\bmilitär\w*"
        r"|\bmilitār\w*|\bkarinin\w*|\bkariuomen\w*|\bbruņot\w*|\bforsvar\w*|\bförsvar\w*"
        r"|\bdefen[cs]e\b|\bміноборон\w*|\bministry of defen[cs]e\b", re.I),
    "lead_nations": re.compile(
        r"\bлатві\w*|\bлитв\w*|\bлитовськ\w*|\bнорвег\w*|\bнорвезьк\w*|\bшвеці\w*|\bшведськ\w*"
        r"|\bбритан\w*|\blatvi\w*|\blithuani\w*|\bnorw\w*|\bswed\w*|\bunited kingdom\b|\bbritish\b"
        r"|\bbritain\b|\blatvij\w*|\blietuv\w*|\bnorg\w*|\bnorsk\w*|\bsverig\w*|\bsvensk\w*", re.I),
    "governance": re.compile(
        r"comprehensive assistance package|комплексн\w*\s+пакет\w*|\bвсебічн\w*\s+пакет\w*"
        r"|командуванн\w*\s+медичних\s+сил|medical forces command|\bnspa\b|\bncia\b"
        r"|executive agent|виконавч\w*\s+агент\w*", re.I),
}

NEGATIVE: dict[str, re.Pattern] = {
    "home_renovation": re.compile(
        r"\bkitchen\w*|\bbathroom\w*|\bhome renovat\w*|\bhouse flip\w*|\breal estate\b|\brealtor\w*"
        r"|\bremodel\w*|\bdiy\b|\bfixer[- ]upper\b|\bhomeowner\w*|\binterior design\w*"
        r"|\bproperty (?:market|developer|investor)\w*|(?<!штаб-)\bквартир\w*|\bкухн\w*"
        r"|\bванн\w*\s+кімнат\w*|\bнерухоміст\w*|\bдизайн\w*\s+інтер.єр\w*|\bжитлов\w*\s+комплекс\w*"
        r"|\bжк\b|\bзабудовник\w*|\bремонт\w*\s+(?:квартир|будинк|під ключ)\w*", re.I),
    "tools": re.compile(
        r"\boscillating\b|\bmulti-?tool\w*|\bpower tool\w*|\bsander\w*|\bcordless\b|\bblade\w*"
        r"|\bосцил\w*|\bмультитул\w*|\bбагатофункціональн\w*\s+інструмент\w*|\bелектроінструмент\w*"
        r"|\bакумулятор\w*|\bнасадк\w*|\bшліфмашин\w*|\bbosch\b|\bmakita\b|\bfein\b|\bdewalt\b"
        r"|\bmetabo\b|\bryobi\b|\bdnipro-m\b", re.I),
    "shop": re.compile(
        r"\bціна\b|\bкупити\b|\bвідгук\w*|\bзнижк\w*|\bв наявності\b|\bінтернет-магазин\w*"
        r"|\bbuy now\b|\badd to cart\b|\bon sale\b|\bdiscount\w*|\bbest .{0,30} of 20\d\d\b", re.I),
    "entertainment": re.compile(
        r"\btv (?:show|series)\b|\bseason \d+\b|\bepisode\b|\bvideo game\b|\bsteam\b|\bnetflix\b"
        r"|\bтелешоу\b|\bсеріал\w*", re.I),
}

# Торговельні майданчики: згадка там майже напевно про інструмент.
SHOP_DOMAINS = ("rozetka.com.ua", "prom.ua", "epicentrk.ua", "olx.ua", "allo.ua", "hotline.ua",
                "amazon.", "ebay.", "aliexpress.")

THRESHOLD_RELEVANT = 60
THRESHOLD_UNCERTAIN = 30

TERM_LEVELS = ("none", "weak", "word", "strong")
_TERM_BASE = {"none": 0, "weak": 20, "word": 40, "strong": 50}


@dataclass
class Score:
    score: int
    status: str                      # relevant | uncertain | irrelevant
    term: str                        # strong | word | weak | none
    context: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)


def query_is_strong(query: str) -> bool:
    """Чи доводить знахідка за цим запитом (у буквальному пошуку), що в тексті є згадка проєкту."""
    q = fold(query)
    if "реноватор" in q:
        return True
    if "renovator" not in q:
        return False
    return bool(re.search(r"nato|нато|ukrain|україн|project|operation|projekt|prosjekt", q))


def detect_term(text: str) -> str:
    t = fold(text)
    if CYR_PHRASE.search(t) or LAT_PHRASE.search(t):
        return "strong"
    if CYR_WORD.search(t):
        return "word"
    if LAT_WORD.search(t):
        return "weak"
    return "none"


def _cap(value: int, limit: int) -> int:
    return min(value, limit)


def score_text(text: str, query_strong: bool = False, query_literal: bool = False,
               page_term: str | None = None, domain: str = "") -> Score:
    """query_literal: знахідку дав буквальний повнотекстовий пошук.
    page_term: результат detect_term по тексту самої сторінки, якщо її перевіряли."""
    t = fold(text)
    term = detect_term(text)
    if page_term and TERM_LEVELS.index(page_term) > TERM_LEVELS.index(term):
        term = page_term
    value = _TERM_BASE[term]
    if query_strong:
        # Термін є в повному тексті (так шукав рушій), хоч в анотації його не видно.
        value += 30 if term == "none" else 10

    context = [name for name, rx in CONTEXT.items() if rx.search(t)]
    negative = [name for name, rx in NEGATIVE.items() if rx.search(t)]
    if domain and any(d in domain for d in SHOP_DOMAINS):
        negative.append("shop_domain")
    value += min(10 * len(context), 40) - min(15 * len(negative), 45)

    uncertain_cap = THRESHOLD_RELEVANT - 1
    if term == "none":
        if not query_strong:
            # Жодного свідчення терміна: контекст сам нічого не доводить.
            value = _cap(value, THRESHOLD_UNCERTAIN - 1)
        elif not query_literal:
            # Нечіткий пошук (Google News, Bing) міг знайти статтю й без терміна.
            value = _cap(value, uncertain_cap)
    if term == "none" and page_term == "none":
        # Сторінку завантажили, а терміна в тексті немає: свідченню пошуку не довіряємо.
        value = _cap(value, uncertain_cap)
    if not context:
        # Голе слово без жодного маркера проєкту: можливо інструмент чи ремонт.
        value = _cap(value, uncertain_cap)
    value = max(0, min(100, value))

    if value >= THRESHOLD_RELEVANT:
        status = "relevant"
    elif value >= THRESHOLD_UNCERTAIN:
        status = "uncertain"
    else:
        status = "irrelevant"
    return Score(value, status, term, context, negative)
