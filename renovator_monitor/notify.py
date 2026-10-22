"""Сповіщення в Telegram про нові згадування через Bot API (без сторонніх бібліотек).

Потрібні змінні середовища RENOVATOR_TG_TOKEN і RENOVATOR_TG_CHAT_ID.
Запис позначається як надісланий лише після успішної відповіді API,
тож збій мережі не загубить сповіщення: воно піде наступним прогоном.
"""

from __future__ import annotations

import html
import json
import logging
import os
import urllib.parse
import urllib.request

from .registry import effective_status
from .report import STATUS_UK

log = logging.getLogger(__name__)
LIMIT = 3900  # запас до межі Telegram у 4096 символів


def _format(rec: dict) -> str:
    e = html.escape
    date = (rec.get("published_at") or rec["first_seen_at"])[:10]
    src = rec.get("source_name") or rec.get("domain") or ""
    st = STATUS_UK[effective_status(rec)]
    summary = (rec.get("llm") or {}).get("summary_uk")
    line = (f'<b>{e(date)}</b>, {e(src)}\n<a href="{e(rec["url"], quote=True)}">'
            f'{e(rec.get("title") or rec["url"])}</a>\n<i>{e(st)}</i>, оцінка {rec.get("score")}, '
            f'<code>{e(rec["id"])}</code>')
    if summary:
        line += f"\n{e(summary)}"
    return line


def send_telegram(text: str, token: str, chat_id: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram відхилив повідомлення: {payload.get('description')}")


def notify_new(records: list[dict], include_uncertain: bool, errors: list[str]) -> int:
    token = os.environ.get("RENOVATOR_TG_TOKEN")
    chat_id = os.environ.get("RENOVATOR_TG_CHAT_ID")
    wanted = {"relevant", "uncertain"} if include_uncertain else {"relevant"}
    pending = [r for r in records if not r.get("notified") and effective_status(r) in wanted]
    if not pending:
        return 0
    if not token or not chat_id:
        log.info("Telegram не налаштовано; %d записів чекають на сповіщення", len(pending))
        return 0
    pending.sort(key=lambda r: r.get("published_at") or r["first_seen_at"])
    header = f"Нові згадування «Реноватор»: {len(pending)}"
    sent = 0
    # Шлемо порціями і позначаємо надісланим лише те, що пішло.
    batch: list[dict] = []
    size = len(header)
    for rec in pending + [None]:
        part = _format(rec) if rec else ""
        if rec is None or (batch and size + len(part) + 2 > LIMIT):
            text = "\n\n".join(([header] if sent == 0 else []) + [_format(r) for r in batch])
            try:
                send_telegram(text, token, chat_id)
            except Exception as e:
                errors.append(f"Telegram: {e}")
                return sent
            for r in batch:
                r["notified"] = True
            sent += len(batch)
            batch, size = [], 0
        if rec is not None:
            batch.append(rec)
            size += len(part) + 2
    return sent
