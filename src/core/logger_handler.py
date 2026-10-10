"""In-memory ring-buffer logging for the Activity Terminal.

Ported from the Sherlock pattern: the root logger feeds a bounded deque so
the settings terminal can show real engine/network/UI activity. Everything
is diagnostic only — the terminal is the debugging surface for the
Cloudflare solver, the kwik resolver and downloads.
"""

import logging
import os
import platform
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional


class MemoryLogHandler(logging.Handler):
    """In-memory ring-buffer handler for live terminal display."""

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self._logs: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._logs.append(msg)

    def get_logs(self) -> list[str]:
        with self._lock:
            return list(self._logs)

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()


in_memory_log_handler = MemoryLogHandler()
in_memory_log_handler.setLevel(logging.DEBUG)
in_memory_log_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
)

_root = logging.getLogger()
if not any(isinstance(h, MemoryLogHandler) for h in _root.handlers):
    _root.addHandler(in_memory_log_handler)
# Deliver records to the handler in the first place — the root logger
# defaults to WARNING.
if _root.level == logging.WARNING:
    _root.setLevel(logging.INFO)

_START_TIME = time.time()


def get_telemetry_snapshot() -> str:
    """One compact diagnostics block for the terminal header strip."""
    uptime = time.time() - _START_TIME
    hours, rem = divmod(int(uptime), 3600)
    minutes, seconds = divmod(rem, 60)
    lines = [
        f"uptime {hours:02d}:{minutes:02d}:{seconds:02d}",
        f"platform {platform.system()} {platform.release()}",
        f"pid {os.getpid()}",
        f"buffered {len(in_memory_log_handler.get_logs())} lines",
        f"started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    return "\n".join(lines)
