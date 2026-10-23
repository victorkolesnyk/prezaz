"""Зчитування дампів дошок Trello (результат trelloReadCard list_by_board або
list_by_list) і розрахунок показників для портфеля.

Схема картки та сама, що в плагіні renovator-pm: назва "[код WBS] Текст",
опис із семи полів, "КОНТРОЛЬНА ПОДІЯ" у Примітці позначає віху,
ознака виконання — dueComplete.
"""
import json
import re
from collections import defaultdict

from .model import parse_date

FIELDS = ["Строк", "Попередник", "Відповідальний підрозділ",
          "Відповідальний КМС", "Виконавець", "Вартість", "Примітка"]
EMPTY = {"—", "-", "–", "", "немає", "нема"}
EA_ZONE = "поза сферою відповідальності кмс"


def load_cards(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "cards" in data:
        return data["cards"]["nodes"]
    if isinstance(data, dict) and "lists" in data:
        return [c for lst in data["lists"] for c in lst.get("cards", [])]
    raise SystemExit(f"Невідома структура файлу Trello: {path}")


def site_of(board_name):
    m = re.match(r"^\s*SITE\s*(\d+)", board_name or "", re.I)
    return m.group(1) if m else None


def money(text):
    m = re.search(r"([\d][\d\s  ]*(?:[.,]\d{1,2})?)\s*євро", text or "")
    if not m:
        return None
    raw = re.sub(r"[\s  ]", "", m.group(1)).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def term_end(text):
    """Кінцева дата з поля «Строк: 01.10.2026 – 30.06.2028»."""
    dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text or "")
    return parse_date(dates[-1]) if dates else None


def parse(cards):
    rows = []
    for c in cards:
        desc = c.get("desc") or ""
        board = (c.get("board") or {}).get("name", "")
        name = c.get("name", "")
        m = re.match(r"\[([\d.]+)\]", name)
        r = {
            "board": board, "site": site_of(board), "name": name,
            "wbs": m.group(1) if m else "",
            "list": (c.get("list") or {}).get("name", ""),
            "due": parse_date(c.get("due")),
            "done": bool(c.get("dueComplete")),
            "url": c.get("url", ""),
        }
        for f in FIELDS:
            mm = re.search(rf"^{f}:\s*(.*)$", desc, re.M)
            r[f] = mm.group(1).strip() if mm else ""
        r["milestone"] = "КОНТРОЛЬНА ПОДІЯ" in (r["Примітка"] + " " + name).upper()
        r["ea_zone"] = EA_ZONE in r["Відповідальний КМС"].lower()
        rows.append(r)
    return rows


def load_boards(paths):
    """Повертає {назва дошки: [рядки]} з усіх переданих файлів."""
    boards = defaultdict(list)
    for p in paths:
        for r in parse(load_cards(p)):
            boards[r["board"]].append(r)
    return dict(boards)


def _owner(text):
    # «звання Ім'я ПРІЗВИЩЕ — Керівник проєкту» -> «звання Ім'я ПРІЗВИЩЕ»
    return re.split(r"\s+—\s+", text or "")[0].strip() or "[не вказано]"


def metrics(rows, today):
    """Показники однієї дошки на дату today. Усі зсуви в днях."""
    work = [r for r in rows if r["wbs"]]
    by_code = {r["wbs"]: r for r in work}
    open_ = [r for r in work if not r["done"]]
    overdue = [r for r in open_ if r["due"] and r["due"] < today]
    ms_overdue = sorted(
        ({"wbs": r["wbs"], "name": r["name"], "due": r["due"], "slip": (today - r["due"]).days,
          "owner": _owner(r["Відповідальний КМС"]), "ea_zone": r["ea_zone"]}
         for r in overdue if r["milestone"]),
        key=lambda x: -x["slip"])
    upcoming = sorted(
        (r for r in open_ if r["milestone"] and r["due"] and 0 <= (r["due"] - today).days <= 30),
        key=lambda r: r["due"])

    # Зведена картка закрита, а дочірні ні: стан фази показано хибно
    closed_parent = []
    for r in work:
        if not r["done"]:
            continue
        kids = [k for k in open_ if k["wbs"].startswith(r["wbs"] + ".")]
        if kids:
            closed_parent.append({"wbs": r["wbs"], "name": r["name"], "open_children": len(kids)})

    # Дата в полі «Строк» не збігається з due картки
    term_mismatch = []
    for r in work:
        end = term_end(r["Строк"])
        if end and r["due"] and end != r["due"]:
            term_mismatch.append({"wbs": r["wbs"], "term": end, "due": r["due"]})

    # Сума дочірніх проти зведеної на рівень вище
    branch = []
    for r in work:
        parent = money(r["Вартість"])
        if parent is None:
            continue
        depth = r["wbs"].count(".")
        vals = [money(k["Вартість"]) for k in work
                if k["wbs"].startswith(r["wbs"] + ".") and k["wbs"].count(".") == depth + 1]
        vals = [v for v in vals if v is not None]
        if vals and abs(sum(vals) - parent) > 0.5:
            branch.append({"wbs": r["wbs"], "parent": parent, "children": sum(vals), "n": len(vals)})

    # Навантаження: відкриті картки з строком у найближчі 30 днів на одного власника
    load = defaultdict(int)
    for r in open_:
        if r["due"] and 0 <= (r["due"] - today).days <= 30 and not r["ea_zone"]:
            load[_owner(r["Відповідальний КМС"])] += 1

    # Кінець проєкту: найпізніший due серед фазових карток першого рівня
    phases = [r for r in work if "." not in r["wbs"]]
    planned_end = max((r["due"] for r in phases if r["due"]), default=None)

    return {
        "board": rows[0]["board"] if rows else "",
        "site": rows[0]["site"] if rows else None,
        "cards": len(work),
        "done": sum(1 for r in work if r["done"]),
        "overdue": len(overdue),
        "overdue_cards": sorted(({"wbs": r["wbs"], "due": r["due"], "slip": (today - r["due"]).days,
                                  "name": r["name"], "ea_zone": r["ea_zone"]} for r in overdue),
                                key=lambda x: -x["slip"]),
        "milestones": sum(1 for r in work if r["milestone"]),
        "milestones_overdue": ms_overdue,
        "max_milestone_slip": ms_overdue[0]["slip"] if ms_overdue else 0,
        "upcoming_milestones": [{"wbs": r["wbs"], "name": r["name"], "due": r["due"]} for r in upcoming],
        "closed_parent_open_children": closed_parent,
        "term_mismatch": term_mismatch,
        "branch_mismatch": branch,
        "ea_zone_open": sum(1 for r in open_ if r["ea_zone"]),
        "owner_load": dict(sorted(load.items(), key=lambda kv: -kv[1])),
        "planned_end": planned_end,
        "broken_predecessors": [r["wbs"] for r in work
                                if r["Попередник"] not in EMPTY
                                and any(p.strip() not in by_code
                                        for p in re.split(r"[;,]", r["Попередник"]) if p.strip())],
    }
