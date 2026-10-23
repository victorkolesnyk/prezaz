"""Пріоритизація портфеля (MoP: пріоритизувати і збалансувати).

Два режими:
  rank   — зважена багатокритеріальна оцінка проєктів портфеля;
  fund   — відбір позицій обсягу в межах наявних коштів (поетапне вивільнення
           фінансування): спершу обов'язкові, далі в порядку оцінки; позиція
           береться разом з усіма попередниками; плюс перевірка чутливості до ваг.

Відбір навмисно не максимізує суму оцінок на гривню: така оптимізація
витісняє дорогі важливі позиції дешевими другорядними, і Раді важко
пояснити, чому благоустрій профінансовано раніше за корпус.

Оцінки за критеріями ставлять люди. Код лише рахує і показує, від чого
залежить результат; він не вирішує за Голову Ради.
"""


def weighted(scores, criteria):
    """Зважена сума оцінок 0..5, нормована до 0..100. Відсутня оцінка = None."""
    if any(scores.get(c["key"]) is None for c in criteria):
        return None
    total = sum(c["weight"] * scores[c["key"]] for c in criteria)
    return round(100 * total / 5, 1)


def rank(projects, criteria):
    rows = []
    for p in projects:
        s = weighted(p.get("scores") or {}, criteria)
        rows.append({"id": p["id"], "name": p.get("name", ""), "score": s,
                     "missing": [c["key"] for c in criteria if (p.get("scores") or {}).get(c["key"]) is None]})
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def _closure(item_id, items, chosen):
    """Позиція разом із її ще не відібраними попередниками."""
    need, stack = [], [item_id]
    while stack:
        cur = stack.pop()
        if cur in chosen or cur in need:
            continue
        need.append(cur)
        stack.extend(items[cur].get("depends_on") or [])
    return need


def fund(scenario, weights_override=None):
    """Відбір позицій. Повертає dict із переліками funded/unfunded і сумами."""
    criteria = scenario["criteria"]
    if weights_override:
        criteria = [dict(c, weight=weights_override.get(c["key"], c["weight"])) for c in criteria]
        total_w = sum(c["weight"] for c in criteria)
        criteria = [dict(c, weight=c["weight"] / total_w) for c in criteria]
    items = {i["id"]: dict(i) for i in scenario["items"]}
    for i in items.values():
        for dep in i.get("depends_on") or []:
            if dep not in items:
                raise SystemExit(f"Позиція {i['id']} залежить від невідомої {dep}")
        i["_score"] = weighted(i.get("scores") or {}, criteria)
    budget = scenario["budget_available"]
    chosen, spent, notes = [], 0.0, []

    for i in sorted((i for i in items.values() if i.get("mandatory")), key=lambda i: i["id"]):
        group = _closure(i["id"], items, chosen)
        chosen += group
        spent += sum(items[g]["cost"] for g in group)
    if spent > budget:
        notes.append("Обов'язкові позиції разом із залежностями вже перевищують наявні кошти")

    # Порядок пріоритету: вища оцінка першою, за рівності дешевша. Позиція, що
    # не вміщується, пропускається, але нижчі за нею можуть пройти: це видно у звіті.
    skipped = []
    order = sorted((i for i in items.values() if i["_score"] is not None and not i.get("mandatory")),
                   key=lambda i: (-i["_score"], i["cost"], i["id"]))
    for i in order:
        if i["id"] in chosen:
            continue
        group = _closure(i["id"], items, chosen)
        cost = sum(items[g]["cost"] for g in group)
        if spent + cost <= budget:
            chosen += group
            spent += cost
        else:
            skipped.append(i["id"])

    unscored = [i["id"] for i in items.values() if i["_score"] is None]
    if unscored:
        notes.append("Без повних оцінок, у відбір не входили: " + ", ".join(unscored))
    return {
        "funded": [items[c] for c in chosen],
        "unfunded": [i for i in items.values() if i["id"] not in chosen],
        "spent": spent,
        "budget": budget,
        "need": sum(i["cost"] for i in items.values()),
        "notes": notes,
        "skipped": skipped,
    }


def sensitivity(scenario, step=0.2):
    """Які позиції міняють статус, якщо вагу одного критерію змінити на ±step (частка)."""
    base = {i["id"] for i in fund(scenario)["funded"]}
    flips = {}
    for c in scenario["criteria"]:
        for sign in (-1, 1):
            w = {c["key"]: max(0.0, c["weight"] * (1 + sign * step))}
            got = {i["id"] for i in fund(scenario, w)["funded"]}
            for changed in base ^ got:
                flips.setdefault(changed, []).append(f"{c['key']} {'+' if sign > 0 else '-'}{int(step * 100)} %")
    return flips
