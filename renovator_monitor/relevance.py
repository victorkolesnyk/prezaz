"""Оцінка релевантності згадки до проєкту НАТО «Реноватор».

Головна проблема предметної області: англійське renovator є звичайним словом
(ремонтник житла, мультитул, телешоу), тоді як кириличне «Реноватор» майже
завжди означає саме проєкт. Тому оцінка зважує:

* сам термін у заголовку чи анотації (кирилиця або «Project/Operation
  Renovator» сильніші за голе renovator);
* свідчення пошукового рушія: запит із сильним терміном означає, що термін є
  в повному тексті, навіть коли заголовок про нього мовчить;
* контекстні групи (НАТО, Україна, реабілітація, госпіталі, військові,
  країни-лідери, учасники управління проєктом);
* негативні маркери побутового ремонту та інструментів.

Оцінка прозора: у записі зберігається, що саме спрацювало.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import fold

STRONG_CYR = re.compile(r"\bреноватор\w*", re.I)
STRONG_LAT = re.compile(
    r"\b(?:project|operation|programme|program|initiative|projekt\w*|prosjekt\w*)"
    r"\s+[«\"“'„]?renovator\b"
    r"|\brenovator\W{0,3}\s*(?:project|programme|initiative|projekt\w*|prosjekt\w*)\b"
    r"|\bnato\W{0,3}s?\s+renovator\b"
    r"|[«\"“„]renovator[»\"”“]",
    re.I,
)
WEAK_LAT = re.compile(r"\brenovator\b", re.I)

CONTEXT: dict[str, re.Pattern] = {
    "nato": re.compile(r"\bnato\b|\bнато\b|\botan\b|альянс\w*|alliance|allies|союзник\w*", re.I),
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
        r"\bлатві\w*|\bлитв\w*|\bнорвег\w*|\bшвеці\w*|\bбритан\w*|\blatvi\w*|\blithuani\w*"
        r"|\bnorw\w*|\bswed\w*|\bunited kingdom\b|\bbritish\b|\bbritain\b|\blatvij\w*|\blietuv\w*"
        r"|\bnorg\w*|\bnorsk\w*|\bsverig\w*|\bsvensk\w*", re.I),
    "governance": re.compile(
        r"comprehensive assistance package|комплексн\w*\s+пакет\w*|\bвсебічн\w*\s+пакет\w*"
        r"|командуванн\w*\s+медичних\s+сил|medical forces command|\bnspa\b|\bncia\b"
        r"|executive agent|виконавч\w*\s+агент\w*", re.I),
}

NEGATIVE: dict[str, re.Pattern] = {
    "home_renovation": re.compile(
        r"\bkitchen\w*|\bbathroom\w*|\bhome renovat\w*|\bhouse flip\w*|\breal estate\b|\brealtor\w*"
        r"|\bremodel\w*|\bdiy\b|\bfixer[- ]upper\b|\bhomeowner\w*|\binterior design\w*"
        r"|\bproperty (?:market|developer|investor)\w*|\bквартир\w*|\bкухн\w*|\bванн\w*\s+кімнат\w*"
        r"|\bнерухоміст\w*|\bдизайн\w*\s+інтер.єр\w*|\bжитлов\w*\s+комплекс\w*|\bжк\b"
        r"|\bзабудовник\w*|\bремонт\w*\s+(?:квартир|будинк|під ключ)\w*", re.I),
    "tools": re.compile(
        r"\boscillating\b|\bmulti-?tool\w*|\bpower tool\w*|\bsander\w*|\bblade\w*|\bcordless\b"
        r"|\bінструмент\w*|\bшліфмашин\w*", re.I),
    "entertainment": re.compile(
        r"\btv (?:show|series)\b|\bseason \d+\b|\bepisode\b|\bvideo game\b|\bsteam\b|\bnetflix\b"
        r"|\bтелешоу\b|\bсеріал\w*", re.I),
}

THRESHOLD_RELEVANT = 60
THRESHOLD_UNCERTAIN = 30


@dataclass
class Score:
    score: int
    status: str                      # relevant | uncertain | irrelevant
    term: str                        # strong | weak | none
    context: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)


def query_is_strong(query: str) -> bool:
    """Чи доводить сама знахідка за цим запитом, що в тексті є згадка проєкту."""
    q = fold(query)
    if "реноватор" in q:
        return True
    if "renovator" not in q:
        return False
    return bool(re.search(r"nato|нато|ukrain|україн|ukrain|project|operation|projekt|prosjekt", q))


_TERM_RANK = {"none": 0, "weak": 1, "strong": 2}
_TERM_BASE = {"none": 0, "weak": 20, "strong": 50}


def detect_term(text: str) -> str:
    t = fold(text)
    if STRONG_CYR.search(t) or STRONG_LAT.search(t):
        return "strong"
    if WEAK_LAT.search(t):
        return "weak"
    return "none"


def score_text(text: str, query_strong: bool = False, page_term: str | None = None) -> Score:
    """page_term: результат перевірки самої сторінки (detect_term по її тексту), якщо була."""
    t = fold(text)
    term = detect_term(text)
    if page_term and _TERM_RANK[page_term] > _TERM_RANK[term]:
        term = page_term
    base = _TERM_BASE[term]

    if query_strong:
        # Термін є в повному тексті (так шукав рушій), але не в анотації: вагоме свідчення.
        # Якщо термін уже видно, рушій лише підтверджує контекстні слова запиту.
        base += 30 if term == "none" else 10

    context = [name for name, rx in CONTEXT.items() if rx.search(t)]
    negative = [name for name, rx in NEGATIVE.items() if rx.search(t)]
    value = base + min(10 * len(context), 40) - min(15 * len(negative), 45)
    # Без жодного свідчення терміна згадка не може бути релевантною, хоч би який був контекст.
    if term == "none" and not query_strong:
        value = min(value, THRESHOLD_UNCERTAIN - 1)
    value = max(0, min(100, value))

    if value >= THRESHOLD_RELEVANT:
        status = "relevant"
    elif value >= THRESHOLD_UNCERTAIN:
        status = "uncertain"
    else:
        status = "irrelevant"
    return Score(value, status, term, context, negative)
