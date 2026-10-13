"""The activity terminal's buffer."""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.logger_handler import MemoryLogHandler, get_telemetry_snapshot


def test_ring_buffer_and_format():
    handler = MemoryLogHandler(maxlen=5)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    for i in range(8):
        handler.emit(
            logging.LogRecord("t", logging.INFO, "p", 1, f"line{i}", None, None)
        )
    logs = handler.get_logs()
    assert len(logs) == 5  # capped
    assert logs[0] == "INFO: line3"  # oldest kept
    assert logs[-1] == "INFO: line7"  # newest
    handler.clear_logs()
    assert handler.get_logs() == []


def test_emit_is_exception_safe():
    handler = MemoryLogHandler()
    # A record whose formatting explodes must not raise.
    import logging.handlers

    class Boom(logging.Formatter):
        def format(self, record):
            raise RuntimeError("boom")

    handler.setFormatter(Boom())
    handler.emit(logging.LogRecord("t", logging.INFO, "p", 1, "x", None, None))
    # handleError swallowed it; nothing raised.


def test_telemetry_snapshot_is_multiline():
    snap = get_telemetry_snapshot()
    assert "uptime" in snap
    assert "platform" in snap
    assert "pid" in snap
