"""Оцінка семи цільових показників PRINCE2 7 проти допусків.

Стан показника — одне з чотирьох значень. Кольорів немає навмисно: виняток
визначає число, а не колір.
"""
from .model import TARGETS, fmt_money, parse_date, policy

WITHIN = "у межах допуску"
AT_RISK = "під загрозою"
EXCEPTION = "виняток"
NO_DATA = "немає даних"
SHORT = {WITHIN: "у межах", AT_RISK: "загроза", EXCEPTION: "виняток", NO_DATA: "—"}


def _grade(value, limit, warn_ratio):
    if value > limit:
        return EXCEPTION
    if value >= warn_ratio * limit:
        return AT_RISK
    return WITHIN


def _time(p, pol, m):
    tol = (p.get("tolerances") or {}).get("time_days", pol["time_days"])
    manual = (p.get("progress") or {}).get("time_slip_days")
    if manual is not None:
        return _grade(manual, tol, pol["warn_ratio"]), \
            f"зсув {manual} дн. за даними {p['progress'].get('source', '[джерело не вказано]')}, допуск {tol} дн."
    if not m:
        return NO_DATA, "дошку Trello не підключено і зсув не внесено вручну"
    end_tol = (p.get("tolerances") or {}).get("end_date_days", pol["end_date_days"])
    # Trello дає кінець останньої фази (Завершення), тому порівнюємо з датою закриття
    dates = p.get("dates") or {}
    planned_end = parse_date(dates.get("closure") or dates.get("planned_end"))
    end_note, end_state = "", WITHIN
    if planned_end and m["planned_end"] and m["planned_end"] > planned_end:
        end_slip = (m["planned_end"] - planned_end).days
        end_state = _grade(end_slip, end_tol, pol["warn_ratio"])
        end_note = (f"; кінцева дата за Trello {m['planned_end']:%d.%m.%Y} пізніша за базову "
                    f"{planned_end:%d.%m.%Y} на {end_slip} дн., допуск {end_tol} дн.")
    if not m["milestones_overdue"]:
        return end_state, f"прострочених контрольних подій немає, допуск {tol} дн.{end_note}"
    slip = m["max_milestone_slip"]
    top = m["milestones_overdue"][0]
    ms_state = _grade(slip, tol, pol["warn_ratio"])
    state = next(s for s in (EXCEPTION, AT_RISK, WITHIN) if s in (ms_state, end_state))
    return state, (
        f"контрольна подія [{top['wbs']}] прострочена на {slip} дн. (строк {top['due']:%d.%m.%Y}), "
        f"допуск {tol} дн.; це нижня оцінка зсуву, бо подія ще не настала{end_note}")


def _cost(p, pol, m):
    b = p.get("budget") or {}
    base, forecast = b.get("baseline"), b.get("forecast")
    tol = (p.get("tolerances") or {}).get("cost_eur", b.get("contingency"))
    if base is None or forecast is None:
        return NO_DATA, "немає базової лінії або прогнозу вартості при завершенні"
    if tol is None:
        return NO_DATA, "не задано допуск вартості і резерв"
    over = forecast - base
    return _grade(over, tol, pol["warn_ratio"]) if over > 0 else WITHIN, (
        f"прогноз {fmt_money(forecast)} проти базової лінії {fmt_money(base)}, "
        f"відхилення {fmt_money(over)}, допуск {fmt_money(tol)}")


def _scope(p, pol, m):
    items = p.get("scope_items") or []
    if not items:
        return NO_DATA, "перелік обсягу з пріоритетами не внесено"
    dropped_must = [i["name"] for i in items if i.get("dropped") and i.get("priority") == "must"]
    dropped_should = [i["name"] for i in items if i.get("dropped") and i.get("priority") == "should"]
    if dropped_must:
        return EXCEPTION, "вилучено обов'язкове: " + "; ".join(dropped_must)
    if dropped_should:
        return AT_RISK, "вилучено бажане: " + "; ".join(dropped_should)
    return WITHIN, f"усі {len(items)} позицій обсягу на місці"


def _quality(p, pol, m):
    q = p.get("quality")
    if not q:
        return NO_DATA, "реєстр якості не ведеться"
    if q.get("rejected_products", 0) > 0:
        return EXCEPTION, f"не прийнято продуктів: {q['rejected_products']}"
    if q.get("repeat_failures", 0) > 0:
        return AT_RISK, f"повторно не пройшли перевірку якості: {q['repeat_failures']}"
    return WITHIN, "відхилень якості не зафіксовано"


def _benefits(p, pol, m):
    rows = [b for b in p.get("benefits") or [] if b.get("planned") and b.get("forecast") is not None]
    if not rows:
        return NO_DATA, "вигоди з планом і прогнозом не внесено"
    worst = max(rows, key=lambda b: (b["planned"] - b["forecast"]) / b["planned"])
    gap = round(100 * (worst["planned"] - worst["forecast"]) / worst["planned"], 1)
    lim = pol["benefits_pct"]
    status = EXCEPTION if gap > lim["exception"] else AT_RISK if gap >= lim["warn"] else WITHIN
    return status, f"«{worst['name']}»: прогноз нижчий за план на {gap} %"


def _risk(p, pol, m):
    risks = [r for r in p.get("risks") or [] if r.get("status", "open") == "open"]
    if not risks:
        return NO_DATA, "реєстр ризиків порожній"
    lim = pol["risk_score"]
    scored = sorted(risks, key=lambda r: -(r.get("probability", 0) * r.get("impact", 0)))
    top = scored[0]
    score = top.get("probability", 0) * top.get("impact", 0)
    no_response = not (top.get("response") or "").strip()
    if score >= lim["exception"] and no_response:
        status = EXCEPTION
    elif score >= lim["warn"]:
        status = AT_RISK
    else:
        status = WITHIN
    tail = ", відповіді немає" if no_response else ""
    return status, f"найвищий ризик «{top.get('title')}» має оцінку {score} з 25{tail}"


def _sustainability(p, pol, m):
    s = (p.get("tolerances") or {}).get("sustainability")
    if not s:
        return NO_DATA, "метрику сталого розвитку не визначено в бізнес-кейсі"
    actual = (p.get("progress") or {}).get("sustainability")
    if actual is None:
        return NO_DATA, f"допуск «{s}» задано, факту немає"
    return (EXCEPTION if actual.get("breach") else WITHIN), actual.get("note", "")


CHECKS = {"time": _time, "cost": _cost, "scope": _scope, "quality": _quality,
          "benefits": _benefits, "risk": _risk, "sustainability": _sustainability}


def evaluate(project, portfolio, trello_metrics=None):
    """{показник: (стан, пояснення)} для всіх семи показників."""
    pol = policy(portfolio)
    return {t: CHECKS[t](project, pol, trello_metrics) for t in TARGETS}


def overall(results):
    states = [s for s, _ in results.values()]
    for s in (EXCEPTION, AT_RISK, WITHIN):
        if s in states:
            return s
    return NO_DATA
