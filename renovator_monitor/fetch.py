"""HTTP-клієнт на стандартній бібліотеці: тайм-аути, повтори, ліміт розміру, пауза між запитами до одного хоста."""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

DEFAULT_UA = "RenovatorMonitor/1.0 (+media monitoring; contact: see README)"
MAX_BYTES = 5 * 1024 * 1024


class FetchError(Exception):
    pass


class HostSkipped(FetchError):
    """Запит не виконувався: хост вимкнено запобіжником у цьому прогоні."""


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    content_type: str

    def text(self) -> str:
        charset = "utf-8"
        ct = self.content_type.lower()
        if "charset=" in ct:
            charset = ct.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(self, user_agent: str = DEFAULT_UA, timeout: float = 20.0,
                 retries: int = 2, min_interval: dict[str, float] | None = None,
                 default_interval: float = 1.0) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval or {}
        self.default_interval = default_interval
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        # Запобіжник: після кількох поспіль мережевих збоїв хост у цьому прогоні
        # більше не смикаємо, інакше недоступний сервіс з'їдає хвилини на повтори.
        self._failures: dict[str, int] = {}
        self.breaker_threshold = 2

    def _throttle(self, host: str) -> None:
        interval = self.min_interval.get(host, self.default_interval)
        with self._lock:
            wait = self._last.get(host, 0.0) + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def get(self, url: str, headers: dict[str, str] | None = None) -> Response:
        parts = urlsplit(url)
        # Посилання приходять зі стрічок: file://, ftp:// тощо не відкриваємо ніколи.
        if parts.scheme not in ("http", "https"):
            raise FetchError(f"дозволено лише http(s): {url[:80]}")
        host = (parts.hostname or "").lower()
        if self._failures.get(host, 0) >= self.breaker_threshold:
            raise HostSkipped(f"{host} недоступний у цьому прогоні, запит пропущено")
        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": "uk,en;q=0.8",
        }
        if headers:
            req_headers.update(headers)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(host)
            req = urllib.request.Request(url, headers=req_headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise FetchError(f"відповідь більша за {MAX_BYTES} байт: {url}")
                    self._failures[host] = 0
                    return Response(resp.geturl(), resp.status, body,
                                    resp.headers.get("Content-Type", ""))
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 429 or e.code >= 500:
                    delay = _retry_after(e) or 2 ** (attempt + 1)
                    log.warning("HTTP %s від %s, повтор через %.0f с", e.code, host, delay)
                    time.sleep(min(delay, 60))
                    continue
                raise FetchError(f"HTTP {e.code}: {url}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
        self._failures[host] = self._failures.get(host, 0) + 1
        raise FetchError(f"не вдалося отримати {url}: {last_error}")


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    value = e.headers.get("Retry-After") if e.headers else None
    if value and value.isdigit():
        return float(value)
    return None
