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
import time
import urllib.error
import urllib.parse
import urllib.request

from .registry import effective_status
from .report import STATUS_UK

log = logging.getLogger(__name__)
LIMIT = 3900  # запас до межі Telegram у 4096 символів


class Rejected(Exception):
    """Telegram відхилив саме це повідомлення (HTTP 400): повтор не допоможе."""


def _safe_href(url: str) -> str:
    return url if url.startswith(("https://", "http://")) else "https://t.me/"


def _format(rec: dict) -> str:
    e = html.escape
    date = (rec.get("published_at") or rec["first_seen_at"])[:10]
    src = rec.get("source_name") or rec.get("domain") or ""
    st = STATUS_UK[effective_status(rec)]
    summary = (rec.get("llm") or {}).get("summary_uk")
    title = (rec.get("title") or rec["url"])[:300]
    line = (f'<b>{e(date)}</b>, {e(src)}\n<a href="{e(_safe_href(rec["url"]), quote=True)}">'
            f'{e(title)}</a>\n<i>{e(st)}</i>, оцінка {rec.get("score")}, '
            f'<code>{e(rec["id"])}</code>')
    if summary:
        line += f"\n{e(summary[:500])}"
    return line


def send_telegram(text: str, token: str, chat_id: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("ok"):
                return
            raise RuntimeError(f"Telegram: {payload.get('description')}")
        except urllib.error.HTTPError as e:
            # Опис помилки Telegram лежить у тілі відповіді; токен у повідомлення не потрапляє.
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {}
            desc = body.get("description", f"HTTP {e.code}")
            if e.code == 429 and attempt == 0:
                time.sleep(min(int((body.get("parameters") or {}).get("retry_after", 5)), 30))
                continue
            if e.code == 400:
                raise Rejected(desc) from None
            raise RuntimeError(f"Telegram: {desc}") from None


def _batches(pending: list[dict], header: str) -> list[list[dict]]:
    out: list[list[dict]] = []
    cur: list[dict] = []
    size = len(header)
    for rec in pending:
        part = len(_format(rec)) + 2
        if cur and size + part > LIMIT:
            out.append(cur)
            cur, size = [], 0
        cur.append(rec)
        size += part
    if cur:
        out.append(cur)
    return out


def notify_new(records: list[dict], include_uncertain: bool, errors: list[str]) -> int:
    token = os.environ.get("RENOVATOR_TG_TOKEN")
    chat_id = os.environ.get("RENOVATOR_TG_CHAT_ID")
    pending = [r for r in records if not r.get("notified") and effective_status(r) in wanted_statuses(include_uncertain)]
    if not pending:
        return 0
    if not token or not chat_id:
        log.info("Telegram не налаштовано; %d записів чекають на сповіщення", len(pending))
        return 0
    pending.sort(key=lambda r: (r.get("published_at") or r["first_seen_at"], r["id"]))
    header = f"Нові згадування «Реноватор»: {len(pending)}"
    sent = 0
    for i, batch in enumerate(_batches(pending, header)):
        text = "\n\n".join(([header] if i == 0 else []) + [_format(r) for r in batch])
        try:
            send_telegram(text, token, chat_id)
        except Rejected:
            # Одне «погане» повідомлення не має назавжди блокувати чергу: шлемо поштучно.
            for r in batch:
                try:
                    send_telegram(_format(r), token, chat_id)
                    sent += 1
                except Rejected as e:
                    r["notify_error"] = str(e)[:200]
                    errors.append(f"Telegram відхилив запис {r['id']}: {e}")
                except Exception as e:
                    errors.append(f"Telegram: {e}")
                    return sent
                r["notified"] = True
                time.sleep(1)
            continue
        except Exception as e:  # мережа, 5xx, 401: решту надішлемо наступним прогоном
            errors.append(f"Telegram: {e}")
            return sent
        for r in batch:
            r["notified"] = True
        sent += len(batch)
        time.sleep(1)  # Telegram обмежує частоту повідомлень в один чат
    return sent


def wanted_statuses(include_uncertain: bool) -> set[str]:
    return {"relevant", "uncertain"} if include_uncertain else {"relevant"}
