"""Offline episode downloads.

Layout follows the storage contract: episodes live under
``$FLET_APP_STORAGE_DATA/animepahe/downloads/<anime>/<episode>/`` (app-private
storage — no Android permissions needed, survives updates, removed on
uninstall).

Format: one variant's media playlist plus all its segments, then a local
``index.m3u8`` whose segment URIs are rewritten to relative filenames (and
key URIs to downloaded key files). No ffmpeg, no concatenation — a
half-written episode is never marked complete, so it can never be opened as
a finished download.

Resume: per-segment ``.part`` files plus a ``manifest.json``. Restarting a
job skips complete segments and continues partials from their byte offset
with a ``Range`` request; cancelling leaves the partials on disk so a later
resume works.
"""

import asyncio
import json
import logging
import os
import re
import time

import primp

logger = logging.getLogger(__name__)

PARALLEL_SEGMENTS = 6
import anyio

SEGMENT_TIMEOUT = 30
PLAYLIST_TIMEOUT = 15
# A whole-file download is not a segment: the timeout must cover the
# full response body, not a 30s segment. User aborts still arrive via
# the cancel event (and Cancel on a stuck transfer via aclose).
FILE_TIMEOUT = 600
# Concurrent direct-file downloads — the rest queue on the limiter.
MAX_FILE_DOWNLOADS = 2

_ERR_THREAD = None
_STATE_PARTIAL = "partial"
_STATE_COMPLETE = "complete"


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
    pending_key = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#EXT-X-KEY") and "URI=" in stripped:
            # #EXT-X-KEY:METHOD=AES-128,URI="https://.../key.bin"
            match = re.search(r'URI="([^"]+)"', stripped)
            if match:
                key_name = os.path.basename(match.group(1).split("?")[0]) or "key.bin"
                rewritten = re.sub(
                    r'URI="[^"]+"', f'URI="{segment_dir_name}/{key_name}"', stripped
                )
                out.append(rewritten)
                pending_key = True
                continue
        if (
            stripped
            and not stripped.startswith("#")
            and (pending_key or count == 0 or True)
        ):
            # A media segment line: last non-comment line wins.
            uri = stripped.split("?")[0]
            name = os.path.basename(uri)
            if name and re.search(r"\.(ts|aac|mp4|m4s|vtt)(\.|$)", name, re.IGNORECASE):
                out.append(f"{segment_dir_name}/{name}")
                count += 1
                pending_key = False
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


