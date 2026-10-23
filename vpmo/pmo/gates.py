"""Комплекти управлінських продуктів для меж етапів (процес Спрямування
проєкту). Склад і пояснення — references/03-produkty.md.
"""
from .model import BOARD_ROLES, STATUS_NAMES, TARGET_NAMES, TARGETS, has_tolerance, parse_date

PRODUCT_NAMES = {
    "mandate": "Мандат проєкту",
    "project_brief": "Бриф проєкту",
    "business_case": "Бізнес-кейс",
    "pid": "Документація ініціювання проєкту (PID)",
    "project_plan": "План проєкту",
    "stage_plan": "План етапу",
    "benefits_approach": "Підхід до управління вигодами",
    "risk_approach": "Підхід до управління ризиками",
    "issue_approach": "Підхід до управління проблемами і змінами",
    "quality_approach": "Підхід до управління якістю",
    "communication_approach": "Підхід до комунікацій",
    "commercial_approach": "Комерційний підхід",
    "digital_data_approach": "Підхід до цифрових засобів і даних",
    "sustainability_approach": "Підхід до сталого розвитку",
    "tailoring": "Положення про адаптацію",
    "product_descriptions": "Описи продуктів",
    "risk_register": "Реєстр ризиків",
    "issue_register": "Реєстр проблем",
    "quality_register": "Реєстр якості",
    "lessons_log": "Журнал уроків",
    "daily_log": "Щоденний журнал",
    "end_stage_report": "Звіт про завершення етапу",
    "end_project_report": "Звіт про завершення проєкту",
    "lessons_report": "Звіт про уроки",
    "acceptance": "Підтвердження приймання",
}
RECORDS = {"risk_register", "issue_register", "quality_register", "lessons_log", "daily_log", "acceptance"}

GATES = {
    "authorize_initiation": {
        "name": "Дозвіл на ініціювання",
        "products": ["mandate", "project_brief", "business_case", "stage_plan", "lessons_log"],
        "draft_ok": {"business_case"},
        "roles": ["executive", "project_manager"],
        "tolerances": False,
    },
    "authorize_project": {
        "name": "Дозвіл на проєкт",
        "products": ["pid", "business_case", "project_plan", "stage_plan", "benefits_approach",
                     "risk_approach", "issue_approach", "quality_approach", "communication_approach",
                     "commercial_approach", "digital_data_approach", "sustainability_approach",
                     "tailoring", "risk_register", "issue_register", "quality_register"],
        "draft_ok": set(),
        "roles": list(BOARD_ROLES),
        "tolerances": True,
    },
    "authorize_next_stage": {
        "name": "Дозвіл на наступний етап",
        "products": ["end_stage_report", "business_case", "stage_plan", "project_plan",
                     "risk_register", "issue_register", "lessons_log"],
        "draft_ok": set(),
        "roles": list(BOARD_ROLES),
        "tolerances": True,
        "business_case_review": True,
    },
    "authorize_closure": {
        "name": "Дозвіл на закриття",
        "products": ["end_project_report", "lessons_report", "acceptance", "benefits_approach"],
        "draft_ok": set(),
        "roles": ["executive", "project_manager"],
        "tolerances": False,
    },
}

NEXT_GATE = {"SU": "authorize_initiation", "IP": "authorize_project",
             "delivery": "authorize_next_stage", "CP": "authorize_closure"}


def gate_for(project):
    stage = project.get("stage") or {}
    if stage.get("process") == "delivery" and stage.get("final"):
        return "authorize_closure"
    return NEXT_GATE.get(stage.get("process"))


def _ok(key, status, draft_ok):
    if status == "n/a":
        return True
    if key in RECORDS:
        return status in ("maintained", "approved")
    return status == "approved" or (key in draft_ok and status == "draft")


def check(project, gate=None):
    """Повертає (назва межі, [невиконані умови]). Порожній перелік — межу можна проходити."""
    gate = gate or gate_for(project)
    if gate not in GATES:
        return None, []
    g = GATES[gate]
    products = project.get("products") or {}
    gaps = []
    for key in g["products"]:
        status = products.get(key, "missing")
        if not _ok(key, status, g["draft_ok"]):
            gaps.append(f"{PRODUCT_NAMES[key]}: {STATUS_NAMES[status]}")
        if status == "n/a" and not (project.get("tailoring_note") or "").strip():
            gaps.append(f"{PRODUCT_NAMES[key]} позначено як незастосовний без пояснення в tailoring_note")
    board = project.get("board") or {}
    for role in g["roles"]:
        if not (board.get(role) or "").strip():
            gaps.append(f"Не призначено: {BOARD_ROLES[role]}")
    if g["tolerances"]:
        tol = project.get("tolerances") or {}
        missing = [t for t in TARGETS if not has_tolerance(tol, t) and not _derivable(t, project)]
        if missing:
            gaps.append("Не задано допусків для показників: "
                        + ", ".join(TARGET_NAMES[t].lower() for t in missing))
    if g.get("business_case_review"):
        reviewed = parse_date(project.get("business_case_reviewed"))
        started = parse_date((project.get("stage") or {}).get("started"))
        if not reviewed:
            gaps.append("Немає дати останнього перегляду бізнес-кейсу")
        elif started and reviewed < started:
            gaps.append(f"Бізнес-кейс востаннє переглянуто {reviewed:%d.%m.%Y}, до початку поточного етапу")
    stage = project.get("stage") or {}
    if gate != "authorize_closure" and not stage.get("boundary_date"):
        gaps.append("Не визначено дату межі поточного етапу")
    return g["name"], gaps


def _derivable(target, project):
    # Допуск часу і вартості береться з політики портфеля та резерву
    if target == "time":
        return True
    if target == "cost":
        return (project.get("budget") or {}).get("contingency") is not None
    return False
