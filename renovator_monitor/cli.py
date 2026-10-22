"""Командний рядок: python -m renovator_monitor <команда>."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from . import config as config_mod
from . import pipeline, report
from .registry import STATUSES, Registry, effective_status, locked
from .sources import COLLECTORS


def _print_result(res: pipeline.RunResult) -> None:
    print(f"Отримано знахідок: {res.fetched} ({', '.join(f'{k}: {v}' for k, v in res.per_source.items()) or 'жодного джерела'})")
    print(f"Нових записів: {res.new}; з них релевантних: {res.new_relevant}, на перевірку: {res.new_uncertain}")
    print(f"Перевірено сторінок: {res.verified}; класифіковано моделлю: {res.classified}; надіслано сповіщень: {res.notified}")
    if res.errors:
        print(f"Помилки ({len(res.errors)}):")
        for e in res.errors:
            print(f"  {e}")


def cmd_run(args, cfg) -> int:
    res = pipeline.run(cfg, only=args.only, backfill=args.backfill, notify_enabled=not args.silent)
    _print_result(res)
    # Код 2: прогін відбувся, але жодне джерело не відповіло. Це варто помітити в CI.
    return 2 if res.fetched == 0 and res.errors else 0


def cmd_watch(args, cfg) -> int:
    log = logging.getLogger("watch")
    while True:
        try:
            _print_result(pipeline.run(cfg, only=args.only))
        except Exception:
            log.exception("прогін завершився помилкою; наступна спроба за розкладом")
        time.sleep(max(300, args.interval))


def cmd_review(args, cfg) -> int:
    path = cfg["storage"]["registry"]
    with locked(path):
        reg = Registry(path)
        status = None if args.status == "auto" else args.status
        rec = reg.set_manual(args.id, status, args.note)
        reg.save()
        pipeline.export(reg, cfg)
    print(f"{rec['id']}: {report.STATUS_UK[effective_status(rec)]} ({report.status_by(rec)}) {rec['title']}")
    return 0


def cmd_list(args, cfg) -> int:
    reg = Registry(cfg["storage"]["registry"])
    rows = [r for r in reg.all() if args.status == "all" or effective_status(r) == args.status]
    rows.sort(key=report.sort_key, reverse=True)
    for r in rows[: args.limit]:
        date = (r.get("published_at") or r["first_seen_at"])[:10]
        print(f"{r['id']}  {date}  {r.get('score', ''):>3}  {effective_status(r):<10}  "
              f"{(r.get('source_name') or r.get('domain') or '')[:24]:<24}  {r['title'][:90]}")
        if args.urls:
            print(f"              {r['url']}")
    return 0


def cmd_stats(args, cfg) -> int:
    reg = Registry(cfg["storage"]["registry"])
    recs = reg.all()
    st = Counter(effective_status(r) for r in recs)
    rel = [r for r in recs if effective_status(r) == "relevant"]
    print(f"Записів: {len(recs)}; " + ", ".join(f"{report.STATUS_UK[s]}: {st[s]}" for s in STATUSES))
    for title, counter in (
        ("Релевантні за мовою", Counter(r.get("language") or "?" for r in rel)),
        ("Релевантні за місяцем публікації", Counter((r.get("published_at") or r["first_seen_at"])[:7] for r in rel)),
        ("Найчастіші джерела", Counter(r.get("domain") or "?" for r in rel)),
        ("Через яке джерело знайдено (усі записи)",
         Counter(src for r in recs for src in {v.split(":", 1)[0] for v in r["found_via"]})),
    ):
        print(f"\n{title}:")
        items = sorted(counter.items(), reverse=True) if "місяцем" in title else counter.most_common(15)
        for k, v in items:
            print(f"  {k}: {v}")
    return 0


def cmd_digest(args, cfg) -> int:
    reg = Registry(cfg["storage"]["registry"])
    text = report.digest_markdown(reg.all(), args.days)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Записано {args.output}")
    else:
        print(text)
    return 0


def cmd_export(args, cfg) -> int:
    reg = Registry(cfg["storage"]["registry"])
    pipeline.export(reg, cfg)
    print(f"Оновлено {cfg['storage']['export_dir']}/registry.csv та index.html")
    return 0


def cmd_rescore(args, cfg) -> int:
    """Переоцінити всі записи після зміни правил релевантності."""
    path = cfg["storage"]["registry"]
    with locked(path):
        reg = Registry(path)
        before = Counter(effective_status(r) for r in reg.all())
        for r in reg.all():
            reg.rescore(r)
        after = Counter(effective_status(r) for r in reg.all())
        reg.save()
        pipeline.export(reg, cfg)
    print("Було: " + ", ".join(f"{s}: {before[s]}" for s in STATUSES))
    print("Стало: " + ", ".join(f"{s}: {after[s]}" for s in STATUSES))
    return 0


def cmd_doctor(args, cfg) -> int:
    """Перевіряє кожне джерело окремо, нічого не записуючи в реєстр."""
    client = pipeline.make_client(cfg)
    failed = 0
    for name, collect in COLLECTORS.items():
        scfg = cfg.get("sources", {}).get(name, {})
        if not scfg.get("enabled"):
            print(f"{name:<12} вимкнено")
            continue
        if name == "telegram" and not scfg.get("channels"):
            print(f"{name:<12} не налаштовано: список channels порожній")
            continue
        errors: list[str] = []
        try:
            found = collect(client, scfg, {"errors": errors, "backfill": True})
        except Exception as e:
            print(f"{name:<12} ЗБІЙ: {type(e).__name__}: {e}")
            failed += 1
            continue
        state = "ок" if not errors else ("частково" if found else "ЗБІЙ")
        failed += state == "ЗБІЙ"
        print(f"{name:<12} {state}: знахідок {len(found)}, помилок {len(errors)}")
        for e in errors[: args.max_errors]:
            print(f"             {e}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="renovator_monitor",
                                description="Моніторинг згадувань проєкту НАТО «Реноватор» в інтернеті")
    p.add_argument("--config", help="TOML-файл, що накладається на типову конфігурацію")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="один прогін збору")
    r.add_argument("--only", nargs="+", choices=list(COLLECTORS), help="лише ці джерела")
    r.add_argument("--backfill", action="store_true", help="шукати на максимальну глибину (перше наповнення)")
    r.add_argument("--silent", action="store_true",
                   help="не надсилати сповіщень і позначити все наявне як надіслане")
    r.set_defaults(func=cmd_run)

    w = sub.add_parser("watch", help="прогони в нескінченному циклі")
    w.add_argument("--interval", type=int, default=3600, help="секунд між прогонами (мінімум 300)")
    w.add_argument("--only", nargs="+", choices=list(COLLECTORS))
    w.set_defaults(func=cmd_watch)

    v = sub.add_parser("review", help="ручне рішення щодо запису")
    v.add_argument("id", help="ID запису або його унікальний початок")
    v.add_argument("status", choices=list(STATUSES) + ["auto"], help="auto знімає ручне рішення")
    v.add_argument("--note", help="примітка аналітика")
    v.set_defaults(func=cmd_review)

    ls = sub.add_parser("list", help="показати записи")
    ls.add_argument("--status", choices=list(STATUSES) + ["all"], default="uncertain")
    ls.add_argument("--limit", type=int, default=50)
    ls.add_argument("--urls", action="store_true")
    ls.set_defaults(func=cmd_list)

    sub.add_parser("stats", help="зведена статистика").set_defaults(func=cmd_stats)

    d = sub.add_parser("digest", help="Markdown-дайджест нових згадувань")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--output")
    d.set_defaults(func=cmd_digest)

    sub.add_parser("export", help="перегенерувати CSV і HTML").set_defaults(func=cmd_export)
    sub.add_parser("rescore", help="переоцінити реєстр після зміни правил").set_defaults(func=cmd_rescore)

    dr = sub.add_parser("doctor", help="перевірити доступність і формат кожного джерела")
    dr.add_argument("--max-errors", type=int, default=5)
    dr.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config_mod.load(args.config)
    try:
        return args.func(args, cfg)
    except (KeyError, ValueError, RuntimeError) as e:
        print(f"Помилка: {e}", file=sys.stderr)
        return 1
