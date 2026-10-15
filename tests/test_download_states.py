"""The download job state machine — Media3's shape.

PAUSE is a persisted stop reason that KEEPS the partial bytes; resume is
clearing it and re-enqueueing (Range continues from the byte offset, and
already-complete segments are skipped). There is no "stopping" state, the
queue caps concurrency across both paths, and progress reports a percent
only when the total is actually known.
"""

import asyncio
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-dlstate-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

import flet as ft  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.downloads import (  # noqa: E402
    MAX_PARALLEL_DOWNLOADS,
    STATE_COMPLETED,
    STATE_QUEUED,
    STATE_STOPPED,
    DownloadManager,
)


class _Resp:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return {}

    async def anext(self):
        if getattr(self, "_peeked", False):
            raise StopAsyncIteration
        self._peeked = True
        return self._body

    _peeked = False

    async def aclose(self):
        pass

    def aiter_bytes(self, chunk_size=None):
        body = self._body

        async def gen():
            for i in range(0, len(body), chunk_size or 65536):
                yield body[i : i + (chunk_size or 65536)]

        return gen()


class _Client:
    def __init__(self, routes=None):
        self._routes = routes or []
        self.requests = []
        self.is_closed = False

    async def get(self, url, headers=None, stream=False, timeout=None):
        self.requests.append({"url": url, "headers": dict(headers or {})})
        for needle, factory in self._routes:
            if needle in url:
                return factory()
        return _Resp(404)

    async def aclose(self):
        self.is_closed = True


class _Store:
    def __init__(self):
        self.rows = {}

    async def save_download(self, session, row):
        self.rows[session] = row

    async def save_download_error(self, session, message):
        self.rows[session] = {"state": "partial", "error": message}


def _manager(tmp_path, routes=None):
    mgr = DownloadManager(store=_Store(), downloads_dir=str(tmp_path))
    mgr._fake = _Client(routes)
    mgr._client = mgr._fake
    return mgr


