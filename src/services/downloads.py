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
import json
import logging
import os
import re
import time

import anyio
import primp

from core.storage import app_data_dir
from services.ddos_solver import _looks_like_cf_challenge

logger = logging.getLogger(__name__)

PARALLEL_SEGMENTS = 3
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
MAX_PARALLEL_DOWNLOADS = 3  # legacy default; superseded by the owner setting
DEFAULT_MAX_PARALLEL_DOWNLOADS = 2
# Wait before a failed segment is retried (seconds), multiplied by the
# attempt number: a throttled CDN gets room to recover instead of being
# hammered by a hot loop (the "too_many_data_frames" bursts in the
# owner's live log, 2026-10-19).
SEGMENT_RETRY_BACKOFF_SECONDS = 1.5
# An HTTP 429 is the CDN saying "too many requests" outright (live log
# 2026-11-02: waves of 429 + h2 too_many_data_frames at 6 workers x 2
# jobs) — back off an order harder than on transport errors.
RATE_LIMIT_BACKOFF_SECONDS = 12.0

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
            # A media segment line: CDNs (AniKato, AnimePahe) frequently
            # obfuscate video chunks with .jpg, .css, .html, .js or no
            # extension to bypass middlebox filtering — any non-empty,
            # non-comment line in a media playlist is a media segment.
            uri = stripped.split("?")[0]
            if uri:
                out.append(f"{segment_dir_name}/{segment_filename(count, uri)}")
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
            uris.append(stripped)
    return uris


def parse_key_uri(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'#EXT-X-KEY:[^\n]*?URI="([^"]+)"', text)
    return match.group(1) if match else None


