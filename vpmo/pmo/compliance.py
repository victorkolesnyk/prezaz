"""Перевірка семи принципів PRINCE2 7 для одного проєкту.

Кожна перевірка повертає (принцип, True | False | None, пояснення).
None означає, що даних для висновку немає; це не те саме, що порушення.
"""
from .model import BOARD_ROLES, STATUS_NAMES, TARGET_NAMES, TARGETS, has_tolerance, parse_date


def _status(p, key):
    return (p.get("products") or {}).get(key, "missing")


def business_justification(p, today):
    if _status(p, "business_case") == "missing":
        return False, "бізнес-кейсу немає"
    reviewed = parse_date(p.get("business_case_reviewed"))
    if not reviewed:
        return None, "бізнес-кейс є, дата перегляду не внесена"
    started = parse_date((p.get("stage") or {}).get("started"))
    if started and reviewed < started:
        return False, f"бізнес-кейс не переглядали з {reviewed:%d.%m.%Y}, етап почався {started:%d.%m.%Y}"
    return True, f"бізнес-кейс переглянуто {reviewed:%d.%m.%Y}"


def learn_from_experience(p, today):
    log = _status(p, "lessons_log")
    if log not in ("maintained", "approved"):
        return False, "журнал уроків не ведеться"
    if p.get("lessons_reviewed_at_start") is False:
        return False, "на старті не переглянуто уроки попередніх проєктів"
    return True, "журнал уроків ведеться"


def defined_roles(p, today):
    board = p.get("board") or {}
    missing = [BOARD_ROLES[r] for r in BOARD_ROLES if not (board.get(r) or "").strip()]
    if missing:
        return False, "не призначено: " + ", ".join(missing)
    if ";" in board.get("executive", "") or " і " in board.get("executive", ""):
        return False, "Голова Ради має бути одна особа"
    return True, "усі ролі Ради і Керівник проєкту призначені"


def manage_by_stages(p, today):
    stage = p.get("stage") or {}
    if not stage.get("process"):
        return None, "процес PRINCE2, у якому перебуває проєкт, не визначено"
    if stage.get("process") in ("SU", "closed"):
        return None, "проєкт ще не має етапів управління або закритий"
    if _status(p, "stage_plan") not in ("approved",):
        return False, "план поточного етапу не затверджено"
    boundary = parse_date(stage.get("boundary_date"))
    if not boundary:
        return False, "дату межі поточного етапу не визначено"
    if boundary < today:
        return False, f"межа етапу {boundary:%d.%m.%Y} минула, рішення Ради не зафіксовано"
    return True, f"наступна межа етапу {boundary:%d.%m.%Y}"


def manage_by_exception(p, today):
    tol = p.get("tolerances") or {}
    explicit = [t for t in TARGETS if has_tolerance(tol, t)]
    if not explicit:
        return False, "допуски не затверджено, діють лише значення політики портфеля"
    missing = [t for t in TARGETS if not has_tolerance(tol, t)]
    if missing:
        return None, "допуски задано частково, бракує: " + ", ".join(TARGET_NAMES[t].lower() for t in missing)
    return True, "допуски задано для всіх семи показників"


def focus_on_products(p, today):
    st = _status(p, "product_descriptions")
    if st == "missing":
        return False, "описів продуктів із критеріями якості немає"
    return True, f"описи продуктів: {STATUS_NAMES[st]}"


def tailor(p, today):
    if _status(p, "tailoring") == "missing" and not (p.get("tailoring_note") or "").strip():
        return False, "положення про адаптацію немає"
    return True, "адаптацію задокументовано"


PRINCIPLES = [
    ("Безперервне бізнес-обґрунтування", business_justification),
    ("Навчання на досвіді", learn_from_experience),
    ("Визначені ролі, обов'язки і стосунки", defined_roles),
    ("Управління за етапами", manage_by_stages),
    ("Управління за винятками", manage_by_exception),
    ("Фокус на продуктах", focus_on_products),
    ("Адаптація до контексту", tailor),
]


def check(project, today):
    out = []
    for name, fn in PRINCIPLES:
        ok, why = fn(project, today)
        out.append((name, ok, why))
    return out


def board_findings(m):
    """Знахідки за даними Trello, що стосуються якості реєстру, а не допусків."""
    if not m:
        return []
    out = []
    for c in m["closed_parent_open_children"]:
        out.append(f"[{c['wbs']}] позначено виконаною, хоча відкритих дочірніх карток {c['open_children']}")
    for b in m["branch_mismatch"]:
        out.append(f"[{b['wbs']}] зведена сума {b['parent']:,.0f} проти суми {b['n']} дочірніх "
                   f"{b['children']:,.0f}".replace(",", " "))
    if m["term_mismatch"]:
        codes = ", ".join(f"[{t['wbs']}]" for t in m["term_mismatch"][:8])
        more = len(m["term_mismatch"]) - 8
        out.append(f"дата в полі «Строк» не збігається з датою картки: {codes}"
                   + (f" і ще {more}" if more > 0 else ""))
    if m["broken_predecessors"]:
        out.append("посилання на неіснуючого попередника: "
                   + ", ".join(f"[{w}]" for w in m["broken_predecessors"]))
    return out
