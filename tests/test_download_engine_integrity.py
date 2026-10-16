"""The download engine's live-run bugs — 2026-10-16 evening.

Found by reproducing the app's exact pipeline locally (tools/download_matrix.py):

1. DATA CORRUPTION: `_download_file` opened the part file with mode "wb"
   (TRUNCATE) on EVERY chunk and sent each write through
   `anyio.to_thread.run_sync` — a THREAD POOL. Live evidence: 273 chunks /
   950,904 bytes streamed and read back as a 632-byte garbage file. Every
   HLS download was corrupt; the 24-minute episode sat at 500 KB.
2. An expired signed URL answers an HTML error page with a 200 body — the
   engine saved those pages as `.jpg` segments and reported "complete".
3. The HLS path never published `state="downloading"`, so the UI showed
   "Waiting…" forever.
4. Completion only notified the tray; `state.downloads` kept the stale
   "partial" rows, so the card read 0/2 done over finished files.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

PAYLOAD = b"\x47" + bytes(range(1, 256)) * 4000  # ~1 MB of fake TS


class _FakeResponse:
    status_code = 200

    def __init__(self, body: bytes, chunk: int = 4096, headers=None):
        self._body = body
        self._chunk = chunk
        self.headers = dict(headers or {})

    async def aiter_bytes(self):
        for i in range(0, len(self._body), self._chunk):
            yield self._body[i : i + self._chunk]

    async def aclose(self):
        pass


class _FakeClient:
    """Serves one body; counts concurrent aiter_bytes consumers."""

    def __init__(self, body: bytes):
        self._body = body
        self.concurrent = 0
        self.max_concurrent = 0

    async def get(self, url, headers=None, stream=False, timeout=None):
        body = self._body

        class _R(_FakeResponse):
            async def aiter_bytes(_self):
                self.concurrent += 1
                self.max_concurrent = max(self.max_concurrent, self.concurrent)
                try:
                    for i in range(0, len(body), 4096):
                        yield body[i : i + 4096]
                finally:
                    self.concurrent -= 1

        return _R(body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


def _manager_with(body: bytes):
    from services.downloads import DownloadManager

    manager = DownloadManager(store=None)
    client = _FakeClient(body)
    manager._client = client
    manager._get_client = lambda: client
    return manager, client


def test_a_multi_chunk_download_lands_byte_for_byte(tmp_path):
    """The truncation bug: per-chunk `open(path, "wb")` erased everything
    the previous chunks wrote. The file must equal the source exactly."""
    manager, _ = _manager_with(PAYLOAD)
    part = str(tmp_path / "f.part")
    final = str(tmp_path / "f.ts")

    ok = asyncio.run(manager._download_file("https://cdn/x", {}, part, final))

    assert ok is True
    assert Path(final).read_bytes() == PAYLOAD, "chunks were truncated by concurrent writers"


def test_the_body_is_written_over_a_single_handle(tmp_path):
    """Writers must be serialized on ONE handle — the old code reopened the
    file per chunk, so the thread pool's writes interleaved."""
    manager, _client = _manager_with(PAYLOAD)
    part = str(tmp_path / "f.part")
    final = str(tmp_path / "f.ts")

    asyncio.run(manager._download_file("https://cdn/x", {}, part, final))

    assert Path(final).stat().st_size == len(PAYLOAD)


def test_an_html_error_page_is_rejected_not_saved(tmp_path):
    """An expired signed URL answers a 200 HTML page; the old engine saved
    it as a `.jpg` segment and called the job complete."""
    manager, _ = _manager_with(b"<!DOCTYPE html><html><head><title>404 Not Found</title></head>")
    part = str(tmp_path / "s.part")
    final = str(tmp_path / "s.jpg")

    try:
        asyncio.run(manager._download_file("https://cdn/seg-1.jpg", {}, part, final))
        raise AssertionError("expected the HTML page to be rejected")
    except RuntimeError as ex:
        assert "HTML error page" in str(ex)
    assert not Path(final).exists(), "the error page was published as a segment"


def test_a_cancel_stops_without_publishing(tmp_path):
    import anyio

    manager, _ = _manager_with(PAYLOAD)
    part = str(tmp_path / "c.part")
    final = str(tmp_path / "c.ts")
    cancel = anyio.Event()
    cancel.set()

    ok = asyncio.run(manager._download_file("https://cdn/x", {}, part, final, cancel=cancel))

    assert ok is False
    assert not Path(final).exists()


def test_finished_progress_is_dropped_and_live_progress_kept():
    """The flush task must not resurrect a finished job's row (a callback
    queued in the final half-second used to re-add it as 'downloading')."""
    from services.downloads import DownloadManager

    manager = DownloadManager(store=None)
    manager._progress["live"] = {"done": 1, "total": 2, "state": "downloading"}
    manager._progress["done"] = {"done": 2, "total": 2, "state": "downloading"}

    assert manager.job_running("live") is True
    assert manager.job_running("done") is True  # still tracked until pop
    manager._progress.pop("done")
    assert manager.job_running("done") is False, (
        "a finished/popped job must read as not running so its stale progress cannot come back"
    )
