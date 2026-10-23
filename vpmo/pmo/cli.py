"""Командний рядок віртуального PMO.

    python3 -m pmo check     <портфель.json>
    python3 -m pmo dashboard <портфель.json> [--trello дамп1.json ...] [--as-of ДД.ММ.РРРР] [--out файл.md]
    python3 -m pmo gate      <портфель.json> <id проєкту> [--trello ...] [--out ...]
    python3 -m pmo exception <портфель.json> <id проєкту> [--trello ...] [--out ...]
    python3 -m pmo fund      <сценарій.json> [--out ...]
    python3 -m pmo trello    <дамп1.json> [...] [--as-of ...]

Запускати з теки vpmo.
"""
import argparse
import json
import sys

from . import compliance, model, prioritize, report, trello


def _emit(text, out):
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Записано: {out}")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _project(portfolio, pid):
    for p in portfolio["projects"]:
        if p["id"] == pid:
            return p
    raise SystemExit(f"Проєкту '{pid}' у портфелі немає. Є: " + ", ".join(p["id"] for p in portfolio["projects"]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pmo", description="Віртуальний PMO за PRINCE2 7")
    ap.add_argument("command", choices=["check", "dashboard", "gate", "exception", "fund", "trello"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--trello", nargs="*", default=[], help="дампи дошок Trello (JSON)")
    ap.add_argument("--as-of", help="дата зрізу, за замовчуванням із портфеля або сьогодні")
    ap.add_argument("--out", help="файл для звіту; без нього друк у консоль")
    a = ap.parse_args(argv)

    if a.command == "fund":
        with open(a.files[0], encoding="utf-8") as f:
            scenario = json.load(f)
        _emit(report.funding_report(scenario), a.out)
        return

    if a.command == "trello":
        today = model.parse_date(a.as_of) or model.as_of({}, None)
        for name, rows in trello.load_boards(a.files).items():
            m = trello.metrics(rows, today)
            print(f"{name}: робіт {m['cards']}, виконано {m['done']}, прострочено {m['overdue']}, "
                  f"контрольних подій {m['milestones']}, найбільший зсув контрольної події {m['max_milestone_slip']} дн.")
            for f in compliance.board_findings(m):
                print(f"  {f}")
        return

    portfolio = model.load(a.files[0])
    today = model.as_of(portfolio, a.as_of)
    boards = trello.load_boards(a.trello) if a.trello else {}

    if a.command == "check":
        print(f"Структура файлу коректна: {len(portfolio['projects'])} проєктів.")
        for p in portfolio["projects"]:
            bad = [(n, w) for n, ok, w in compliance.check(p, today) if ok is False]
            print(f"{p['id']}: порушено принципів {len(bad)} з 7")
            for n, w in bad:
                print(f"  {n}: {w}")
        return
    if a.command == "dashboard":
        _emit(report.dashboard(portfolio, boards, today), a.out)
        return
    if len(a.files) < 2:
        raise SystemExit("Вкажіть id проєкту другим аргументом")
    p = _project(portfolio, a.files[1])
    if a.command == "gate":
        _emit(report.gate_report(portfolio, p, boards, today), a.out)
    elif a.command == "exception":
        _emit(report.exception_report(portfolio, p, boards, today), a.out)


if __name__ == "__main__":
    main()
