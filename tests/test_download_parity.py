"""Fetch/stream parity: every file downloads, every stream's bytes fetch.

Dispatch is by what the media IS — never by which source it came from.
Fake transport only; no network.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class _Resp:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return {}

    async def anext(self):
        if self._peeked:
            raise StopAsyncIteration
        self._peeked = True
        return self._body

    _peeked = False

    async def aclose(self):
        pass

    def aiter_bytes(self, chunk_size=None):
        async def gen():
            for i in range(0, len(self._body), chunk_size or 65536):
                yield self._body[i : i + (chunk_size or 65536)]

        return gen()


class _PeekResp(_Resp):
    """The shape detector's peek: first chunk carries the playlist head."""

    def __init__(self, head=b"", headers=None):
        super().__init__(status_code=200, body=b"", headers=headers)
        self._head = head

    async def anext(self):
        if self._peeked:
            raise StopAsyncIteration
        self._peeked = True
        return self._head

    async def aclose(self):
        pass


class _FakeDownloadClient:
    """downloads.py's primp client surface, scripted per URL."""

    def __init__(self, routes):
        self._routes = routes
        self.requests = []

    async def get(self, url, headers=None, stream=False, timeout=None):
        self.requests.append({"url": url, "headers": dict(headers or {})})
        for needle, factory in self._routes:
            if needle in url:
                return factory()
        return _Resp(404)


class _MemoryStore:
    def __init__(self):
        self.rows = {}

    async def save_download(self, session, row):
        self.rows[session] = row

    async def save_download_error(self, session, message):
        self.rows[session] = {"state": "error", "error": message}


def _manager(tmp_path, routes):
    from services.downloads import DownloadManager

    mgr = DownloadManager(store=_MemoryStore(), downloads_dir=str(tmp_path))
    mgr._fake_client = _FakeDownloadClient(routes)
    mgr._get_client = lambda: mgr._fake_client
    return mgr


def test_detect_kind_reads_the_media_not_the_extension(tmp_path):
    mgr = _manager(tmp_path, [])
    mgr._fake_client._routes = [("x", lambda: _PeekResp(b"#EXTM3U\n"))]
    assert asyncio.run(mgr.detect_kind("https://cdn/x.m3u8", {})) == "hls"
    mgr._fake_client._routes = [("x", lambda: _PeekResp(b"\x1aE\xdf\xa3\x93"))]
    assert asyncio.run(mgr.detect_kind("https://drive/x", {})) == "file"


def test_direct_download_resumes_with_range(tmp_path):
    body = b"B" * 4096
    mgr = _manager(
        tmp_path,
        [
            ("full", lambda: _Resp(200, body=body)),
        ],
    )
    # a pre-existing partial resumes with Range
    job_dir = tmp_path / "sess" / "ep1"
    os.makedirs(job_dir, exist_ok=True)
    part = job_dir / "file.mkv.part"
    part.write_bytes(b"B" * 1024)
    seen_headers = {}

    async def run():
        seen = {"bytes": 0}

        def on_progress(n):  # chunk-level, one arg
            seen["bytes"] += n

        ok = await mgr._download_file(
            "https://drive/full",
            {},
            str(part),
            str(job_dir / "file.mkv"),
            on_progress=on_progress,
        )
        return ok, seen

    ok, seen = asyncio.run(run())
    assert ok is True
    assert (job_dir / "file.mkv").read_bytes() == body
    assert seen["bytes"] == len(body)  # every served byte reported
    # the resume is a Range request for exactly what's missing
    assert mgr._fake_client.requests[-1]["headers"].get("Range") == "bytes=1024-"


def test_direct_cancel_leaves_resumable_partial(tmp_path):
    body = b"Z" * 8192
    mgr = _manager(tmp_path, [("full", lambda: _Resp(200, body=body))])
    job_dir = tmp_path / "sess" / "ep2"
    os.makedirs(job_dir, exist_ok=True)
    part = job_dir / "file.mkv.part"

    cancel = asyncio.Event()
    cancel.set()  # cancelled before the first chunk lands
    ok = asyncio.run(
        mgr._download_file(
            "https://drive/full", {}, str(part), str(job_dir / "file.mkv"),
            cancel=cancel,
        )
    )
    assert ok is False
    assert not (job_dir / "file.mkv").exists()  # no final file, partial kept


def test_start_direct_reuses_progress_and_store(tmp_path):
    from services.downloads import _STATE_COMPLETE

    mgr = _manager(tmp_path, [("file", lambda: _Resp(200, body=b"DATA" * 512))])

    async def _scenario():
        await mgr.start_direct(
            "ep3", "https://drive/file", {"Referer": "x"}, {"anime_session": "sess"}
        )
        while mgr.active_jobs:
            await asyncio.sleep(0.02)

    asyncio.run(_scenario())
    row = mgr._store.rows["ep3"]
    assert row["state"] == _STATE_COMPLETE
    assert row["file"].endswith("file.mkv")
    assert row["size_bytes"] == len(b"DATA" * 512)
