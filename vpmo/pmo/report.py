"""Звіти віртуального PMO у Markdown.

Правила подання: висновок першим реченням, заголовок несе висновок, без
кольорів і значків, усе, чого немає в даних, — у квадратних дужках.
"""
import datetime
from collections import defaultdict

from . import compliance, gates, prioritize, tolerances as tl
from .trello import metrics
from .model import (PROCESSES, PROJECT_STATUS_NAMES, TARGETS, TARGET_NAMES, fmt_date,
                    fmt_money, parse_date, policy)


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _title(p):
    return f"{p['id']} {p.get('name', '')}".strip()


def assess(portfolio, project, boards, today):
    """Зводить усе, що PMO знає про проєкт, в один словник."""
    m = None
    board_name = project.get("trello_board")
    if board_name and board_name in boards:
        m = metrics(boards[board_name], today)
    results = tl.evaluate(project, portfolio, m)
    gate_name, gate_gaps = gates.check(project)
    return {
        "project": project,
        "metrics": m,
        "board_missing": bool(board_name) and board_name not in boards,
        "tolerances": results,
        "overall": tl.overall(results),
        "principles": compliance.check(project, today),
        "board_findings": compliance.board_findings(m),
        "gate": gate_name,
        "gate_gaps": gate_gaps,
    }


def _headline(a):
    p = a["project"]
    exc = [TARGET_NAMES[t].lower() for t in TARGETS if a["tolerances"][t][0] == tl.EXCEPTION]
    risk = [TARGET_NAMES[t].lower() for t in TARGETS if a["tolerances"][t][0] == tl.AT_RISK]
    parts = []
    if exc:
        parts.append("виняток за показником " + ", ".join(exc))
    elif risk:
        parts.append("під загрозою " + ", ".join(risk))
    else:
        nodata = sum(1 for t in TARGETS if a["tolerances"][t][0] == tl.NO_DATA)
        parts.append(f"у межах допусків за наявними даними, без даних {nodata} з 7 показників")
    if a["gate"]:
        n = len(a["gate_gaps"])
        parts.append(f"межа «{a['gate']}» " + ("готова" if not n else
                                                f"не готова, бракує {n} {_plural(n, 'умови', 'умов', 'умов')}"))
    return f"{_title(p)}: " + "; ".join(parts)


def decisions(assessments, portfolio, today):
    """Рішення, потрібні від керівництва: дія, власник, строк."""
    days = policy(portfolio)["decision_days"]
    due = today + datetime.timedelta(days=days)
    out = []
    for a in assessments:
        p = a["project"]
        owner = (p.get("board") or {}).get("executive") or "Голова Ради проєкту [не призначено]"
        pm = (p.get("board") or {}).get("project_manager") or "Керівник проєкту [не призначено]"
        exc = [t for t in TARGETS if a["tolerances"][t][0] == tl.EXCEPTION]
        if exc:
            out.append(f"{pm}: до {fmt_date(due)} подати Голові Ради звіт про виняток по {p['id']} "
                       f"(показники: {', '.join(TARGET_NAMES[t].lower() for t in exc)}); "
                       f"{owner}: ухвалити рішення протягом {days} днів після отримання.")
        boundary = parse_date((p.get("stage") or {}).get("boundary_date"))
        if boundary and a["gate_gaps"] and (boundary - today).days <= 30:
            out.append(f"{pm}: до {fmt_date(boundary)} закрити {len(a['gate_gaps'])} умов межі "
                       f"«{a['gate']}» по {p['id']}, інакше Голові Ради не буде на чому ухвалювати рішення.")
        if not (p.get("tolerances") or {}):
            out.append(f"{owner}: до {fmt_date(due)} затвердити допуски проєкту {p['id']} "
                       f"(пропозиція: references/02-model-pmo.md, розділ «Допуски за замовчуванням»).")
    return out


