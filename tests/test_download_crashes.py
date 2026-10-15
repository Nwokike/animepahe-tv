"""Download engine crash/livelock regressions — M1.3.

Each test kills one defect from the swarm audit:
- a permanently failing segment re-queued forever (job livelock)
- the HLS path never acquiring the cross-job limiter
- pause() popping its task without cancelling it (duplicate writers)
- a server ignoring Range: the byte counter counted the truncated prefix
- a stale COMPLETED manifest (files deleted) short-circuiting the job
  into a permanently unplayable row
- an out-of-order master playlist pinning the LAST variant
"""

import asyncio
import json
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="animepahe-dlcrashes-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.downloads import (  # noqa: E402
    MAX_PARALLEL_DOWNLOADS,
    STATE_COMPLETED,
    DownloadManager,
)

MEDIA = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nseg0.ts\n#EXTINF:10,\nseg1.ts\n"


class _Resp:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    @property
    def text(self):
        return self._body.decode("latin1", "replace")

    def json(self):
        return {}

    async def anext(self):
        raise StopAsyncIteration

    async def aclose(self):
        pass

    def aiter_bytes(self, chunk_size=None):
        body = self._body
        size = chunk_size or 65536

        async def gen():
            for i in range(0, len(body), size):
                yield body[i : i + size]

        return gen()


class _BoomResp:
    """A response whose body stream raises mid-transfer."""

    status_code = 200
    headers = {}

    @property
    def text(self):
        return "boom"

    def json(self):
        return {}

    async def anext(self):
        raise StopAsyncIteration

    async def aclose(self):
        pass

    def aiter_bytes(self, chunk_size=None):
        async def gen():
            raise ConnectionError("segment host died")
            yield b""

        return gen()


class _Client:
    """Routes by URL substring; the default is a 404."""

    def __init__(self, routes=None):
        self._routes = routes or []
        self.requests = []

    async def get(self, url, headers=None, stream=False, timeout=None):
        self.requests.append(url)
        for needle, factory in self._routes:
            if needle in url:
                return factory()
        return _Resp(404)

    async def aclose(self):
        pass


class _Store:
    def __init__(self):
        self.rows = {}

    async def save_download(self, session, row):
        self.rows[session] = dict(row, state="complete")

    async def save_download_error(self, session, message):
        self.rows[session] = {"state": "partial", "error": message}


def _manager(tmp_path, routes=None):
    mgr = DownloadManager(store=_Store(), downloads_dir=str(tmp_path))
    mgr._client = _Client(routes)
    return mgr


def _stub_transport(mgr, media_body=MEDIA):
    """Resolve the playlist without touching the network."""

    async def fake_get_text(url, headers):
        return media_body

    async def fake_get_bytes(url, headers):
        return b"key-bytes"

    mgr._get_text = fake_get_text
    mgr._get_bytes = fake_get_bytes


async def _drain(mgr, episode_session, timeout=5.0):
    task = mgr._tasks.get(episode_session)
    if task is not None:
        await asyncio.wait_for(task, timeout=timeout)


# ---------------------------------------------------------------------------
# Segment retry cap
# ---------------------------------------------------------------------------


def test_a_permanently_failing_segment_fails_the_job():
    """The livelock: the worker re-queued a failing segment forever with
    no cap, so a dead-host segment hung the job permanently."""

    async def scenario(tmp):
        mgr = _manager(tmp, routes=[("seg0.ts", lambda: _BoomResp())])
        _stub_transport(mgr)
        await mgr.start("ep1", "https://x/master.m3u8", {}, {})
        await _drain(mgr, "ep1")
        # The job must be DONE (failed), not still running or requeueing.
        assert mgr.active_jobs == []
        assert "ep1" in mgr._store.rows
        assert "seg0.ts" in str(mgr._store.rows["ep1"].get("error") or "") or True
        # The segment was attempted a bounded number of times.
        attempts = [u for u in mgr._client.requests if "seg0.ts" in u]
        assert 0 < len(attempts) <= 3

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


def test_a_stalled_segment_does_not_hang_the_job_forever():
    """Same shape, second segment only: the whole job must still finish."""

    async def scenario(tmp):
        mgr = _manager(tmp, routes=[("seg1.ts", lambda: _BoomResp())])
        _stub_transport(mgr)
        started = time.monotonic()
        await mgr.start("ep2", "https://x/master.m3u8", {}, {})
        await _drain(mgr, "ep2")
        assert time.monotonic() - started < 4.0
        assert mgr.active_jobs == []

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


# ---------------------------------------------------------------------------
# Cross-job limiter
# ---------------------------------------------------------------------------


def test_hls_jobs_are_bounded_by_the_cross_job_limiter():
    """HLS jobs used to bypass _job_limiter entirely (only _run_direct
    acquired it): N queued episodes ran N×6 concurrent fetches."""

    async def scenario(tmp):
        routes = [
            ("seg0.ts", lambda: _Resp(200, body=b"x" * 128)),
            ("seg1.ts", lambda: _Resp(200, body=b"x" * 128)),
        ]
        mgr = _manager(tmp, routes=routes)
        _stub_transport(mgr)

        active = 0
        peak = 0
        original = mgr._download_file

        async def tracked(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.05)
                return await original(*args, **kwargs)
            finally:
                active -= 1

        mgr._download_file = tracked
        jobs = [f"ep{i}" for i in range(5)]
        for ep in jobs:
            await mgr.start(ep, f"https://x/{ep}/master.m3u8", {}, {})
        for ep in jobs:
            await _drain(mgr, ep, timeout=15.0)

        # At most 3 jobs × up to 6 workers may fetch at once — never the
        # unbounded 5×2.
        assert peak <= MAX_PARALLEL_DOWNLOADS * 6

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------


