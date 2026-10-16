"""Offline episode downloads.

Layout follows the storage contract: episodes live under
``$FLET_APP_STORAGE_DATA/animepahe/downloads/<anime>/<episode>/`` (app-private
storage — no Android permissions needed, survives updates, removed on
uninstall).

Format: one variant's media playlist plus all its segments, then a local
``index.m3u8`` whose segment URIs are rewritten to relative filenames (and
key URIs to downloaded key files). No ffmpeg, no concatenation — a
half-written episode is never marked complete, so it can never be opened as
a finished download. A direct file is stored byte-for-byte under the name
the server gave it. Nothing is ever converted.

Resume: per-segment ``.part`` files plus a ``manifest.json``. Restarting a
job skips complete segments and continues partials from their byte offset
with a ``Range`` request.

Job states follow Android Media3's model (the reference the YouTube-class
apps are built on): queued / downloading / stopped / completed / failed /
removing / restarting — there is no "stopping". PAUSE is a persisted stop
reason that keeps the partial bytes; resume is clearing it. A queue caps
concurrency across both paths (files and segments) and orders the rest by
start time, so a whole-series batch is a queue, not a burst.
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import time

import anyio
import primp

from core.storage import app_data_dir

logger = logging.getLogger(__name__)

PARALLEL_SEGMENTS = 6
# Per-segment retry cap inside one job: a segment that keeps failing
# (404) fails the job instead of re-queueing forever.
MAX_SEGMENT_ATTEMPTS = 3

SEGMENT_TIMEOUT = 30
PLAYLIST_TIMEOUT = 15
# A whole-file download is not a segment: the timeout must cover the
# full response body, not a 30s segment. User aborts still arrive via
# the cancel event (and Cancel on a stuck transfer via aclose).
FILE_TIMEOUT = 600
# Concurrent jobs across BOTH paths — the rest queue on the limiter, in
# start order (Media3's maxParallelDownloads, which defaults to 3 there).
MAX_PARALLEL_DOWNLOADS = 3

# Job states (Media3's set — the persisted vocabulary in manifest.json).
STATE_QUEUED = "queued"
STATE_DOWNLOADING = "downloading"
STATE_STOPPED = "stopped"  # paused by the user; partials kept
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
# The store row's two words — what the screens already speak. A row's
# state maps to a job state, never the other way round.
ROW_COMPLETE = "complete"


# ---------------------------------------------------------------------------
# Pure playlist rewriting (unit-tested)
# ---------------------------------------------------------------------------


def rewrite_playlist(text: str, segment_dir_name: str = "segs") -> tuple[str, int]:
    """Rewrite a media playlist for local playback.

    Segment URIs become filenames under ``<segment_dir_name>/`` and are
    returned with the segment count. ``#EXT-X-KEY`` URIs are rewritten to
    the local key file we download alongside the segments. Absolute-URI
    lines that are not keys pass through untouched when they cannot be
    resolved locally.
    """
    if not text:
        return text, 0
    lines = text.splitlines()
    out = []
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#EXT-X-KEY") and "URI=" in stripped:
            # #EXT-X-KEY:METHOD=AES-128,URI="https://.../key.bin"
            match = re.search(r'URI="([^"]+)"', stripped)
            if match:
                key_name = os.path.basename(match.group(1).split("?")[0]) or "key.bin"
                rewritten = re.sub(r'URI="[^"]+"', f'URI="{segment_dir_name}/{key_name}"', stripped)
                out.append(rewritten)
                continue
        if stripped and not stripped.startswith("#"):
            # A media segment line: last non-comment line wins.
            uri = stripped.split("?")[0]
            name = os.path.basename(uri)
            if name and re.search(r"\.(ts|aac|mp4|m4s|vtt)(\.|$)", name, re.IGNORECASE):
                out.append(f"{segment_dir_name}/{name}")
                count += 1
                continue
        out.append(line)
    return "\n".join(out) + "\n", count


def parse_segment_uris(text: str) -> list[str]:
    """The media segment URIs of a media playlist, in order."""
    if not text:
        return []
    uris = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            name = os.path.basename(stripped.split("?")[0])
            if name and re.search(r"\.(ts|aac|mp4|m4s|vtt)(\.|$)", name, re.IGNORECASE):
                uris.append(stripped)
    return uris


def parse_key_uri(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'#EXT-X-KEY:[^\n]*?URI="([^"]+)"', text)
    return match.group(1) if match else None


_ILLEGAL_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _filename_from_disposition(value) -> str:
    """The filename a Content-Disposition header carries.

    Handles ``filename="..."``, ``filename*=UTF-8''...`` (RFC 5987, which
    is what Drive uses for names with non-ASCII characters) and the bare
    ``filename=...`` form. Empty when the header says nothing usable."""
    if not value:
        return ""
    header = str(value)
    match = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", header, re.IGNORECASE)
    if not match:
        match = re.search(r'filename\s*=\s*"([^"]+)"', header, re.IGNORECASE) or re.search(
            r"filename\s*=\s*([^;]+)", header, re.IGNORECASE
        )
    if not match:
        return ""
    from urllib.parse import unquote

    return unquote(match.group(1)).strip().strip('"')


def _safe_component(name, fallback: str = "unknown") -> str:
    """One path component every platform this app ships on accepts.

    Our session ids carry a namespace colon ('kayoanime:961') or separators —
    both are NTFS-illegal, and ``makedirs`` raises WinError 267 on them,
    which silently killed every download on Windows. The mapping is STABLE
    (the same session always maps to the same directory) because resume has
    to find the job again.
    """
    text = _ILLEGAL_PATH_CHARS.sub("_", str(name or "")).strip(" .")
    return text[:80] or fallback


def _safe_filename(name) -> str | None:
    """A provider-supplied filename, reduced to something a filesystem
    will take on every platform this app ships on. None when there is
    nothing usable — the caller then names the file itself.

    The point is fidelity: the saved copy keeps the name the source gave
    it (which carries the quality and the fansub) instead of a bare
    file.mkv, and nothing is converted to achieve that.
    """
    if not name:
        return None
    # A Drive id like "1AbC..." has no extension and no separators — it is
    # an identifier, not a name.
    text = str(name).strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not text or not os.path.splitext(text)[1]:
        return None
    cleaned = _ILLEGAL_PATH_CHARS.sub("_", text).strip(" .")
    if not cleaned or cleaned in {".", ".."} or len(cleaned) > 120:
        return None
    return cleaned


def _calculate_dir_size(directory: str) -> int:
    """Calculate total size of segment files off the event loop."""
    if not os.path.isdir(directory):
        return 0
    return sum(
        os.path.getsize(os.path.join(directory, f))
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    )


def _scan_segments(segs_dir: str, uris: list[str]) -> tuple[int, list[tuple[int, str]]]:
    """One directory listing answers both the resume count and the queue.

    The per-URI probes did N blocking listdir calls on the event loop;
    this runs once, in a worker thread. Matching is by name suffix — the
    same rule resume has always used."""
    present: list[str] = []
    if os.path.isdir(segs_dir):
        present = os.listdir(segs_dir)
    done = 0
    queue: list[tuple[int, str]] = []
    for index, uri in enumerate(uris):
        suffix = "-" + os.path.basename(uri.split("?")[0])
        if any(candidate.endswith(suffix) for candidate in present):
            done += 1
        else:
            queue.append((index, uri))
    return done, queue


class DownloadManager:
    """Owns download jobs: one asyncio task per episode, shared primp client."""

    def __init__(self, store=None, downloads_dir: str | None = None):
        # A queue of jobs shares one limiter so a big batch can't starve
        # the app's own fetches (the UI, the router) — Media3's
        # maxParallelDownloads, applied across BOTH paths (files and
        # segments): the rest queue in start order.
        self._job_limiter = anyio.CapacityLimiter(MAX_PARALLEL_DOWNLOADS)
        self._store = store
        self.downloads_dir = downloads_dir or self._default_dir()
        self._jobs: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel: dict[str, asyncio.Event] = {}
        self._client: primp.AsyncClient | None = None
        self._progress: dict[str, dict] = {}
        # Stop reasons: a PAUSED job keeps its partials (Range resume
        # continues from the byte offset), exactly as Media3's
        # setStopReason does.
        self._stop_reason: dict[str, str] = {}
        self.on_progress = None  # callable(episode_session, dict)
        # callable(episode_session, metadata) when a job completes — the
        # controller turns it into the tray's "download complete" row.
        self.on_finished = None

    @staticmethod
    def _default_dir() -> str:
        return app_data_dir("downloads")

    def _get_client(self) -> primp.AsyncClient:
        if self._client is None:
            self._client = primp.AsyncClient(timeout=SEGMENT_TIMEOUT, impersonate="chrome")
        return self._client

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    @property
    def active_jobs(self) -> list[str]:
        return list(self._tasks.keys())

    async def start(
        self,
        episode_session: str,
        m3u8_url: str,
        headers: dict,
        metadata: dict,
    ) -> None:
        """Enqueue (or resume) an episode download."""
        if episode_session in self._tasks:
            return
        if episode_session in self._stop_reason:
            # Paused by the user: enqueueing again is a no-op until resume
            # clears the stop reason.
            return
        job_dir = self._ensure_job_dir(episode_session, metadata)
        os.makedirs(job_dir, exist_ok=True)
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if self._manifest_is_complete(job_dir, manifest):
            return
        manifest.update(
            {
                "m3u8_url": m3u8_url,
                "headers": headers,
                "state": STATE_QUEUED,
                "metadata": metadata,
            }
        )
        self._write_manifest(manifest_path, manifest)
        self._jobs[episode_session] = {"dir": job_dir, "manifest": manifest_path}
        cancel = asyncio.Event()
        self._cancel[episode_session] = cancel
        # The row's title and anime session ride the progress dict too,
        # so the tray notification can name what is downloading.
        meta = metadata or {}
        self._progress[episode_session] = {
            "done": 0,
            "total": 0,
            "bytes": 0,
            "state": STATE_QUEUED,
            "title": str(meta.get("title") or ""),
            "anime_session": str(meta.get("anime_session") or ""),
        }
        task = asyncio.create_task(
            self._run(episode_session, m3u8_url, headers, metadata, job_dir, cancel),
            name=f"download-{episode_session}",
        )
        self._tasks[episode_session] = task
        task.add_done_callback(lambda t: self._on_done(episode_session))

    async def detect_kind(self, url: str, headers: dict) -> str:
        """What the resolved URL actually is, and what the server calls it.

        Returns ``(kind, filename)``. The kind is the URL's own first
        bytes — never the provider's name and never the extension: 'hls'
        -> segment download; 'file' -> one range-resumed file. Everything
        else is a file: if it doesn't declare EXT-X-M3U, there is nothing
        to segment.

        The filename comes from the SAME response (its
        Content-Disposition), so the saved copy keeps what the server
        named it — a Drive id link, a pixeldrain id link, a CDN path — at
        no extra request."""
        client = self._get_client()
        filename = ""
        try:
            resp = await client.get(url, headers=headers, stream=True, timeout=PLAYLIST_TIMEOUT)
            filename = _filename_from_disposition(resp.headers.get("content-disposition"))
            if url.split("?")[0].endswith(".m3u8") or resp.headers.get(
                "content-type", ""
            ).startswith("application/vnd.apple.mpegurl"):
                await resp.aclose()
                return ("hls", "")
            try:
                first = await resp.anext()
            except StopAsyncIteration:
                first = b""
            finally:
                await resp.aclose()
            if b"#EXTM3U" in (first or b"")[:1024]:
                return ("hls", "")
        except Exception as ex:
            logger.warning("download shape peek failed for %s: %s", url, ex)
        return ("file", filename)

    async def start_direct(
        self,
        episode_session: str,
        url: str,
        headers: dict,
        metadata: dict,
    ) -> None:
        """Enqueue (or resume) a direct-file download — one file, any
        size, range-resumable. Same lifecycle, same store rows, same
        progress/cancel surface as the HLS path; no second system."""
        if episode_session in self._tasks:
            return
        if episode_session in self._stop_reason:
            return  # paused until resume clears the stop reason
        job_dir = self._ensure_job_dir(episode_session, metadata)
        os.makedirs(job_dir, exist_ok=True)
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if self._manifest_is_complete(job_dir, manifest):
            return
        manifest.update(
            {
                "url": url,
                "headers": headers,
                "state": STATE_QUEUED,
                "metadata": metadata,
            }
        )
        self._write_manifest(manifest_path, manifest)
        self._jobs[episode_session] = {"dir": job_dir, "manifest": manifest_path}
        cancel = asyncio.Event()
        self._cancel[episode_session] = cancel
        # The row's title and anime session ride the progress dict too,
        # so the tray notification can name what is downloading.
        meta = metadata or {}
        self._progress[episode_session] = {
            "done": 0,
            "total": 0,
            "bytes": 0,
            "state": STATE_QUEUED,
            "title": str(meta.get("title") or ""),
            "anime_session": str(meta.get("anime_session") or ""),
        }
        task = asyncio.create_task(
            self._run_direct(episode_session, url, headers, metadata, job_dir, cancel),
            name=f"download-{episode_session}",
        )
        self._tasks[episode_session] = task
        task.add_done_callback(lambda t: self._on_done(episode_session))

    def _job_dir(self, anime_session: str, episode_session: str) -> str:
        """Where an episode's job lives. One place, so delete/resume/play
        can never disagree — and one place to keep the names legal on
        every platform (see _safe_component)."""
        return os.path.join(
            self.downloads_dir,
            _safe_component(anime_session or "unknown"),
            _safe_component(episode_session),
        )

    def remove_job(self, anime_session: str, episode_session: str) -> None:
        """Delete a job's files (partials included). Safe when absent."""
        import shutil

        job_dir = self._job_dir(anime_session, episode_session)
        shutil.rmtree(job_dir, ignore_errors=True)
        # Rows written before the platform-safe mapping live under the RAW
        # session name; without this the old files leak forever (nothing
        # would ever delete them).
        legacy = os.path.join(
            self.downloads_dir,
            str(anime_session or "unknown"),
            str(episode_session),
        )
        if os.path.abspath(legacy) != os.path.abspath(job_dir):
            shutil.rmtree(legacy, ignore_errors=True)

    # ------------------------------------------------------------------
    # Pause / resume / retry — Media3's model: pause is a stop reason,
    # not a delete, and the partial bytes are what make resume cheap
    # ------------------------------------------------------------------

    def _ensure_job_dir(self, episode_session: str, metadata: dict) -> str:
        """The job's directory — the one already known for this session
        when there is one, otherwise derived from the metadata.

        Recomputing from metadata would move a resumed job (a manifest
        with no metadata block lands in ``unknown/<ep>``) and orphan the
        partials the resume was supposed to continue."""
        known = self._jobs.get(episode_session)
        if known and os.path.isdir(known.get("dir") or ""):
            return known["dir"]
        return self._job_dir(metadata.get("anime_session", "unknown"), episode_session)

    @staticmethod
    def _job_has_final_file(job_dir: str) -> bool:
        """A COMPLETED manifest is trusted only when the artifact is
        really there: a stale manifest (segments deleted, direct file
        removed) otherwise short-circuited the job into a permanently
        unplayable 'complete' row."""
        if not os.path.isdir(job_dir):
            return False
        for _root, _dirs, files in os.walk(job_dir):
            for name in files:
                if name == "manifest.json" or name.endswith(".part"):
                    continue
                return True
        return False

    def _manifest_is_complete(self, job_dir: str, manifest: dict) -> bool:
        """COMPLETED means done AND present."""
        return manifest.get("state") == STATE_COMPLETED and self._job_has_final_file(job_dir)

    def pause(self, episode_session: str) -> bool:
        """Stop a running job and KEEP its partials. False when the job
        isn't running (nothing to pause)."""
        if episode_session not in self._tasks:
            return False
        self._stop_reason[episode_session] = "paused"
        cancel = self._cancel.get(episode_session)
        if cancel is not None:
            cancel.set()
        task = self._tasks.pop(episode_session, None)
        self._cancel.pop(episode_session, None)
        if task is not None:
            # The task must actually STOP: popping it without cancelling
            # left the writer running, and a later start() (its guard now
            # passes) spawned a SECOND writer on the same directory.
            task.cancel()
        job = self._jobs.get(episode_session)
        if job is not None:
            manifest = self._read_manifest(job["manifest"])
            self._write_manifest(
                job["manifest"],
                {**manifest, "state": STATE_STOPPED, "stop_reason": "paused"},
            )
        logger.info("download paused: %s", episode_session)
        return True

    async def resume(self, episode_session: str, url: str, headers: dict, metadata: dict) -> bool:
        """Clear the stop reason and re-enqueue. The partials on disk are
        what make this a resume rather than a restart (Range continues
        from the byte offset; complete segments are skipped)."""
        job_dir = self._job_dir(metadata.get("anime_session", "unknown"), episode_session)
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if self._manifest_is_complete(job_dir, manifest):
            return False
        self._stop_reason.pop(episode_session, None)
        if manifest.get("m3u8_url") or url.endswith(".m3u8"):
            await self.start(episode_session, manifest.get("m3u8_url") or url, headers, metadata)
        else:
            # The manifest's stored URL wins: resuming with the passed URL
            # appended a different file's bytes to the existing .part.
            await self.start_direct(episode_session, manifest.get("url") or url, headers, metadata)
        return True

    async def retry(self, episode_session: str) -> bool:
        """Re-queue a FAILED job. The only manual retry YouTube documents,
        and the per-episode answer when a batch item fails."""
        job = self._jobs.get(episode_session)
        if job is None:
            return False
        manifest = self._read_manifest(job["manifest"])
        # A stale COMPLETED (manifest says done, files gone) is retryable
        # too — otherwise the row is permanently unplayable.
        if self._manifest_is_complete(job["dir"], manifest):
            return False
        if manifest.get("state") not in (STATE_FAILED, STATE_STOPPED, STATE_COMPLETED):
            return False
        self._stop_reason.pop(episode_session, None)
        if manifest.get("m3u8_url"):
            await self.start(
                episode_session,
                manifest["m3u8_url"],
                manifest.get("headers") or {},
                manifest.get("metadata") or {},
            )
        else:
            await self.start_direct(
                episode_session,
                manifest.get("url") or "",
                manifest.get("headers") or {},
                manifest.get("metadata") or {},
            )
        return True

    def progress(self, episode_session: str) -> dict | None:
        """One progress row for the UI: bytes + the percent when the total
        is known, explicitly percent=None when it isn't (Media3's
        PERCENTAGE_UNSET) — the bar then shows indeterminate rather than
        lying at 0%."""
        current = self._progress.get(episode_session)
        if not current:
            return None
        row = dict(current)
        total = row.get("total") or 0
        row["percent"] = (100 * row.get("done", 0) / total) if total else None
        # The state the UI shows: a job the user paused is stopped even
        # while its partial bytes are still on disk.
        if not row.get("state"):
            row["state"] = (
                STATE_STOPPED
                if episode_session in self._stop_reason
                else STATE_DOWNLOADING
                if episode_session in self._tasks
                else STATE_QUEUED
            )
        return row

    async def _run_direct(
        self,
        episode_session: str,
        url: str,
        headers: dict,
        metadata: dict,
        job_dir: str,
        cancel: asyncio.Event,
    ) -> None:
        """One file, chunked, with the app's progress contract."""
        self._progress[episode_session]["state"] = STATE_DOWNLOADING
        # The provider's own filename when we have it (kayoanime's Drive
        # files carry a real one) — the saved copy keeps what the source
        # named it, so nothing is converted or renamed. Falls back to the
        # URL's extension, which the Drive routes do not have.
        filename = _safe_filename(metadata.get("filename"))
        if filename:
            final_path = os.path.join(job_dir, filename)
        else:
            ext = os.path.splitext(url.split("?")[0])[1] or ".mkv"
            final_path = os.path.join(job_dir, f"file{ext}")
        part_path = f"{final_path}.part"
        progress = self._progress[episode_session]
        have = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        progress["bytes"] = have
        on_progress = getattr(self, "on_progress", None)

        def _chunk(n: int):
            # ONE progress contract: (episode_session, dict) — the same
            # shape the segment path emits. This used to call
            # (session, bytes, 0), which raised TypeError against the
            # controller's handler and was swallowed, so a direct-file
            # download's byte progress never reached the UI at all.
            progress["bytes"] = have + n if not progress["done"] else progress["bytes"] + n
            progress["done"] = 1
            if on_progress is not None:
                with contextlib.suppress(Exception):
                    on_progress(episode_session, dict(progress))

        try:
            async with self._job_limiter:
                ok = await self._download_file(
                    url,
                    headers,
                    part_path,
                    final_path,
                    on_progress=_chunk,
                    cancel=cancel,
                )
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.warning("direct download failed for %s: %s", episode_session, ex)
            if self._store is not None:
                await self._store.save_download_error(episode_session, str(ex))
            return
        finally:
            manifest_path = os.path.join(job_dir, "manifest.json")
            if not os.path.exists(manifest_path) or (
                self._read_manifest(manifest_path).get("state") != STATE_COMPLETED
            ):
                # A paused job keeps its STOPPED state — overwriting it
                # with queued would make the next enqueue resume a job the
                # user paused.
                state = STATE_STOPPED if episode_session in self._stop_reason else STATE_QUEUED
                self._write_manifest(
                    manifest_path,
                    {
                        "url": url,
                        "headers": headers,
                        "state": state,
                        "metadata": metadata,
                    },
                )
        if not ok:
            # Cancelled mid-file: the partial stays on disk (resumable).
            return
        size_bytes = os.path.getsize(final_path)
        if on_progress is not None:
            with contextlib.suppress(Exception):
                on_progress(episode_session, {"bytes": size_bytes, "done": 1, "total": 1})
        self._write_manifest(
            os.path.join(job_dir, "manifest.json"),
            {
                "url": url,
                "headers": headers,
                "state": STATE_COMPLETED,
                "file": final_path,
                "metadata": metadata,
            },
        )
        if self._store is not None:
            row = dict(metadata)
            row.update(
                {
                    "state": ROW_COMPLETE,
                    "file": final_path,
                    "size_bytes": size_bytes,
                    "completed_at": time.time(),
                }
            )
            await self._store.save_download(episode_session, row)
        self._progress.pop(episode_session, None)
        logger.info("download complete (direct): %s (%d bytes)", episode_session, size_bytes)
        if self.on_finished is not None:
            try:
                self.on_finished(episode_session, dict(metadata))
            except Exception as ex:
                logger.info("on_finished failed: %s", ex)

    def cancel(self, episode_session: str):
        cancel = self._cancel.get(episode_session)
        if cancel:
            cancel.set()

    def _on_done(self, episode_session: str):
        task = self._tasks.pop(episode_session, None)
        self._cancel.pop(episode_session, None)
        if task is None or task.cancelled():
            return
        # Retrieve the exception: an unretrieved one is logged by asyncio
        # as "Task exception was never retrieved" and the row would sit on
        # "partial" forever with no error to show. Recording it here means
        # a crashed writer surfaces as the row's Retry state.
        exc = task.exception()
        if exc is None:
            return
        logger.warning("download task failed for %s: %s", episode_session, exc)

        async def _record() -> None:
            if self._store is not None:
                await self._store.save_download_error(episode_session, str(exc))

        with contextlib.suppress(RuntimeError):
            # No running loop (interpreter teardown): nothing to record.
            asyncio.get_running_loop().create_task(_record())

    async def close(self):
        for session in list(self._tasks):
            self.cancel(session)
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    # ------------------------------------------------------------------
    # The job itself
    # ------------------------------------------------------------------

    async def _run(
        self,
        episode_session: str,
        m3u8_url: str,
        headers: dict,
        metadata: dict,
        job_dir: str,
        cancel: asyncio.Event,
    ):
        try:
            # 1. Resolve to a media playlist (top variant for master).
            media_url, media_text = await self._resolve_playlist(m3u8_url, headers)
            if not media_text:
                raise RuntimeError("could not load the media playlist")

            segs_dir = os.path.join(job_dir, "segs")
            os.makedirs(segs_dir, exist_ok=True)

            # 2. Download the key first (segments need it), if any.
            key_uri = parse_key_uri(media_text)
            if key_uri:
                key_name = os.path.basename(key_uri.split("?")[0]) or "key.bin"
                key_path = os.path.join(segs_dir, key_name)
                if not os.path.exists(key_path):
                    body = await self._get_bytes(key_uri, headers)
                    if body is not None:
                        await anyio.to_thread.run_sync(self._atomic_write, key_path, body)

            # 3. Download segments (resume-aware).
            base_url = media_url.rsplit("/", 1)[0]
            uris = parse_segment_uris(media_text)
            total = len(uris)
            progress = self._progress[episode_session]
            progress["total"] = total

            done, queue = await anyio.to_thread.run_sync(_scan_segments, segs_dir, uris)
            progress["done"] = done
            workers = [
                asyncio.create_task(
                    self._worker(
                        queue,
                        base_url,
                        headers,
                        segs_dir,
                        progress,
                        episode_session,
                        cancel,
                    ),
                    name=f"segment-worker-{episode_session}-{i}",
                )
                for i in range(min(PARALLEL_SEGMENTS, max(1, len(queue))))
            ]
            try:
                await asyncio.gather(*workers)
            except Exception:
                # A worker that exhausted its retries raises: tear down its
                # siblings so the job fails cleanly instead of leaving
                # orphaned writers on the same directory.
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                raise
            if cancel.is_set():
                return
            if progress["done"] < total:
                raise RuntimeError("segments incomplete")

            # 4. Rewrite the playlist locally and publish.
            local_playlist, _ = rewrite_playlist(media_text)
            index_path = os.path.join(job_dir, "index.m3u8")
            self._atomic_write_text(index_path, local_playlist)
            manifest_path = os.path.join(job_dir, "manifest.json")
            manifest = self._read_manifest(manifest_path)
            manifest.update(
                {
                    "state": STATE_COMPLETED,
                    "segments": total,
                    "completed_at": time.time(),
                }
            )
            self._write_manifest(manifest_path, manifest)
            if self._store is not None:
                row = dict(manifest.get("metadata") or metadata)
                size_bytes = await anyio.to_thread.run_sync(_calculate_dir_size, segs_dir)
                row.update(
                    {
                        "state": ROW_COMPLETE,
                        "playlist": index_path,
                        "size_bytes": size_bytes,
                        "completed_at": time.time(),
                    }
                )
                await self._store.save_download(episode_session, row)
            self._progress.pop(episode_session, None)
            logger.info("download complete: %s (%d segments)", episode_session, total)
            if self.on_finished is not None:
                try:
                    self.on_finished(episode_session, dict(metadata))
                except Exception as ex:
                    logger.info("on_finished failed: %s", ex)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.warning("download failed for %s: %s", episode_session, ex)
            if self._store is not None:
                await self._store.save_download_error(episode_session, str(ex))
        finally:
            manifest_path = os.path.join(job_dir, "manifest.json")
            manifest = self._read_manifest(manifest_path)
            if manifest.get("state") != STATE_COMPLETED:
                # A paused job keeps its STOPPED state.
                manifest["state"] = (
                    STATE_STOPPED if episode_session in self._stop_reason else STATE_QUEUED
                )
                self._write_manifest(manifest_path, manifest)

    async def _worker(
        self,
        queue: list[tuple[int, str]],
        base_url: str,
        headers: dict,
        segs_dir: str,
        progress: dict,
        episode_session: str,
        cancel: asyncio.Event,
    ):
        # HLS jobs run one worker per segment PARALLEL to the cross-job
        # limiter: without this, N queued episodes fetched Nx6 segments
        # concurrently and bounded nothing.
        async with self._job_limiter:
            # One permanently-failing segment (404) used to be re-queued
            # forever — the job livelocked and never failed. Bounded now.
            attempts: dict[str, int] = {}
            while queue and not cancel.is_set():
                try:
                    index, uri = queue.pop(0)
                except IndexError:
                    return
                segment_url = uri if uri.startswith("http") else f"{base_url}/{uri}"
                name = f"{index:05d}-" + os.path.basename(uri.split("?")[0])
                part_path = os.path.join(segs_dir, name + ".part")
                final_path = os.path.join(segs_dir, name)
                try:
                    await self._download_file(segment_url, headers, part_path, final_path)
                except Exception as ex:
                    tries = attempts.get(uri, 0) + 1
                    attempts[uri] = tries
                    if tries >= MAX_SEGMENT_ATTEMPTS:
                        # Fail the job: _run's except records the error and
                        # the row becomes retryable, not permanently stuck.
                        raise RuntimeError(f"segment {name} failed {tries} times: {ex}") from ex
                    logger.warning(
                        "segment %s failed (attempt %d/%d): %s",
                        name,
                        tries,
                        MAX_SEGMENT_ATTEMPTS,
                        ex,
                    )
                    # Put it back for the next pass; a later retry can pick it up.
                    queue.append((index, uri))
                    continue
                progress["done"] += 1
                if self.on_progress is not None:
                    with contextlib.suppress(Exception):
                        self.on_progress(episode_session, dict(progress))

    async def _resolve_playlist(self, url: str, headers: dict) -> tuple[str, str]:
        """Return the media playlist URL + body (top variant for a master)."""
        body = await self._get_text(url, headers)
        if not body:
            return url, ""
        if "#EXT-X-STREAM-INF" not in body:
            return url, body
        variants = self._parse_variants(body)
        if not variants:
            return url, body
        # Highest bandwidth wins. The old code took the LAST line, which is
        # just the master's listing order — an out-of-order playlist
        # silently pinned the slowest rendition.
        top = max(variants, key=lambda v: v.get("bandwidth", 0)).get("uri", "")
        if not top:
            return url, body
        top_url = top if top.startswith("http") else url.rsplit("/", 1)[0] + "/" + top
        media = await self._get_text(top_url, headers)
        return top_url, media or ""

    @staticmethod
    def _parse_variants(body: str) -> list[dict]:
        """The variant URIs of a master playlist with their BANDWIDTH, in
        listing order."""
        variants: list[dict] = []
        pending: dict | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#EXT-X-STREAM-INF:"):
                attrs = stripped[len("#EXT-X-STREAM-INF:") :]
                bandwidth = 0
                m = re.search(r"BANDWIDTH=(\d+)", attrs)
                if m:
                    bandwidth = int(m.group(1))
                pending = {"uri": "", "bandwidth": bandwidth}
            elif not stripped.startswith("#") and pending is not None:
                pending["uri"] = stripped
                variants.append(pending)
                pending = None
        return [v for v in variants if v["uri"]]

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get_bytes(self, url: str, headers: dict) -> bytes | None:
        try:
            client = self._get_client()
            resp = await client.get(url, headers=headers, timeout=SEGMENT_TIMEOUT)
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception as ex:
            logger.warning("GET %s failed: %s", url, ex)
        return None

    async def _get_text(self, url: str, headers: dict) -> str | None:
        try:
            client = self._get_client()
            resp = await client.get(url, headers=headers, timeout=PLAYLIST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
        except Exception as ex:
            logger.warning("GET %s failed: %s", url, ex)
        return None

    async def _download_file(
        self,
        url: str,
        headers: dict,
        part_path: str,
        final_path: str,
        on_progress=None,
        cancel=None,
        timeout=None,
    ):
        """Download (or resume) one file; atomically move it into place.

        The chunk loop optionally reports byte progress and honors a
        cancel event — the HLS segment callers pass neither, the
        direct-file path passes both, and both share this one body."""
        have = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        request_headers = dict(headers)
        if have:
            request_headers["Range"] = f"bytes={have}-"
        client = self._get_client()
        resp = await client.get(
            url,
            headers=request_headers,
            stream=True,
            timeout=FILE_TIMEOUT if timeout is None else timeout,
        )
        if resp.status_code not in (200, 206):
            # A 404/410/451 segment used to fall through with an empty
            # body and crash later at os.replace (WinError 2). Raising
            # routes it into the worker's retry-with-cap path instead.
            with contextlib.suppress(Exception):
                await resp.aclose()
            raise RuntimeError(f"HTTP {resp.status_code} for {url}")
        mode = "ab" if have and resp.status_code == 206 else "wb"
        # When the server ignores Range and answers 200 we TRUNCATE — so
        # the byte counter starts at 0 too, or it counts the discarded
        # prefix on top of the body.
        done = have if mode == "ab" else 0

        def _write(chunk: bytes) -> None:
            # Off-loop: a per-chunk disk write competes with the UI's
            # frames when it runs on the event loop.
            with open(part_path, mode) as f:
                f.write(chunk)

        async for chunk in resp.aiter_bytes():
            if cancel is not None and cancel.is_set():
                await resp.aclose()
                return False
            await anyio.to_thread.run_sync(_write, chunk)
            done += len(chunk)
            if on_progress is not None:
                on_progress(len(chunk))
        if not os.path.exists(part_path):
            # A 200 with an empty body (some CDNs answer the segment URL
            # with a zero-byte page): nothing to publish.
            raise RuntimeError(f"nothing downloaded from {url}")
        await anyio.to_thread.run_sync(os.replace, part_path, final_path)
        return True

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_manifest(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_manifest(path: str, manifest: dict) -> None:
        DownloadManager._atomic_write_text(path, json.dumps(manifest, indent=2, default=str))

    @staticmethod
    def _replace_with_retry(tmp: str, path: str, attempts: int = 5) -> None:
        """``os.replace`` with a short retry.

        On Windows the destination can be transiently locked by an
        antivirus scan or the search indexer right after the previous
        write; the plain replace then raises WinError 5 and — because the
        call sits inside a fire-and-forget task — killed the whole
        download silently (owner's run, 2026-10-16: a manifest write died
        with PermissionError and the task exception was never retrieved).
        """
        for attempt in range(attempts):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
                    raise
                # Short, growing backoff: the lock is held for milliseconds.
                time.sleep(0.05 * (attempt + 1))

    @staticmethod
    def _atomic_write_text(path: str, text: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        DownloadManager._replace_with_retry(tmp, path)

    @staticmethod
    def _atomic_write(path: str, data: bytes) -> None:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        DownloadManager._replace_with_retry(tmp, path)