def dashboard(portfolio, boards, today):
    meta = portfolio.get("portfolio") or {}
    active = [p for p in portfolio["projects"] if p.get("status", "active") in ("active", "on_hold")]
    pipeline = [p for p in portfolio["projects"] if p.get("status") == "pipeline"]
    assessments = [assess(portfolio, p, boards, today) for p in active]
    n_exc = sum(1 for a in assessments if a["overall"] == tl.EXCEPTION)
    n_risk = sum(1 for a in assessments if a["overall"] == tl.AT_RISK)
    n_trello = sum(1 for a in assessments if a["metrics"])

    L = [f"# {meta.get('name', 'Портфель')}: огляд станом на {fmt_date(today)}", ""]
    L.append(f"З {len(active)} {_plural(len(active), 'активного проєкту', 'активних проєктів', 'активних проєктів')} "
             f"у винятку {n_exc}, під загрозою {n_risk}; ще {len(pipeline)} у черзі на запуск. "
             f"Дані Trello підключено для {n_trello} з {len(active)}, решта оцінена лише за реєстром портфеля, "
             f"тому картина неповна саме там, де немає дошки.")
    L.append("")

    dec = decisions(assessments, portfolio, today)
    L.append(f"## Потрібно {len(dec)} {_plural(len(dec), 'рішення', 'рішення', 'рішень')} керівництва" if dec
             else "## Рішень керівництва цього разу не потрібно")
    L.append("")
    for d in dec:
        L.append(f"- {d}")
    L.append("")

    L.append("## Зведення за сімома показниками PRINCE2 7")
    L.append("")
    L.append("| Проєкт | Процес | " + " | ".join(TARGET_NAMES[t] for t in TARGETS) + " | Наступна межа |")
    L.append("| --- | --- | " + " | ".join("---" for _ in TARGETS) + " | --- |")
    for a in assessments:
        p = a["project"]
        st = p.get("stage") or {}
        cells = [tl.SHORT[a["tolerances"][t][0]] for t in TARGETS]
        L.append(f"| {p['id']} | {PROCESSES.get(st.get('process'), '[не визначено]')} | "
                 + " | ".join(cells) + f" | {fmt_date(parse_date(st.get('boundary_date')))} |")
    L.append("")
    L.append("«Загроза» означає прогноз від 80 % допуску, «виняток» означає прогноз за межею допуску, "
             "прочерк означає, що даних для оцінки немає.")
    L.append("")

    for a in sorted(assessments, key=lambda a: [tl.EXCEPTION, tl.AT_RISK, tl.WITHIN, tl.NO_DATA].index(a["overall"])):
        L += project_block(a)

    groups = defaultdict(list)
    for p in active + pipeline:
        if p.get("programme"):
            groups[p["programme"]].append(p)
    for prog, ps in groups.items():
        with_budget = [p for p in ps if (p.get("budget") or {}).get("baseline") is not None]
        L.append(f"## Програма {prog}: бюджет відомий для {len(with_budget)} з {len(ps)} проєктів, "
                 f"тому суму по програмі не наведено")
        L.append("")
        for p in ps:
            b = p.get("budget") or {}
            L.append(f"- {p['id']}: {PROJECT_STATUS_NAMES[p.get('status', 'active')]}, базова лінія {fmt_money(b.get('baseline'))}"
                     + (f", резерв {fmt_money(b.get('contingency'))}" if b.get("contingency") is not None else ""))
        L.append("")

    crit = meta.get("criteria") or []
    if crit:
        ranked = prioritize.rank(active + pipeline, crit)
        if all(r["score"] is None for r in ranked):
            L.append("## Рейтинг портфеля не пораховано: оцінок за критеріями не внесено")
            L.append("")
            L.append("Оцінки 0..5 за кожним критерієм ставить Голова Ради або робоча група; "
                     "PMO їх не вигадує. Поле scores у портфелі.")
            L.append("")
            ranked = []
        else:
            L.append("## Рейтинг портфеля за зваженими критеріями")
            L.append("")
        if ranked:
            L.append("Ваги: " + "; ".join(f"{c.get('name', c['key'])} {round(c['weight'] * 100)} %" for c in crit) + ".")
            L.append("")
        for i, r in enumerate(ranked, 1):
            if r["score"] is None:
                L.append(f"{i}. {r['id']}: оцінку не пораховано, бракує критеріїв {', '.join(r['missing'])}")
            else:
                L.append(f"{i}. {r['id']}: {r['score']} з 100")
        L.append("")

    gaps = [(p["id"], g) for p in active + pipeline for g in p.get("gaps") or []]
    if gaps:
        L.append(f"## Прогалини в даних: {len(gaps)}")
        L.append("")
        for pid, g in gaps:
            L.append(f"- {pid}: {g}")
        L.append("")
    return "\n".join(L)