_ILLEGAL_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def segment_filename(index: int, uri: str) -> str:
    """The on-disk name of one segment — THE single naming rule.

    The index prefix is what makes the name unique: CDNs (AniKato,
    AnimePahe) obfuscate their chunks with rotating fake extensions
    (``seg-f1-00000.jpg``, ``seg-f1-00001.html`` …) and, worse, several
    distinct segments can share a basename across a playlist's variants.
    Without the prefix the writer and the playlist rewriter disagreed
    about every filename, so a COMPLETE download played as a black frame
    while mpv logged "Cannot open file …/seg-f1-00000.jpg" once per
    segment (owner's live log, 2026-10-25).

    Writer (``_worker``) and rewriter (``rewrite_playlist``) both call
    this, so they cannot drift again.
    """
    return f"{index:05d}-" + os.path.basename(uri.split("?")[0])


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

    def __init__(
        self,
        store=None,
        downloads_dir: str | None = None,
        max_parallel: int = DEFAULT_MAX_PARALLEL_DOWNLOADS,
    ):
        # A queue of jobs shares one limiter so a big batch can't starve
        # the app's own fetches (the UI, the router) — Media3's
        # maxParallelDownloads, applied across BOTH paths (files and
        # segments): the rest queue in start order. Owner setting
        # (Settings screen), default 2 — more runners starve each other
        # on the same CDN (owner, 2026-11-02).
        self.max_parallel = max(1, min(int(max_parallel), 2))
        self._job_limiter = anyio.CapacityLimiter(self.max_parallel)
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
        variant: int | None = None,
    ) -> None:
        """Enqueue (or resume) an episode download.

        `variant` pins the master-playlist rendition the user picked
        (owner, 2026-11-02: without it a 360p pick downloaded the 1080p —
        ~10x the bytes). Persisted in the manifest so resume/retry keep it."""
        if episode_session in self._tasks:
            return
        if episode_session in self._stop_reason:
            # Paused by the user: enqueueing again is a no-op until resume
            # clears the stop reason.
            return
        job_dir = self._ensure_job_dir(episode_session, metadata)
        os.makedirs(job_dir, exist_ok=True)
        # Subtitle sidecars ride with the download so offline playback has
        # them (owner, 2026-11-03). Each track is fetched to a local file
        # and the manifest metadata is rewritten to that path — mpv reads
        # local files with no network and no CDN headers. A track that
        # fails to fetch keeps its remote URL (still playable while online).
        remote_subs = (metadata or {}).get("subtitles") or []
        if remote_subs:
            metadata = dict(metadata)
            metadata["subtitles"] = await self._fetch_subtitle_sidecars(
                remote_subs, headers, job_dir
            )
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if self._manifest_is_complete(job_dir, manifest):
            return
        if variant is None:
            variant = manifest.get("variant")  # resume keeps the pinned one
        manifest.update(
            {
                "m3u8_url": m3u8_url,
                "headers": headers,
                "state": STATE_QUEUED,
                "metadata": metadata,
                "variant": variant,
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
            self._run(episode_session, m3u8_url, headers, metadata, job_dir, cancel, variant),
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
        # Subtitle sidecars ride with the download so offline playback has
        # them (owner, 2026-11-03). Each track is fetched to a local file
        # and the manifest metadata is rewritten to that path — mpv reads
        # local files with no network and no CDN headers. A track that
        # fails to fetch keeps its remote URL (still playable while online).
        remote_subs = (metadata or {}).get("subtitles") or []
        if remote_subs:
            metadata = dict(metadata)
            metadata["subtitles"] = await self._fetch_subtitle_sidecars(
                remote_subs, headers, job_dir
            )
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
        and the per-episode answer when a batch item fails.

        Cold start: the in-memory job map is empty after the app restarted;
        a partial row recovers its manifest from the store row and resumes
        from the segments already on disk (owner's report 2026-11-02: a
        killed app read "Not started" with no way back in)."""
        job = self._jobs.get(episode_session)
        manifest = None
        if job is not None:
            manifest = self._read_manifest(job["manifest"])
        else:
            row = None
            try:
                if self._store is not None:
                    rows = await self._store.get_downloads()
                    row = rows.get(episode_session)
            except AttributeError:
                row = None  # test doubles / stores without downloads
            if not isinstance(row, dict) or row.get("state") != "partial":
                return False
            manifest_path = os.path.join(
                self._ensure_job_dir(episode_session, dict(row)), "manifest.json"
            )
            if not os.path.exists(manifest_path):
                return False
            manifest = self._read_manifest(manifest_path)
            self._jobs[episode_session] = {
                "dir": os.path.dirname(manifest_path),
                "manifest": manifest_path,
            }
        # A stale COMPLETED (manifest says done, files gone) is retryable
        # too — otherwise the row is permanently unplayable. Stale
        # QUEUED/DOWNLOADING states are a session that died mid-run: the
        # same cold-start case, resumable from the manifest.
        if self._manifest_is_complete(
            job["dir"] if job else self._jobs[episode_session]["dir"], manifest
        ):
            return False
        if manifest.get("state") not in (
            STATE_FAILED,
            STATE_STOPPED,
            STATE_COMPLETED,
            STATE_QUEUED,
            STATE_DOWNLOADING,
        ):
            return False
        self._stop_reason.pop(episode_session, None)
        if manifest.get("m3u8_url"):
            await self.start(
                episode_session,
                manifest["m3u8_url"],
                manifest.get("headers") or {},
                manifest.get("metadata") or {},
                variant=manifest.get("variant"),
            )
        else:
            await self.start_direct(
                episode_session,
                manifest.get("url") or "",
                manifest.get("headers") or {},
                manifest.get("metadata") or {},
            )
        return True

    def set_max_parallel(self, value: int) -> None:
        """Owner setting: 1-4 concurrent downloads. Jobs already fetching
        keep the old limiter's permits; the next fetch uses the new one."""
        self.max_parallel = max(1, min(int(value), 2))
        self._job_limiter = anyio.CapacityLimiter(self.max_parallel)

    def job_running(self, episode_session: str) -> bool:
        """Is this job still tracked? False once it finished/was removed —
        the signal the controller's flusher uses to stop resurrecting a
        finished row from a late progress callback."""
        return episode_session in self._progress

    def clear_progress(self, sessions: list[str]) -> None:
        """Drop progress entries the UI has already consumed (a failed
        job whose row now carries the error + Retry)."""
        for session in sessions:
            self._progress.pop(session, None)

    async def _solve_cloudflare(self, episode_session: str, url: str) -> dict | None:
        """A Cloudflare wall answered the file fetch. One shot: ask the
        controller to run the verification (the same window the play path
        shows) and return FRESH headers, or None when unsolved. The new
        headers are written into the job's manifest so resume/retry keep
        them."""
        resolver = getattr(self, "on_cloudflare", None)
        new_headers = None
        if resolver is not None:
            try:
                new_headers = await resolver(episode_session, url)
            except Exception as ex:
                logger.warning("download CF resolve failed: %s", ex)
        if not new_headers:
            return None
        job = self._jobs.get(episode_session)
        if job is not None:
            manifest_path = job.get("manifest")
            manifest = self._read_manifest(manifest_path)
            if manifest:
                manifest["headers"] = dict(new_headers)
                self._write_manifest(manifest_path, manifest)
        return dict(new_headers)

    async def _fetch_subtitle_sidecars(
        self, subs: list, headers: dict, job_dir: str
    ) -> list:
        """Download each remote subtitle track into <job_dir>/subs and
        return the same entries with their url rewritten to the local file
        path (a supported VideoSubtitleTrack.src form — mpv reads local
        files with no network and no CDN headers). A track that fails to
        fetch keeps its remote URL (still playable while online)."""
        out: list = []
        subs_dir = os.path.join(job_dir, "subs")
        client = None
        for i, entry_in in enumerate(subs):
            if not isinstance(entry_in, dict):
                continue
            entry = dict(entry_in)
            url = entry.get("url") or ""
            if url.startswith(("http://", "https://")):
                try:
                    client = client or self._get_client()
                    resp = await client.get(url, headers=headers, timeout=PLAYLIST_TIMEOUT)
                    data = resp.content or b""
                    await resp.aclose()
                    if data:
                        os.makedirs(subs_dir, exist_ok=True)
                        ext = os.path.splitext(url.split("?")[0])[1] or ".vtt"
                        if ext.lower() not in (".vtt", ".srt", ".ass", ".ssa"):
                            ext = ".vtt"
                        label = str(entry.get("label") or "sub")
                        safe = _safe_filename(label) or "sub"
                        path = os.path.join(subs_dir, f"{i + 1}-{safe}{ext}")
                        await anyio.to_thread.run_sync(self._atomic_write, path, data)
                        entry["url"] = path
                except Exception as ex:
                    logger.warning("subtitle fetch failed for %s: %s", url, ex)
            out.append(entry)
        return out

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
        # Byte-based jobs (direct files) percent from BYTES, not the file
        # counter — done=1 over a 195 MB total would read as 0% forever.
        bytes_done = row.get("bytes") or 0
        if total > 20_000 and bytes_done:
            row["percent"] = min(100.0, 100 * bytes_done / total)
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

    def _emit_progress(self, episode_session: str) -> None:
        """Send the UI-facing row (WITH percent) to the controller callback.

        The live chunk/segment paths used to send the raw internal dict, which
        has bytes/total/done/state but no "percent" — so the downloads screen
        could only ever paint "Starting…" and an indeterminate bar while a
        job ran (owner, 2026-11-01: no realtime state/percentage)."""
        on_progress = getattr(self, "on_progress", None)
        if on_progress is None:
            return
        row = self.progress(episode_session)
        if row is None:
            return
        try:
            on_progress(episode_session, dict(row))
        except Exception:
            logger.debug("suppressed")

    async def _run_direct(
        self,
        episode_session: str,
        url: str,
        headers: dict,
        metadata: dict,
        job_dir: str,
        cancel: asyncio.Event,
    ) -> None:
        """One file, chunked, with the app's progress contract. The JOB slot
        (max_parallel) is held for the whole download — segment-level
        parallelism is a per-job concern."""
        async with self._job_limiter:
            await self._run_direct_inner(episode_session, url, headers, metadata, job_dir, cancel)

    async def _run_direct_inner(
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
        progress["total"] = progress.get("total") or 0

        def _chunk(n: int, total: int):
            # ONE progress contract: (episode_session, dict) — the same
            # shape the segment path emits. This used to call
            # (session, bytes, 0), which raised TypeError against the
            # controller's handler and was swallowed, so a direct-file
            # download's byte progress never reached the UI at all.
            progress["bytes"] = progress.get("bytes", 0) + n
            if total:
                # The server's own size is the denominator, so the bar
                # shows a real percent from the first chunk (Sherlock's
                # shape: "42% · 78.2/186.4 MB") instead of spinning at 0
                # until the file ends.
                progress["total"] = total
                # The MB ladder reads total_bytes (bytes for a direct file).
                progress["total_bytes"] = total
            progress["done"] = 1
            self._emit_progress(episode_session)

        try:
            ok = await self._download_file(
                url,
                headers,
                part_path,
                final_path,
                on_progress=_chunk,
                cancel=cancel,
                episode_session=episode_session,
            )
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.warning("direct download failed for %s: %s", episode_session, ex)
            # Publish the failure NOW: without it the row's spinner kept
            # turning forever on a job that had already died (owner's run:
            # episode 1 sat "downloading" while the log showed its failure).
            progress["state"] = STATE_FAILED
            progress["error"] = str(ex)[:200]
            self._emit_progress(episode_session)
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
                # user paused. Anything else that did not complete
                # FAILED, so the row can be retried (retry() accepts
                # failed/stopped/completed, 2026-10-19 re-audit).
                state = STATE_STOPPED if episode_session in self._stop_reason else STATE_FAILED
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
        progress["bytes"] = size_bytes
        progress["total"] = size_bytes
        progress["total_bytes"] = size_bytes
        progress["done"] = 1
        # The old 2-arg call on_progress(size_bytes, size_bytes) violated the
        # (session, dict) contract and was silently dropped by the flusher.
        self._emit_progress(episode_session)
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

        try:
            # No running loop (interpreter teardown): nothing to record.
            asyncio.get_running_loop().create_task(_record())

        except RuntimeError:
            logger.debug("suppressed")

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
        variant: int | None = None,
    ):
        # The job SLOT is held for the WHOLE job: max_parallel bounds JOBS,
        # while each job's PARALLEL_SEGMENTS workers fetch freely (owner's
        # speed report, 2026-11-02 — the old per-FETCH limiter collapsed
        # every job's 6 workers to 2 concurrent fetches app-wide).
        async with self._job_limiter:
            await self._run_inner(
                episode_session, m3u8_url, headers, metadata, job_dir, cancel, variant
            )

    async def _run_inner(
        self,
        episode_session: str,
        m3u8_url: str,
        headers: dict,
        metadata: dict,
        job_dir: str,
        cancel: asyncio.Event,
        variant: int | None = None,
    ):
        try:
            # 1. Resolve to a media playlist — the CHOSEN variant for a
            # master (owner, 2026-11-02: the top variant meant a 360p pick
            # downloaded 1080p, ~10x the bytes).
            #
            # The kwik CDN hotlink-protects the resolved master: by the time
            # this fetch runs, the resolver's GET+HEAD and detect_kind have
            # already hit the URL, and batch downloads 403 the tail (owner's
            # phone run: every episode failed "could not load the media
            # playlist" right after a 200 from the resolver). On failure,
            # ask the controller for a FRESH resolve (a new kwik session →
            # a new owocdn URL) and retry — a fresh URL always answers.
            media_url = m3u8_url
            media_text = ""
            for attempt in range(3):
                media_url, media_text = await self._resolve_playlist(
                    m3u8_url, headers, variant
                )
                if media_text or self._is_closing:
                    break
                if cancel is not None and cancel.is_set():
                    break
                fresh_url = None
                blocked = getattr(self, "on_fetch_blocked", None)
                if blocked is not None:
                    try:
                        fresh_url = await blocked(episode_session, m3u8_url)
                    except Exception as ex:
                        logger.warning(
                            "fresh-resolve callback failed: %s", ex
                        )
                if fresh_url:
                    m3u8_url = fresh_url
                    logger.info(
                        "retrying playlist with a fresh resolve (attempt %d)",
                        attempt + 1,
                    )
                else:
                    await asyncio.sleep(2.0)
            if not media_text:
                raise RuntimeError(
                    "could not load the media playlist (the CDN refused the "
                    "resolved URL; a fresh resolve was attempted)"
                )

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
            if total == 0:
                # A playlist with no segments is not a video: the source
                # served an ad-stub or an empty manifest. The owner's log
                # showed "download complete: … (0 segments)" — a COMPLETE
                # row holding nothing, which then "plays" as a black frame.
                # Failing here is the honest outcome; the row offers Retry.
                raise RuntimeError("the stream served no segments")
            progress = self._progress[episode_session]
            progress["total"] = total
            # The job IS downloading now — without this the progress dict
            # stayed "queued" for the whole 144-segment run and the UI
            # rendered the "Waiting…" spinner with no bar, from first byte
            # to last (owner's live run: every published row said
            # state=queued while segments were flying). _run_direct
            # already declared this; the HLS path never did.
            progress["state"] = STATE_DOWNLOADING

            done, queue = await anyio.to_thread.run_sync(_scan_segments, segs_dir, uris)
            progress["done"] = done
            # Seed the MB display from the segments already on disk (a
            # resumed job must not start its byte count at zero). NO
            # total_bytes here: an m3u8 job's total is unknowable until
            # every segment is fetched, and a running "total" that keeps
            # growing is a lie (owner, 2026-11-02).
            if done:
                try:
                    resumed_bytes = await anyio.to_thread.run_sync(_calculate_dir_size, segs_dir)
                    progress["bytes"] = resumed_bytes
                except Exception:
                    logger.debug("suppressed")
            # One attempt counter for the WHOLE job: a requeued segment
            # can land on any worker, so a per-worker counter would reset
            # and one bad segment could be retried 18 times (6 workers x
            # 3 attempts) instead of the 3 the cap promises.
            attempts: dict[str, int] = {}
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
                        attempts,
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
            # The row must SAY failed — it used to stay "Queued" while the
            # manifest quietly flipped to FAILED, so Retry never appeared
            # and the job looked immortal (owner's phone run, 2026-11-03).
            progress = self._progress.get(episode_session)
            if progress is not None:
                progress["state"] = STATE_FAILED
                progress["error"] = str(ex)[:200]
                self._emit_progress(episode_session)
            if self._store is not None:
                await self._store.save_download_error(episode_session, str(ex))
        finally:
            manifest_path = os.path.join(job_dir, "manifest.json")
            manifest = self._read_manifest(manifest_path)
            if manifest.get("state") != STATE_COMPLETED:
                # A paused job keeps its STOPPED state. Anything else that
                # did not complete FAILED — and it must SAY so: the
                # manifest said "queued", but retry() only accepts
                # failed/stopped/completed, so a failed download could
                # never be retried from the row (a dead end, 2026-10-19
                # re-audit).
                manifest["state"] = (
                    STATE_STOPPED if episode_session in self._stop_reason else STATE_FAILED
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
        attempts: dict[str, int],
    ):
        # The segment workers of one job SHARE the attempt counter: a
        # requeued segment can be picked up by a different worker, so a
        # per-worker counter reset itself and one segment could be tried
        # PARALLEL_SEGMENTS x MAX_SEGMENT_ATTEMPTS times (18) instead of
        # the 3 the cap promises.
        def _segment_bytes(n: int, seg_total: int):
            # Live byte accounting for the MB-done display (owner's rule:
            # MB, never segment counts). m3u8 sets NO total — the direct
            # path's Content-Length is the only verifiable one.
            if n:
                progress["bytes"] = progress.get("bytes", 0) + n

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
                await self._download_file(
                    segment_url,
                    headers,
                    part_path,
                    final_path,
                    on_progress=_segment_bytes,
                    cancel=cancel,
                    episode_session=episode_session,
                )
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
                # Back off before requeueing. The wall-mounted CDNs
                # answer a burst with "too_many_data_frames", and a hot
                # retry loop turns that into a throttle spiral (owner's
                # log, 2026-10-19: bursts of those warnings mid-series).
                # An HTTP 429 is an explicit rate limit: back off an order
                # harder (live log 2026-11-02). The wait grows with the
                # attempt and happens OUTSIDE the job slot, so the job's
                # other segments — and other jobs — keep going.
                is_rate_limited = "429" in str(ex)[:120]
                backoff = (
                    RATE_LIMIT_BACKOFF_SECONDS if is_rate_limited else SEGMENT_RETRY_BACKOFF_SECONDS
                )
                await asyncio.sleep(min(backoff * tries, 20.0))
                # Put it back for the next pass; a later retry can pick it up.
                queue.append((index, uri))
                continue
            # Clamp to total: a re-scan duplicate must not push the percent
            # to a stuck "100%" while stragglers still retry (owner's log
            # 2026-11-02).
            progress["done"] = min(progress["done"] + 1, progress.get("total") or 0)
            # NO total_bytes for m3u8 jobs: the total is unknowable until
            # every segment has been fetched, and a running "total" that
            # keeps growing is a lie (owner, 2026-11-02). The UI shows the
            # verified bytes-done only.
            self._emit_progress(episode_session)

    async def _resolve_playlist(
        self, url: str, headers: dict, variant: int | None = None
    ) -> tuple[str, str]:
        """Return the media playlist URL + body.

        For a master, the CHOSEN variant wins when valid (the download
        dialog's pick / the series preset); otherwise the top-bandwidth
        variant (previous behavior)."""
        body = await self._get_text(url, headers)
        if not body:
            return url, ""
        if "#EXT-X-STREAM-INF" not in body:
            return url, body
        variants = self._parse_variants(body)
        if not variants:
            return url, body
        if variant is not None and 0 <= variant < len(variants):
            chosen = variants[variant]
        else:
            # Highest bandwidth wins. The old code took the LAST line, which is
            # just the master's listing order — an out-of-order playlist
            # silently pinned the slowest rendition.
            chosen = max(variants, key=lambda v: v.get("bandwidth", 0))
        uri = chosen.get("uri", "")
        if not uri:
            return url, body
        media_url = uri if uri.startswith("http") else url.rsplit("/", 1)[0] + "/" + uri
        media = await self._get_text(media_url, headers)
        return media_url, media or ""

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
            # The kwik CDN (owocdn) hotlink-protects the resolved master:
            # the resolver's own GET+HEAD, detect_kind and this fetch all
            # hit the same URL within seconds, and the batch pattern 403s
            # the tail. Report it so the caller can re-resolve fresh.
            logger.warning("GET %s -> %s", url, resp.status_code)
            return None
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
        _retried: bool = False,
        episode_session: str | None = None,
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
            try:
                body = resp.text or ""
            except Exception:
                body = ""
            try:
                await resp.aclose()
            except Exception:
                logger.debug("suppressed")
            # A Cloudflare wall must trigger the solver — the same way the
            # play path does — instead of failing silently (owner,
            # 2026-11-03: AnimeOut downloads died on the file host's 403
            # with no verification window).
            if resp.status_code in (403, 503, 542) and _looks_like_cf_challenge(
                body, resp.status_code
            ):
                new_headers = await self._solve_cloudflare(
                    episode_session or "", url
                )
                if new_headers is not None:
                    return await self._download_file(
                        url,
                        new_headers,
                        part_path,
                        final_path,
                        on_progress=on_progress,
                        cancel=cancel,
                        timeout=timeout,
                        _retried=True,
                    )
                raise RuntimeError(
                    f"Cloudflare verification required for {url.split('/')[2]}"
                )
            raise RuntimeError(f"HTTP {resp.status_code} for {url}")
        # Resume ALIGNMENT. A Range request is only valid when the answer
        # starts exactly at `have`:
        #   - 206 must carry `Content-Range: bytes {have}-...`;
        #   - a 200 to a Range request means the server IGNORED it and is
        #     sending the whole file from byte 0 — appending that onto the
        #     partial wrote a doubled, unplayable file (live evidence:
        #     82 MB "complete" MKV with no EBML magic; the player answered
        #     "Failed to recognize file format", owner's run 2026-10-16).
        # Anything misaligned restarts the file from zero.
        content_range = str(resp.headers.get("content-range") or "")
        if have and resp.status_code == 206:
            if not content_range.startswith(f"bytes {have}-"):
                try:
                    await resp.aclose()
                except Exception:
                    logger.debug("suppressed")
                logger.warning(
                    "resume misaligned for %s (%s) — restarting the file",
                    url,
                    content_range or "no Content-Range",
                )
                try:
                    os.remove(part_path)
                except OSError:
                    logger.debug("suppressed")
                have = 0
        elif have and resp.status_code == 200:
            declared = resp.headers.get("content-length")
            try:
                declared = int(declared) if declared is not None else None
            except (TypeError, ValueError):
                declared = None
            if declared is not None and declared != have:
                # The body is not our partial: the server ignored Range
                # (misaligned append) or the file changed under us.
                logger.warning(
                    "resume ignored by the server for %s (have=%d, body=%s) — restarting",
                    url,
                    have,
                    declared,
                )
                have = 0
        mode = "ab" if have and resp.status_code == 206 else "wb"
        # When the server ignores Range and answers 200 we TRUNCATE — so
        # the byte counter starts at 0 too, or it counts the discarded
        # prefix on top of the body.
        done = have if mode == "ab" else 0
        # The denominator for a real percent. 206 answers carry the FULL
        # size in Content-Range ("bytes 100-999/1000"); a 200's
        # Content-Length is the whole file.
        body_total = 0
        if mode == "ab" and "/" in content_range:
            try:
                body_total = int(content_range.rsplit("/", 1)[1])
            except ValueError:
                logger.debug("suppressed")
        if not body_total:
            try:
                body_total = int(resp.headers.get("content-length") or 0)
            except (TypeError, ValueError):
                logger.debug("suppressed")
        progress_total = body_total if body_total > done else 0

        # ONE handle for the whole body. The old per-chunk writer opened
        # the part file with mode "wb" (truncate) on EVERY chunk and
        # dispatched each write through anyio.to_thread.run_sync — a
        # THREAD POOL, so concurrent writers truncated one another. Live
        # proof (2026-10-16): 273 chunks / 950,904 bytes streamed and read
        # back as a 632-byte garbage file. One handle also makes the
        # close-before-rename ordering deterministic. The handle lives
        # across awaits by design; the finally below closes it everywhere.
        handle = await anyio.to_thread.run_sync(lambda: open(part_path, mode))  # noqa: SIM115
        try:
            first = True
            async for chunk in resp.aiter_bytes():
                if cancel is not None and cancel.is_set():
                    await resp.aclose()
                    return False
                if first:
                    first = False
                    # A media segment is NEVER an HTML page. An EXPIRED
                    # signed URL answers an error page with a 200 body —
                    # the old code saved those pages as `.jpg` segments and
                    # reported the job "complete": a 24-minute episode
                    # ended up 500 KB on disk (owner's run, 2026-10-16).
                    # Raising routes it into the worker's retry-with-cap
                    # path, so the job FAILS honestly instead of publishing
                    # 404 pages as video.
                    head = chunk[:512].lower()
                    if b"<html" in head or b"<!doctype html" in head or b"<head>" in head:
                        await resp.aclose()
                        raise RuntimeError(f"HTML error page served for {url}")
                # Off-loop: a per-chunk disk write competes with the UI's
                # frames when it runs on the event loop. Serialized on the
                # single handle, so concurrent threads can never interleave.
                await anyio.to_thread.run_sync(handle.write, chunk)
                done += len(chunk)
                if on_progress is not None:
                    on_progress(len(chunk), progress_total)
        finally:
            # Close SYNCHRONOUSLY: a thread-pool close can be skipped when
            # the task is cancelled (and on Windows an open handle blocks
            # every later delete/rename of the part file).
            try:
                handle.close()
            except Exception:
                logger.debug("suppressed")
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
                    try:
                        os.unlink(tmp)
                    except OSError:
                        logger.debug("suppressed")
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
