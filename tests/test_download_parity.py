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
    assert asyncio.run(mgr.detect_kind("https://cdn/x.m3u8", {})) == ("hls", "")
    mgr._fake_client._routes = [("x", lambda: _PeekResp(b"\x1aE\xdf\xa3\x93"))]
    assert asyncio.run(mgr.detect_kind("https://drive/x", {})) == ("file", "")


def test_detect_kind_returns_the_servers_own_filename(tmp_path):
    """The peek response already carries Content-Disposition, so the saved
    copy can keep the server's name at no extra request."""
    mgr = _manager(tmp_path, [])
    mgr._fake_client._routes = [
        (
            "download",
            lambda: _PeekResp(
                b"\x1aE\xdf\xa3\x93",
                headers={
                    "content-disposition": 'attachment; filename="[Kayoanime] Frieren - 01 [1080p].mkv"'
                },
            ),
        )
    ]
    kind, filename = asyncio.run(
        mgr.detect_kind("https://drive.usercontent.google.com/download?id=abc", {})
    )
    assert kind == "file"
    assert filename == "[Kayoanime] Frieren - 01 [1080p].mkv"


def test_filename_from_disposition_reads_the_rfc5987_form():
    """Drive encodes non-ASCII names as filename*=UTF-8''..."""
    from services.downloads import _filename_from_disposition

    from urllib.parse import quote

    name = "スタッフ.mkv"
    assert (
        _filename_from_disposition(f"attachment; filename*=UTF-8''{quote(name)}")
        == name
    )
    assert _filename_from_disposition("attachment; filename=ep01.mkv") == "ep01.mkv"
    for junk in (None, "", "attachment", "inline"):
        assert _filename_from_disposition(junk) == ""


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
            "https://drive/full",
            {},
            str(part),
            str(job_dir / "file.mkv"),
            cancel=cancel,
        )
    )
    assert ok is False
    assert not (job_dir / "file.mkv").exists()  # no final file, partial kept


def test_start_direct_reuses_progress_and_store(tmp_path):
    from services.downloads import ROW_COMPLETE

    mgr = _manager(tmp_path, [("file", lambda: _Resp(200, body=b"DATA" * 512))])

    async def _scenario():
        await mgr.start_direct(
            "ep3", "https://drive/file", {"Referer": "x"}, {"anime_session": "sess"}
        )
        while mgr.active_jobs:
            await asyncio.sleep(0.02)

    asyncio.run(_scenario())
    row = mgr._store.rows["ep3"]
    assert row["state"] == ROW_COMPLETE
    assert row["file"].endswith("file.mkv")
    assert row["size_bytes"] == len(b"DATA" * 512)


# ---------------------------------------------------------------------
# The provider's own filename, kept (Phase 7.5)
# ---------------------------------------------------------------------


def test_safe_filename_keeps_the_real_name_and_rejects_identifiers():
    from services.downloads import _safe_filename

    # A Drive name with quality + fansub survives intact.
    assert _safe_filename("[Kayoanime] Frieren - 01 [1080p] (SubsPlease).mkv") == (
        "[Kayoanime] Frieren - 01 [1080p] (SubsPlease).mkv"
    )
    # Windows-illegal characters are replaced, never the whole name.
    assert _safe_filename("a:b*c?.mkv") == "a_b_c_.mkv"
    # A bare id (no extension) is an identifier, not a name.
    assert _safe_filename("1AbCdEfGhIjKlMnOpQrSt") is None
    # Drive serves ids with a query string on the URL; the NAME is what
    # matters here, and a path prefix is stripped.
    assert _safe_filename("sub/dir/Ep 01.mkv") == "Ep 01.mkv"
    for junk in (None, "", "   ", ".", "..", "no-extension"):
        assert _safe_filename(junk) is None


def test_direct_download_keeps_the_provided_filename(tmp_path):
    """The keyless Drive route ends in an id, not a name — so the file on
    disk keeps whatever the provider said it was called. No renaming, no
    converting."""
    import asyncio
    import os

    from services.downloads import DownloadManager

    name = "[Kayoanime] Frieren - 01 [1080p] (SubsProvide).mkv"
    body = b"x" * 2048
    mgr = DownloadManager(store=None, downloads_dir=str(tmp_path / "dl"))

    async def _fake(url, headers, part, final, **kw):
        with open(part, "wb") as f:
            f.write(body)
        os.replace(part, final)
        return True

    mgr._download_file = _fake

    async def scenario():
        await mgr.start_direct(
            "ep1",
            "https://drive.usercontent.google.com/download?id=abc&export=download&confirm=t",
            {},
            {"anime_session": "kayoanime:961", "filename": name},
        )
        await asyncio.sleep(0.3)

    asyncio.run(scenario())
    # a namespace colon is illegal on Windows, so the job dir is the
    # sanitized mapping — stable, because resume has to find it again
    import json

    job = tmp_path / "dl" / "kayoanime_961" / "ep1"
    saved = job / name
    assert saved.exists()
    assert saved.read_bytes() == body
    # the manifest records the same name, so a resume finds the file
    manifest = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"]["filename"] == name


def test_direct_download_falls_back_to_the_url_extension(tmp_path):
    import asyncio
    import os

    from services.downloads import DownloadManager

    body = b"y" * 512
    mgr = DownloadManager(store=None, downloads_dir=str(tmp_path / "dl"))

    async def _fake(url, headers, part, final, **kw):
        with open(part, "wb") as f:
            f.write(body)
        os.replace(part, final)
        return True

    mgr._download_file = _fake

    async def scenario():
        await mgr.start_direct(
            "ep2", "https://cdn/x/episode.mkv", {}, {"anime_session": "anikato:a"}
        )
        await asyncio.sleep(0.3)

    asyncio.run(scenario())
    assert (tmp_path / "dl" / "anikato_a" / "ep2" / "file.mkv").exists()


def test_job_paths_are_stable_and_legal_on_every_platform(tmp_path):
    """Our session ids carry a namespace colon ('kayoanime:961') and some
    have a pipe ('slug|7'). NTFS rejects both, which is how every
    download silently failed to start on Windows: makedirs raised
    WinError 267 inside the spawned task, so the row was saved as partial
    and nothing ever downloaded. The mapping is stable, so a resume (or a
    delete) finds the same directory again."""
    import os

    from services.downloads import DownloadManager

    mgr = DownloadManager(store=None, downloads_dir=str(tmp_path))
    first = mgr._job_dir("kayoanime:961", "f274")
    assert mgr._job_dir("kayoanime:961", "f274") == first  # stable
    assert mgr._job_dir("anikato:5789", "slug|7") == mgr._job_dir(
        "anikato:5789", "slug|7"
    )
    # the directory is actually creatable now
    os.makedirs(first, exist_ok=True)
    assert os.path.isdir(first)
    # and the pipe session too
    pipe_dir = mgr._job_dir("anikato:5789", "slug|7")
    os.makedirs(pipe_dir, exist_ok=True)
    assert os.path.isdir(pipe_dir)
    # remove_job deletes what start_direct created
    mgr.remove_job("kayoanime:961", "f274")
    assert not os.path.isdir(first)