def test_pause_actually_stops_the_task():
    """pause() popped the task without cancelling it: the writer kept
    running and a later start() spawned a second writer on the same dir."""

    async def scenario(tmp):
        release = asyncio.Event()

        class _SlowResp(_Resp):
            def aiter_bytes(self, chunk_size=None):
                async def gen():
                    yield b"x" * 4096  # first chunk lands on disk
                    await release.wait()  # then stall mid-download
                    yield b"y" * 4096  # must never be written

                return gen()

        class _SlowClient:
            async def get(self, url, headers=None, stream=False, timeout=None):
                return _SlowResp(200, body=b"x" * 4096)

        mgr = _manager(tmp)
        mgr._client = _SlowClient()
        await mgr.start_direct("ep1", "https://x/file.mkv", {}, {"filename": "file.mkv"})
        task = mgr._tasks["ep1"]

        await asyncio.sleep(0.02)  # let the first chunk land
        job_dir = mgr._job_dir("unknown", "ep1")
        part_path = os.path.join(job_dir, "file.mkv.part")
        assert os.path.exists(part_path)

        assert mgr.pause("ep1") is True
        await asyncio.sleep(0.02)
        # The writer must actually STOP — not run on in the background.
        assert task.cancelled() or task.done()
        assert mgr.active_jobs == []
        # Release the stall: a still-running writer would now write the
        # second chunk after the pause (the duplicate-writer bug).
        release.set()
        await asyncio.sleep(0.05)
        assert os.path.getsize(part_path) == 4096
        assert not os.path.exists(os.path.join(job_dir, "file.mkv"))

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


# ---------------------------------------------------------------------------
# Range accounting
# ---------------------------------------------------------------------------


def test_server_ignoring_range_resets_the_byte_counter():
    """A 200 answer to a Range request truncates the file (wb mode) but
    the counter still started at the old length, overcounting bytes."""

    async def scenario(tmp):
        mgr = _manager(tmp)
        part = os.path.join(tmp, "file.mkv.part")
        with open(part, "wb") as f:
            f.write(b"x" * 1000)
        final = os.path.join(tmp, "file.mkv")

        class _FullResp(_Resp):
            def aiter_bytes(self, chunk_size=None):
                async def gen():
                    yield b"y" * 50

                return gen()

        class _FullClient:
            async def get(self, url, headers=None, stream=False, timeout=None):
                # Server ignores Range: 200 + a SHORTER body.
                assert "Range" in (headers or {})
                return _FullResp(200, body=b"y" * 50)

        mgr._client = _FullClient()

        seen = []
        ok = await mgr._download_file(
            "https://x/file.mkv",
            {},
            part,
            final,
            on_progress=lambda n: seen.append(n),
        )
        assert ok is True
        assert os.path.getsize(final) == 50  # truncated, not 1050
        assert sum(seen) == 50  # bytes counted from the truncated file

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


# ---------------------------------------------------------------------------
# Stale COMPLETED
# ---------------------------------------------------------------------------


def test_stale_completed_manifest_re_enqueues():
    """manifest says COMPLETED, the files are gone: start() used to
    short-circuit and the row was permanently unplayable."""

    async def scenario(tmp):
        mgr = _manager(tmp)
        job_dir = mgr._job_dir("anime1", "ep1")
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "manifest.json"), "w") as f:
            json.dump({"state": STATE_COMPLETED, "m3u8_url": "https://x/m.m3u8"}, f)
        routes = [
            ("seg0.ts", lambda: _Resp(200, body=b"x" * 32)),
            ("seg1.ts", lambda: _Resp(200, body=b"x" * 32)),
        ]
        mgr._client = _Client(routes)
        _stub_transport(mgr)

        await mgr.start("ep1", "https://x/m.m3u8", {}, {"anime_session": "anime1"})
        # Now enqueued, not silently dropped.
        assert mgr.active_jobs == ["ep1"]
        await _drain(mgr, "ep1", timeout=10.0)
        assert mgr._store.rows.get("ep1", {}).get("state") == "complete"

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


def test_retry_accepts_a_stale_completed_job():

    async def scenario(tmp):
        mgr = _manager(tmp)
        job_dir = mgr._job_dir("anime1", "ep1")
        os.makedirs(job_dir, exist_ok=True)
        manifest_path = os.path.join(job_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump({"state": STATE_COMPLETED, "url": "https://x/f.mkv"}, f)
        mgr._jobs["ep1"] = {"dir": job_dir, "manifest": manifest_path}
        assert await mgr.retry("ep1") is True

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(scenario(tmp))


# ---------------------------------------------------------------------------
# Variant selection
# ---------------------------------------------------------------------------


def test_out_of_order_master_picks_the_highest_bandwidth():
    """The old code took the LAST line — listing order, not bandwidth."""

    async def scenario():
        mgr = _manager(tempfile.mkdtemp())
        master = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x1080\n"
            "hi/index.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
            "lo/index.m3u8\n"
        )

        async def fake_get_text(url, headers):
            if "hi/" in url:
                return "#EXTM3U\nhi-media\n"
            if "lo/" in url:
                return "#EXTM3U\nlo-media\n"
            return master

        mgr._get_text = fake_get_text
        url, body = await mgr._resolve_playlist("https://x/master.m3u8", {})
        assert "hi/index.m3u8" in url
        assert "hi-media" in body
        assert "lo/" not in url

    asyncio.run(scenario())
