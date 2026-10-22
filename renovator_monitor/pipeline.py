"""Один прогін: збір, злиття в реєстр, перевірка сторінок, класифікація, сповіщення, вивантаження."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import llm, notify, report, verify
from .fetch import HttpClient
from .registry import Registry, effective_status, locked
from .sources import COLLECTORS
from .textutil import utcnow_iso

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    fetched: int = 0
    new: int = 0
    new_relevant: int = 0
    new_uncertain: int = 0
    verified: int = 0
    classified: int = 0
    notified: int = 0
    errors: list[str] = field(default_factory=list)
    per_source: dict[str, int] = field(default_factory=dict)


def make_client(cfg: dict) -> HttpClient:
    h = cfg.get("http", {})
    return HttpClient(
        user_agent=h.get("user_agent", "RenovatorMonitor/1.0"),
        timeout=float(h.get("timeout", 20)),
        retries=int(h.get("retries", 2)),
        min_interval={k: float(v) for k, v in h.get("min_interval", {}).items()},
        default_interval=float(h.get("default_interval", 1.0)),
    )


def export(reg: Registry, cfg: dict) -> None:
    out = Path(cfg["storage"]["export_dir"])
    # Позначка часу береться з даних, а не з годинника: незмінний реєстр дає незмінні файли.
    as_of = max((r["first_seen_at"] for r in reg.all()), default=utcnow_iso())
    report.write_csv(reg.all(), out / "registry.csv")
    report.write_html(reg.all(), out / "index.html", as_of.replace("T", " ").rstrip("Z"))


def run(cfg: dict, only: list[str] | None = None, backfill: bool = False,
        notify_enabled: bool = True, client: HttpClient | None = None) -> RunResult:
    res = RunResult()
    client = client or make_client(cfg)
    path = cfg["storage"]["registry"]
    with locked(path):
        reg = Registry(path)
        ctx = {"errors": res.errors, "backfill": backfill}
        new_ids: list[str] = []
        for name, collect in COLLECTORS.items():
            scfg = cfg.get("sources", {}).get(name, {})
            if not scfg.get("enabled") or (only and name not in only):
                continue
            try:
                found = collect(client, scfg, ctx)
            except Exception as e:  # дефект конектора не має зупиняти інші
                res.errors.append(f"{name}: {type(e).__name__}: {e}")
                continue
            res.per_source[name] = len(found)
            res.fetched += len(found)
            for m in found:
                if not m.url or not m.title:
                    continue
                rec, is_new = reg.upsert(m)
                if is_new:
                    new_ids.append(rec["id"])

        res.verified = verify.verify_pages(
            reg, client, int(cfg.get("verify", {}).get("max_pages_per_run", 30)), res.errors)
        res.classified = llm.classify(reg, cfg.get("llm", {}), res.errors)

        res.new = len(new_ids)
        for rid in new_ids:
            st = effective_status(reg.records[rid])
            res.new_relevant += st == "relevant"
            res.new_uncertain += st == "uncertain"

        if notify_enabled:
            res.notified = notify.notify_new(
                reg.all(), bool(cfg.get("notify", {}).get("include_uncertain")), res.errors)
        else:
            # Без сповіщень (напр. перше наповнення): позначаємо, щоб не засипати чат історією.
            for r in reg.all():
                r["notified"] = True
        reg.save()
        export(reg, cfg)
    return res
