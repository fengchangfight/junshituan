"""Structured logging with timestamp + user context.

Usage:
    from app.core.logging import get_logger
    log = get_logger(__name__)
    log.info("something happened")
    log.timing("operation took 500ms")

Output format:
    [2026-07-03 11:30:45.123] [user:alice] [MODULE] message
"""

import contextvars
import time
from datetime import datetime, timezone

# Context var for current user — set by middleware or at request entry
_current_user: contextvars.ContextVar[str] = contextvars.ContextVar("log_user", default="-")


def set_log_user(username: str):
    _current_user.set(username)


class Logger:
    def __init__(self, name: str):
        self._name = name.replace("app.", "", 1) if name.startswith("app.") else name

    def _format(self, level: str, msg: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        user = _current_user.get()
        return f"[{ts}] [user:{user}] [{level} {self._name}] {msg}"

    def debug(self, msg: str):
        print(self._format("DEBUG", msg), flush=True)

    def timing(self, msg: str):
        print(self._format("TIMING", msg), flush=True)

    def info(self, msg: str):
        print(self._format("INFO", msg), flush=True)

    def error(self, msg: str):
        print(self._format("ERROR", msg), flush=True)

    def warning(self, msg: str):
        print(self._format("WARN", msg), flush=True)


_loggers: dict[str, Logger] = {}


def get_logger(name: str = "root") -> Logger:
    if name not in _loggers:
        _loggers[name] = Logger(name)
    return _loggers[name]