def project_block(a):
    p, m = a["project"], a["metrics"]
    L = [f"## {_headline(a)}", ""]
    st = p.get("stage") or {}
    facts = [f"Процес: {PROCESSES.get(st.get('process'), '[не визначено]')}"
             + (f", {st['name']}" if st.get("name") else "")]
    if p.get("executing_agent"):
        facts.append(f"Виконавчий Агент: {p['executing_agent']}")
    L.append(". ".join(facts) + ".")
    L.append("")
    for t in TARGETS:
        state, why = a["tolerances"][t]
        if state in (tl.EXCEPTION, tl.AT_RISK):
            L.append(f"{TARGET_NAMES[t]}, {state}: {why.rstrip('.')}.")
            L.append("")
    if m:
        L.append(f"Реєстр Trello «{m['board']}»: {m['cards']} робіт, виконано {m['done']}, "
                 f"прострочено {m['overdue']}, з них контрольних подій {len(m['milestones_overdue'])}; "
                 f"у зоні Виконавчого Агента відкрито {m['ea_zone_open']}.")
        L.append("")
        if m["upcoming_milestones"]:
            L.append("Контрольні події на 30 днів: " + "; ".join(
                f"[{u['wbs']}] {fmt_date(u['due'])}" for u in m["upcoming_milestones"]) + ".")
            L.append("")
        if m["owner_load"]:
            top = list(m["owner_load"].items())[:3]
            L.append("Найбільше навантаження на 30 днів: " + "; ".join(f"{o} {n}" for o, n in top) + ".")
            L.append("")
    elif a["board_missing"]:
        L.append(f"Дошку «{p['trello_board']}» вказано в портфелі, але її дамп не передано.")
        L.append("")
    if a["board_findings"]:
        L.append("Дефекти реєстру, що спотворюють картину:")
        L.append("")
        for f in a["board_findings"]:
            L.append(f"- {f}")
        L.append("")
    bad = [(n, w) for n, ok, w in a["principles"] if ok is False]
    unk = [(n, w) for n, ok, w in a["principles"] if ok is None]
    L.append(f"Принципи PRINCE2: дотримано {7 - len(bad) - len(unk)} з 7, порушено {len(bad)}, "
             f"без даних {len(unk)}.")
    L.append("")
    for n, w in bad:
        L.append(f"- {n}: {w}")
    if bad:
        L.append("")
    if a["gate"] and a["gate_gaps"]:
        L.append(f"Межа «{a['gate']}»: бракує {len(a['gate_gaps'])}.")
        L.append("")
        for g in a["gate_gaps"]:
            L.append(f"- {g}")
        L.append("")
    return L


def gate_report(portfolio, project, boards, today):
    a = assess(portfolio, project, boards, today)
    if not a["gate"]:
        return f"# {_title(project)}: процес не визначено, межу етапу перевірити неможливо\n"
    ready = not a["gate_gaps"]
    L = [f"# {_title(project)}: межу «{a['gate']}» " + ("можна проходити" if ready else
         f"проходити не можна, бракує {len(a['gate_gaps'])} умов"), ""]
    L.append(f"Перевірено {fmt_date(today)} за комплектом із references/03-produkty.md.")
    L.append("")
    if not ready:
        L.append("## Що закрити до подання на Раду")
        L.append("")
        for g in a["gate_gaps"]:
            L.append(f"- {g}")
        L.append("")
    exc = [t for t in TARGETS if a["tolerances"][t][0] == tl.EXCEPTION]
    if exc:
        L.append("## Межу поєднати з розглядом винятку")
        L.append("")
        L.append("Прогноз уже за межею допуску, тому на Раду йде не звіт про завершення етапу, "
                 "а план винятку (процес Управління межею етапу).")
        L.append("")
    L.append("## Стан принципів")
    L.append("")
    for n, ok, w in a["principles"]:
        mark = {True: "дотримано", False: "порушено", None: "без даних"}[ok]
        L.append(f"- {n}: {mark}; {w}")
    return "\n".join(L) + "\n"


