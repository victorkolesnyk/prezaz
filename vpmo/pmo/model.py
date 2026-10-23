"""Модель портфеля: завантаження, значення за замовчуванням, перевірка структури.

Портфель зберігається в JSON (див. data/pryklad_portfel.json). Рушій не
доповнює відсутні факти: чого немає у файлі, те лишається None і потрапляє
у звіт як прогалина.
"""
import datetime
import json

TARGETS = ["time", "cost", "scope", "quality", "benefits", "risk", "sustainability"]
TARGET_NAMES = {
    "time": "Час", "cost": "Вартість", "scope": "Обсяг", "quality": "Якість",
    "benefits": "Вигоди", "risk": "Ризик", "sustainability": "Сталий розвиток",
}

# Процес PRINCE2, у якому зараз перебуває проєкт
PROCESSES = {
    "SU": "Запуск проєкту",
    "IP": "Ініціювання проєкту",
    "delivery": "Етап виконання",
    "CP": "Закриття проєкту",
    "closed": "Закрито",
}
PROJECT_STATUSES = {"pipeline", "active", "on_hold", "closed"}
PRODUCT_STATUSES = {"missing", "draft", "approved", "maintained", "n/a"}
STATUS_NAMES = {"missing": "немає", "draft": "чернетка", "approved": "затверджено",
                "maintained": "ведеться", "n/a": "не застосовується"}
PROJECT_STATUS_NAMES = {"pipeline": "у черзі на запуск", "active": "виконується",
                        "on_hold": "призупинено", "closed": "закрито"}
BOARD_ROLES = {
    "executive": "Голова Ради проєкту (Executive)",
    "senior_user": "Старший користувач",
    "senior_supplier": "Старший постачальник",
    "project_manager": "Керівник проєкту",
}

# Ключ допуску в полі tolerances проєкту для кожного показника
TOLERANCE_KEYS = {"time": "time_days", "cost": "cost_eur"}


def has_tolerance(tolerances, target):
    return TOLERANCE_KEYS.get(target, target) in (tolerances or {})


DEFAULT_POLICY = {
    "warn_ratio": 0.8,
    "time_days": 30,
    "end_date_days": 60,
    "risk_score": {"warn": 15, "exception": 20},
    "benefits_pct": {"warn": 10, "exception": 25},
    "decision_days": 7,
}


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(d):
    return d.strftime("%d.%m.%Y") if d else "[дата не визначена]"


def fmt_money(value, currency="євро"):
    if value is None:
        return "[сума не визначена]"
    whole = f"{int(round(value)):,}".replace(",", " ")
    return f"{whole} {currency}"


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = validate(data)
    if errors:
        raise SystemExit("Помилки у файлі портфеля:\n  " + "\n  ".join(errors))
    return data


def policy(portfolio):
    merged = dict(DEFAULT_POLICY)
    merged.update((portfolio.get("portfolio") or {}).get("policy") or {})
    return merged


def as_of(portfolio, override=None):
    return parse_date(override) or parse_date((portfolio.get("portfolio") or {}).get("as_of")) \
        or datetime.date.today()


def validate(data):
    """Структурні помилки, через які рахувати не можна. Змістовні прогалини
    сюди не входять: їх показує compliance."""
    errors = []
    if not isinstance(data, dict) or "projects" not in data:
        return ["немає ключа 'projects'"]
    seen = set()
    for i, p in enumerate(data["projects"]):
        where = f"projects[{i}]"
        pid = p.get("id")
        if not pid:
            errors.append(f"{where}: немає 'id'")
        elif pid in seen:
            errors.append(f"{where}: повторний id '{pid}'")
        seen.add(pid)
        if p.get("status", "active") not in PROJECT_STATUSES:
            errors.append(f"{where}: невідомий status '{p.get('status')}'")
        process = (p.get("stage") or {}).get("process")
        if process and process not in PROCESSES:
            errors.append(f"{where}: невідомий stage.process '{process}'")
        for key, st in (p.get("products") or {}).items():
            if st not in PRODUCT_STATUSES:
                errors.append(f"{where}: продукт '{key}' має невідомий статус '{st}'")
        for r in p.get("risks") or []:
            for k in ("probability", "impact"):
                v = r.get(k)
                if v is not None and not (isinstance(v, int) and 1 <= v <= 5):
                    errors.append(f"{where}: ризик '{r.get('id')}' має {k}={v}, потрібно ціле 1..5")
        for k, v in (p.get("scores") or {}).items():
            if v is not None and not (isinstance(v, (int, float)) and 0 <= v <= 5):
                errors.append(f"{where}: оцінка '{k}'={v}, потрібно 0..5")
    weights = [c.get("weight", 0) for c in (data.get("portfolio") or {}).get("criteria") or []]
    if weights and abs(sum(weights) - 1) > 0.001:
        errors.append(f"portfolio.criteria: сума ваг {sum(weights):.3f}, має бути 1")
    return errors