def _job(mgr, anime_session, episode_session, **manifest):
    job_dir = mgr._job_dir(anime_session, episode_session)
    os.makedirs(job_dir, exist_ok=True)
    if manifest:
        with open(os.path.join(job_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
    return job_dir


def _manifest(job_dir) -> dict:
    with open(os.path.join(job_dir, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def test_pause_keeps_the_partial_and_writes_stopped(tmp_path):
    """PAUSE is a stop reason, not a delete: the fetched bytes stay on disk
    and the manifest says stopped."""
    mgr = _manager(tmp_path)
    job_dir = _job(
        mgr, "sess", "ep1", state=STATE_QUEUED, url="https://x/f"
    )
    with open(os.path.join(job_dir, "file.mkv.part"), "wb") as f:
        f.write(b"B" * 2048)

    async def _scenario():
        async def _hang():
            await asyncio.sleep(30)

        running = asyncio.ensure_future(_hang())
        mgr._tasks["ep1"] = running
        mgr._cancel["ep1"] = asyncio.Event()
        mgr._jobs["ep1"] = {"dir": job_dir, "manifest": os.path.join(job_dir, "manifest.json")}
        assert mgr.pause("ep1") is True
        running.cancel()  # pause() already removed it from _tasks

    asyncio.run(_scenario())

    stored = _manifest(job_dir)
    assert stored["state"] == STATE_STOPPED
    assert stored["stop_reason"] == "paused"
    assert os.path.exists(os.path.join(job_dir, "file.mkv.part"))
    assert "ep1" not in mgr.active_jobs


def test_a_paused_job_is_not_re_enqueued_until_resume(tmp_path):
    mgr = _manager(tmp_path)
    _job(mgr, "sess", "ep2", state=STATE_STOPPED)

    async def _scenario():
        await mgr.start_direct("ep2", "https://x/f", {}, {"anime_session": "sess"})

    # paused (the stop reason is set) -> the enqueue is a no-op
    mgr._stop_reason["ep2"] = "paused"
    asyncio.run(_scenario())
    assert "ep2" not in mgr.active_jobs


def test_resume_clears_the_reason_and_continues_from_the_partial(tmp_path):
    mgr = _manager(tmp_path, [("drive/file", lambda: _Resp(200, body=b"Z" * 1024))])
    job_dir = _job(
        mgr, "sess", "ep3", state=STATE_STOPPED, url="https://drive/file"
    )
    with open(os.path.join(job_dir, "file.mkv.part"), "wb") as f:
        f.write(b"Z" * 512)

    async def _scenario():
        assert await mgr.resume("ep3", "https://drive/file", {}, {"anime_session": "sess"})
        while mgr.active_jobs:
            await asyncio.sleep(0.02)

    asyncio.run(_scenario())
    assert "ep3" not in mgr._stop_reason
    assert _manifest(job_dir)["state"] == STATE_COMPLETED
    # the Range request carried the offset — a resume, not a restart
    assert any(
        r["headers"].get("Range") == "bytes=512-" for r in mgr._fake.requests
    )


def test_retry_re_queues_a_failed_job_from_the_manifest(tmp_path):
    mgr = _manager(tmp_path, [("drive/file", lambda: _Resp(200, body=b"Y" * 256))])
    job_dir = _job(
        mgr, "sess", "ep4", state="failed", url="https://drive/file"
    )

    async def _scenario():
        mgr._jobs["ep4"] = {"dir": job_dir, "manifest": os.path.join(job_dir, "manifest.json")}
        assert await mgr.retry("ep4") is True
        while mgr.active_jobs:
            await asyncio.sleep(0.02)

    asyncio.run(_scenario())
    assert _manifest(job_dir)["state"] == STATE_COMPLETED
    # a job that isn't failed (or doesn't exist) is not retried
    assert asyncio.run(mgr.retry("ep-nope")) is False


def test_progress_reports_percent_only_when_the_total_is_known(tmp_path):
    mgr = _manager(tmp_path)
    mgr._progress["ep1"] = {"done": 5, "total": 20, "bytes": 500}
    assert mgr.progress("ep1")["percent"] == 25
    # unknown length: percent is explicitly None (indeterminate), never a
    # lie at 0%
    mgr._progress["ep2"] = {"done": 3, "total": 0, "bytes": 300}
    assert mgr.progress("ep2")["percent"] is None
    assert mgr.progress("ep-missing") is None


def test_one_progress_contract_for_both_paths(tmp_path):
    """The direct path used to call on_progress(session, bytes, 0) while the
    controller's handler takes (session, dict) — every chunk raised
    TypeError into a swallow, so a file download's progress never reached
    the UI. Both paths now emit the same dict shape."""
    mgr = _manager(tmp_path, [("drive/file", lambda: _Resp(200, body=b"Q" * 4096))])
    seen: list[dict] = []
    mgr.on_progress = lambda session, row: seen.append(dict(row))

    async def _scenario():
        await mgr.start_direct(
            "ep5", "https://drive/file", {}, {"anime_session": "sess"}
        )
        while mgr.active_jobs:
            await asyncio.sleep(0.02)

    asyncio.run(_scenario())
    assert seen, "no progress rows emitted"
    assert all("bytes" in row and "done" in row and "total" in row for row in seen)
    assert seen[-1]["bytes"] == 4096


def test_the_queue_caps_concurrency_across_both_paths(tmp_path):
    mgr = _manager(tmp_path)
    assert mgr._job_limiter.total_tokens == MAX_PARALLEL_DOWNLOADS
    assert MAX_PARALLEL_DOWNLOADS >= 2

    async def _scenario():
        held = 0
        peak = 0

        async def _job():
            nonlocal held, peak
            held += 1
            peak = max(peak, held)
            await asyncio.sleep(0.05)
            held -= 1

        async with anyio.create_task_group() as tg:
            for _ in range(8):
                tg.start_soon(_guarded, mgr._job_limiter, _job)
        return peak

    async def _guarded(limiter, coro_fn):
        async with limiter:
            await coro_fn()

    import anyio

    peak = asyncio.run(_scenario())
    assert peak == MAX_PARALLEL_DOWNLOADS  # the rest queued, in start order


# ---------------------------------------------------------------------
# The backend badge (Phase 8 Step 6)
# ---------------------------------------------------------------------


def test_the_badge_names_the_serving_backend():
    from screens.home_screen import _backend_badge

    class _State:
        current_source_name = "anikato"

    class _Controller:
        def open_backend_picker(self):
            pass

    badge = _backend_badge(_State(), _Controller())
    texts = _texts(badge)
    assert "Anikato" in texts
    # tapping opens the picker
    badge.on_click(None)  # no exception = the wiring is real


def test_the_badge_with_no_serving_backend_says_nothing_auto(tmp_path):
    """Before a source resolves the badge shows a neutral placeholder —
    the word "Auto" never appears (the owner's rule)."""
    from screens.home_screen import _backend_badge

    class _State:
        current_source_name = ""

    badge = _backend_badge(_State(), type("C", (), {"open_backend_picker": lambda: None})())
    texts = _texts(badge)
    assert "…" in texts
    assert not any("auto" in t.lower() for t in texts)


def _texts(control) -> list[str]:
    found: list[str] = []
    stack = [control]
    while stack:
        current = stack.pop()
        if isinstance(current, ft.Text):
            found.append(str(current.value))
        for attr in ("controls", "content"):
            value = getattr(current, attr, None)
            if isinstance(value, list):
                stack.extend(value)
            elif value is not None:
                stack.append(value)
    return found