def exception_report(portfolio, project, boards, today):
    """Чернетка звіту про виняток за складом PRINCE2: назва, причина,
    наслідки, варіанти, рекомендація, уроки. Варіанти й рекомендацію
    формулює Керівник проєкту, PMO лише готує каркас і факти."""
    a = assess(portfolio, project, boards, today)
    exc = [t for t in TARGETS if a["tolerances"][t][0] == tl.EXCEPTION]
    risk = [t for t in TARGETS if a["tolerances"][t][0] == tl.AT_RISK]
    if not exc and not risk:
        return (f"# {_title(project)}: звіт про виняток не потрібен\n\nЖоден із семи показників "
                f"станом на {fmt_date(today)} не наблизився до межі допуску.\n")
    board = project.get("board") or {}
    head = "виняток" if exc else "попередження про можливий виняток"
    L = [f"# Звіт про виняток: {_title(project)}, {head} за показником "
         + ", ".join(TARGET_NAMES[t].lower() for t in (exc or risk)), ""]
    L.append(f"Дата: {fmt_date(today)}. Від: {board.get('project_manager') or '[Керівник проєкту]'}. "
             f"Кому: {board.get('executive') or '[Голова Ради проєкту]'}.")
    L.append("")
    L.append("## Причина відхилення")
    L.append("")
    for t in exc + risk:
        L.append(f"{TARGET_NAMES[t]}: {a['tolerances'][t][1].rstrip('.')}.")
        L.append("")
    m = a["metrics"]
    if m and m["milestones_overdue"]:
        L.append("Прострочені контрольні події:")
        L.append("")
        for x in m["milestones_overdue"]:
            zone = ", зона Виконавчого Агента" if x["ea_zone"] else ""
            L.append(f"- [{x['wbs']}] строк {fmt_date(x['due'])}, зсув {x['slip']} дн., власник {x['owner']}{zone}")
        L.append("")
    L.append("## Наслідки")
    L.append("")
    L.append("[Керівник проєкту: які наступні роботи і контрольні події зсуваються, на скільки днів, "
             "чи зачеплено строк Листа-доручення і графік траншів.]")
    L.append("")
    L.append("## Варіанти")
    L.append("")
    L.append("| Варіант | Вплив на час | Вплив на вартість | Вплив на ризик | Хто ухвалює |")
    L.append("| --- | --- | --- | --- | --- |")
    L.append("| Прийняти відхилення і перезатвердити базову лінію | [дн.] | [євро] | [опис] | Голова Ради |")
    L.append("| Надолужити за рахунок паралельних робіт | [дн.] | [євро] | [опис] | Керівник проєкту в межах допуску етапу |")
    L.append("| Ескалувати Виконавчому Агенту або НАТО | [дн.] | [євро] | [опис] | Голова Ради, далі Командувач |")
    L.append("")
    L.append("## Рекомендація")
    L.append("")
    L.append("[Один варіант, власник і дата рішення.]")
    L.append("")
    L.append("## Уроки")
    L.append("")
    L.append("[Що в плануванні чи контролі дозволило відхиленню вийти за допуск непоміченим; запис у журнал уроків.]")
    return "\n".join(L) + "\n"


def funding_report(scenario):
    res = prioritize.fund(scenario)
    flips = prioritize.sensitivity(scenario)
    cur = scenario.get("currency", "євро")
    deficit = res["need"] - res["budget"]
    L = [f"# {scenario.get('name', 'Сценарій фінансування')}: у межах {fmt_money(res['budget'], cur)} "
         f"вміщується {len(res['funded'])} з {len(res['funded']) + len(res['unfunded'])} позицій", ""]
    L.append(f"Потреба {fmt_money(res['need'], cur)}, наявно {fmt_money(res['budget'], cur)}, "
             f"дефіцит {fmt_money(max(deficit, 0), cur)}. Відібрано на {fmt_money(res['spent'], cur)}, "
             f"невикористаний залишок {fmt_money(res['budget'] - res['spent'], cur)}.")
    L.append("")
    for n in res["notes"]:
        L.append(n + ".")
        L.append("")
    L.append("## Перша черга")
    L.append("")
    for i in res["funded"]:
        tag = ", обов'язкова" if i.get("mandatory") else ""
        L.append(f"- {i['id']} {i['name']}: {fmt_money(i['cost'], cur)}, оцінка {i['_score']}{tag}")
    L.append("")
    L.append("## Друга черга")
    L.append("")
    for i in res["unfunded"]:
        why = ", не вмістилася в залишок разом із попередниками" if i["id"] in res["skipped"] else ""
        L.append(f"- {i['id']} {i['name']}: {fmt_money(i['cost'], cur)}, оцінка {i['_score']}{why}")
    L.append("")
    L.append("## Чутливість до ваг")
    L.append("")
    if flips:
        L.append("Відбір нестійкий щодо цих позицій: зміна ваги одного критерію на 20 % переводить їх у іншу чергу.")
        L.append("")
        for k, v in flips.items():
            L.append(f"- {k}: {', '.join(v)}")
    else:
        L.append("Зміна ваги будь-якого критерію на 20 % не змінює складу першої черги.")
    return "\n".join(L) + "\n"