class DownloadManager:
    """Owns download jobs: one asyncio task per episode, shared primp client."""

    def __init__(self, store=None, downloads_dir: str | None = None):
        # A queue of direct-file downloads shares one limiter so a big
        # batch can't starve the app's own fetches (the UI, the router).
        self._file_limiter = anyio.CapacityLimiter(MAX_FILE_DOWNLOADS)
        self._store = store
        self.downloads_dir = downloads_dir or self._default_dir()
        self._jobs: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel: dict[str, asyncio.Event] = {}
        self._client: primp.AsyncClient | None = None
        self._progress: dict[str, dict] = {}
        self.on_progress = None  # callable(episode_session, dict)

    @staticmethod
    def _default_dir() -> str:
        base = os.getenv("FLET_APP_STORAGE_DATA")
        root = os.path.join(base, "animepahe", "downloads") if base else os.path.join(
            "storage", "data", "animepahe", "downloads"
        )
        os.makedirs(root, exist_ok=True)
        return root

    def _get_client(self) -> primp.AsyncClient:
        if self._client is None:
            self._client = primp.AsyncClient(
                timeout=SEGMENT_TIMEOUT, impersonate="chrome"
            )
        return self._client

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    @property
    def active_jobs(self) -> list[str]:
        return list(self._tasks.keys())

    def get_progress(self, episode_session: str) -> dict | None:
        return self._progress.get(episode_session)

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
        job_dir = os.path.join(
            self.downloads_dir,
            metadata.get("anime_session", "unknown"),
            episode_session,
        )
        os.makedirs(job_dir, exist_ok=True)
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if manifest.get("state") == _STATE_COMPLETE:
            return
        manifest.update(
            {
                "m3u8_url": m3u8_url,
                "headers": headers,
                "state": _STATE_PARTIAL,
                "metadata": metadata,
            }
        )
        self._write_manifest(manifest_path, manifest)
        self._jobs[episode_session] = {"dir": job_dir, "manifest": manifest_path}
        cancel = asyncio.Event()
        self._cancel[episode_session] = cancel
        self._progress[episode_session] = {"done": 0, "total": 0, "bytes": 0}
        task = asyncio.create_task(
            self._run(episode_session, m3u8_url, headers, metadata, job_dir, cancel),
            name=f"download-{episode_session}",
        )
        self._tasks[episode_session] = task
        task.add_done_callback(lambda t: self._on_done(episode_session))

    async def detect_kind(self, url: str, headers: dict) -> str:
        """What the resolved URL actually is: an HLS playlist or a file.

        The peek is the URL's own first bytes — never the provider's
        name and never the extension. 'hls' -> segment download; 'file'
        -> one range-resumed file. Everything else is a file: if it
        doesn't declare EXT-X-M3U, there is nothing to segment."""
        client = self._get_client()
        try:
            resp = await client.get(url, headers=headers, stream=True, timeout=PLAYLIST_TIMEOUT)
            if url.split("?")[0].endswith(".m3u8") or resp.headers.get(
                "content-type", ""
            ).startswith("application/vnd.apple.mpegurl"):
                await resp.aclose()
                return "hls"
            try:
                first = await resp.anext()
            except StopAsyncIteration:
                first = b""
            finally:
                await resp.aclose()
            if b"#EXTM3U" in (first or b"")[:1024]:
                return "hls"
        except Exception as ex:
            logger.warning("download shape peek failed for %s: %s", url, ex)
        return "file"

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
        job_dir = os.path.join(
            self.downloads_dir,
            metadata.get("anime_session", "unknown"),
            episode_session,
        )
        os.makedirs(job_dir, exist_ok=True)
        manifest_path = os.path.join(job_dir, "manifest.json")
        manifest = self._read_manifest(manifest_path)
        if manifest.get("state") == _STATE_COMPLETE:
            return
        manifest.update(
            {
                "url": url,
                "headers": headers,
                "state": _STATE_PARTIAL,
                "metadata": metadata,
            }
        )
        self._write_manifest(manifest_path, manifest)
        self._jobs[episode_session] = {"dir": job_dir, "manifest": manifest_path}
        cancel = asyncio.Event()
        self._cancel[episode_session] = cancel
        self._progress[episode_session] = {"done": 0, "total": 0, "bytes": 0}
        task = asyncio.create_task(
            self._run_direct(episode_session, url, headers, metadata, job_dir, cancel),
            name=f"download-{episode_session}",
        )
        self._tasks[episode_session] = task
        task.add_done_callback(lambda t: self._on_done(episode_session))

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
        ext = os.path.splitext(url.split("?")[0])[1] or ".mkv"
        final_path = os.path.join(job_dir, f"file{ext}")
        part_path = f"{final_path}.part"
        progress = self._progress[episode_session]
        have = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        progress["bytes"] = have
        on_progress = getattr(self, "on_progress", None)

        def _chunk(n: int):
            progress["bytes"] = have + n if not progress["done"] else progress["bytes"] + n
            progress["done"] = 1
            if on_progress is not None:
                try:
                    on_progress(episode_session, progress["bytes"], 0)
                except Exception:
                    pass

        try:
            async with self._file_limiter:
                ok = await self._download_file(
                    url, headers, part_path, final_path, on_progress=_chunk, cancel=cancel
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
            if not os.path.exists(os.path.join(job_dir, "manifest.json")) or (
                self._read_manifest(manifest_path).get("state") != _STATE_COMPLETE
            ):
                self._write_manifest(
                    manifest_path,
                    {
                        "url": url,
                        "headers": headers,
                        "state": _STATE_PARTIAL,
                        "metadata": metadata,
                    },
                )
        if not ok:
            # Cancelled mid-file: the partial stays on disk (resumable).
            return
        size_bytes = os.path.getsize(final_path)
        if on_progress is not None:
            try:
                on_progress(episode_session, size_bytes, size_bytes)
            except Exception:
                pass
        self._write_manifest(
            os.path.join(job_dir, "manifest.json"),
            {
                "url": url,
                "headers": headers,
                "state": _STATE_COMPLETE,
                "file": final_path,
                "metadata": metadata,
            },
        )
        if self._store is not None:
            row = dict(metadata)
            row.update(
                {
                    "state": _STATE_COMPLETE,
                    "file": final_path,
                    "size_bytes": size_bytes,
                    "completed_at": time.time(),
                }
            )
            await self._store.save_download(episode_session, row)
        self._progress.pop(episode_session, None)
        logger.info("download complete (direct): %s (%d bytes)", episode_session, size_bytes)

    def cancel(self, episode_session: str):
        cancel = self._cancel.get(episode_session)
        if cancel:
            cancel.set()

    def _on_done(self, episode_session: str):
        self._tasks.pop(episode_session, None)
        self._cancel.pop(episode_session, None)

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
                        self._atomic_write(key_path, body)

            # 3. Download segments (resume-aware).
            base_url = media_url.rsplit("/", 1)[0]
            uris = parse_segment_uris(media_text)
            total = len(uris)
            progress = self._progress[episode_session]
            progress["total"] = total

            done = sum(
                1
                for u in uris
                if self._segment_complete(segs_dir, u)
            )
            progress["done"] = done

            queue = [
                (index, u)
                for index, u in enumerate(uris)
                if not self._segment_complete(segs_dir, u)
            ]
            workers = [
                asyncio.create_task(
                    self._worker(
                        queue, base_url, headers, segs_dir, progress, episode_session, cancel
                    )
                )
                for _ in range(min(PARALLEL_SEGMENTS, max(1, len(queue))))
            ]
            await asyncio.gather(*workers)
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
                    "state": _STATE_COMPLETE,
                    "segments": total,
                    "completed_at": time.time(),
                }
            )
            self._write_manifest(manifest_path, manifest)
            if self._store is not None:
                row = dict(manifest.get("metadata") or metadata)
                row.update(
                    {
                        "state": _STATE_COMPLETE,
                        "playlist": index_path,
                        "size_bytes": sum(
                            os.path.getsize(os.path.join(segs_dir, f))
                            for f in os.listdir(segs_dir)
                            if os.path.isfile(os.path.join(segs_dir, f))
                        ),
                        "completed_at": time.time(),
                    }
                )
                await self._store.save_download(episode_session, row)
            self._progress.pop(episode_session, None)
            logger.info("download complete: %s (%d segments)", episode_session, total)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.warning("download failed for %s: %s", episode_session, ex)
            if self._store is not None:
                await self._store.save_download_error(episode_session, str(ex))
        finally:
            manifest_path = os.path.join(job_dir, "manifest.json")
            manifest = self._read_manifest(manifest_path)
            if manifest.get("state") != _STATE_COMPLETE:
                manifest["state"] = _STATE_PARTIAL
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
                logger.warning("segment %s failed: %s", name, ex)
                # Put it back for the next pass; a later retry can pick it up.
                queue.append((index, uri))
                continue
            progress["done"] += 1
            if self.on_progress is not None:
                try:
                    self.on_progress(episode_session, dict(progress))
                except Exception:
                    pass

    async def _resolve_playlist(self, url: str, headers: dict) -> tuple[str, str]:
        """Return the media playlist URL + body (top variant for a master)."""
        body = await self._get_text(url, headers)
        if not body:
            return url, ""
        if "#EXT-X-STREAM-INF" not in body:
            return url, body
        variants = []
        for line in body.splitlines():
            if line and not line.startswith("#"):
                variants.append(line)
        if not variants:
            return url, body
        top = variants[-1]
        top_url = top if top.startswith("http") else url.rsplit("/", 1)[0] + "/" + top
        media = await self._get_text(top_url, headers)
        return top_url, media or ""

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
        mode = "ab" if have and resp.status_code == 206 else "wb"
        done = have

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
        await anyio.to_thread.run_sync(os.replace, part_path, final_path)
        return True

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_complete(segs_dir: str, uri: str) -> bool:
        name = f"-" + os.path.basename(uri.split("?")[0])
        for candidate in os.listdir(segs_dir) if os.path.isdir(segs_dir) else []:
            if candidate.endswith(name):
                return True
        return False

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
        DownloadManager._atomic_write_text(
            path, json.dumps(manifest, indent=2, default=str)
        )

    @staticmethod
    def _atomic_write_text(path: str, text: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    @staticmethod
    def _atomic_write(path: str, data: bytes) -> None:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
