"""Pluggable notification sinks.

Backends are selected with ``NETSENTINEL_NOTIFY_BACKEND``. Every backend accepts
a title, a body and a severity; delivery failures are logged, never raised, so a
flaky push service can't take the hub down.
"""

from __future__ import annotations

import logging

import httpx

from .config import Settings, get_settings

log = logging.getLogger("netsentinel.notify")

_SEVERITY_EMOJI = {"info": "i", "low": "*", "medium": "!", "high": "!!!"}


class Notifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()

    def send(self, title: str, body: str = "", severity: str = "medium") -> bool:
        backend = self.s.notify_backend
        try:
            if backend == "none":
                return True
            if backend == "log":
                log.warning("ALERT [%s] %s - %s", severity, title, body)
                return True
            if backend == "ntfy":
                return self._ntfy(title, body, severity)
            if backend == "telegram":
                return self._telegram(title, body, severity)
            if backend == "webhook":
                return self._webhook(title, body, severity)
        except Exception as exc:  # pragma: no cover - network dependent
            log.error("notification via %s failed: %s", backend, exc)
        return False

    # ------------------------------------------------------------------ backends
    def _ntfy(self, title: str, body: str, severity: str) -> bool:
        if not self.s.ntfy_topic:
            log.error("ntfy backend selected but NETSENTINEL_NTFY_TOPIC is empty")
            return False
        prio = {"info": "default", "low": "low", "medium": "default", "high": "urgent"}
        r = httpx.post(
            f"{self.s.ntfy_url.rstrip('/')}/{self.s.ntfy_topic}",
            content=body or title,
            headers={
                "Title": title,
                "Priority": prio.get(severity, "default"),
                "Tags": "shield,netsentinel",
            },
            timeout=10,
        )
        return r.is_success

    def _telegram(self, title: str, body: str, severity: str) -> bool:
        if not (self.s.telegram_bot_token and self.s.telegram_chat_id):
            log.error("telegram backend selected but token/chat id missing")
            return False
        mark = _SEVERITY_EMOJI.get(severity, "!")
        text = f"{mark} *{title}*\n{body}".strip()
        r = httpx.post(
            f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage",
            json={"chat_id": self.s.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return r.is_success

    def _webhook(self, title: str, body: str, severity: str) -> bool:
        if not self.s.webhook_url:
            log.error("webhook backend selected but NETSENTINEL_WEBHOOK_URL is empty")
            return False
        r = httpx.post(
            self.s.webhook_url,
            json={"title": title, "body": body, "severity": severity, "source": "net-sentinel"},
            timeout=10,
        )
        return r.is_success
