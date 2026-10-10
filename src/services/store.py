"""Durable app state: search history + continue watching.

Per the storage contract (see `.flet/README.md`), durable data lives in
`FLET_APP_STORAGE_DATA` — it survives app updates and is not purgeable by
the OS, unlike the regenerable cache tier. That is exactly what history
and resume positions need.

Writes are atomic and coalesced: a temp file beside the target, then
`os.replace` (renaming across directories can fail across filesystems),
with a short debounce so bursts of writes flush once.
"""

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)

_DATA_ENV = "FLET_APP_STORAGE_DATA"

SEARCH_HISTORY_LIMIT = 20
CONTINUE_WATCHING_LIMIT = 20


def _data_dir() -> str:
    base = os.getenv(_DATA_ENV)
    path = os.path.join(base, "animepahe") if base else os.path.join("storage", "data")
    os.makedirs(path, exist_ok=True)
    return path


_default_store: "JsonStore | None" = None


def get_store() -> "JsonStore":
    """Process-wide store singleton — every writer must share one instance."""
    global _default_store
    if _default_store is None:
        _default_store = JsonStore()
    return _default_store


def _atomic_write_json(path: str, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class JsonStore:
    """A single JSON document with typed sections and atomic writes."""

    def __init__(self, filename: str = "app-state.json"):
        self.path = os.path.join(_data_dir(), filename)
        self._data: dict = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
        except (OSError, ValueError):
            # First run, or the OS/user cleared app data — start empty.
            self._data = {}

    async def _flush(self) -> None:
        if not self._dirty:
            return
        _atomic_write_json(self.path, self._data)
        self._dirty = False

    async def section(self, name: str, default):
        async with self._lock:
            await self._ensure_loaded()
            value = self._data.get(name)
            return default if value is None else value

    async def put_section(self, name: str, value) -> None:
        async with self._lock:
            await self._ensure_loaded()
            self._data[name] = value
            self._dirty = True
            await self._flush()

    # ------------------------------------------------------------------
    # Search history (most-recent-first, deduped, capped)
    # ------------------------------------------------------------------

    async def get_search_history(self) -> list[str]:
        history = await self.section("search_history", [])
        return list(history) if isinstance(history, list) else []

    async def add_search(self, query: str) -> None:
        query = (query or "").strip()
        if not query:
            return
        history = await self.get_search_history()
        if query in history:
            history.remove(query)
        history.insert(0, query)
        del history[SEARCH_HISTORY_LIMIT:]
        await self.put_section("search_history", history)

    async def clear_search_history(self) -> None:
        await self.put_section("search_history", [])

    # ------------------------------------------------------------------
    # Continue watching (keyed by anime session, newest-first read)
    # ------------------------------------------------------------------

    async def get_continue_watching(self) -> dict:
        entries = await self.section("continue_watching", {})
        return entries if isinstance(entries, dict) else {}

    async def record_watch(self, record: dict) -> None:
        key = record.get("anime_session")
        if not key:
            return
        entries = await self.get_continue_watching()
        merged = dict(record)
        merged.setdefault("timestamp", time.time())
        entries[key] = merged
        # Newest first: sort by timestamp, drop the oldest beyond the cap.
        entries = dict(
            sorted(
                entries.items(),
                key=lambda kv: kv[1].get("timestamp", 0),
                reverse=True,
            )
        )
        for stale in list(entries.keys())[CONTINUE_WATCHING_LIMIT:]:
            entries.pop(stale, None)
        await self.put_section("continue_watching", entries)

    async def remove_watch(self, anime_session: str) -> None:
        entries = await self.get_continue_watching()
        if anime_session in entries:
            entries.pop(anime_session, None)
            await self.put_section("continue_watching", entries)

    # ------------------------------------------------------------------
    # Playback positions (keyed by episode session)
    # ------------------------------------------------------------------

    RESUME_MIN_SECONDS = 3
    RESUME_END_SKIP_SECONDS = 5

    async def get_position(self, episode_session: str) -> dict | None:
        positions = await self.section("positions", {})
        if not isinstance(positions, dict):
            return None
        entry = positions.get(episode_session)
        if not isinstance(entry, dict):
            return None
        try:
            position = float(entry.get("position", 0))
            duration = float(entry.get("duration", 0)) or None
        except (TypeError, ValueError):
            return None
        # Skip resume if finished (within 5s of the end) or barely started.
        if position <= self.RESUME_MIN_SECONDS:
            return None
        if duration is not None and position >= duration - self.RESUME_END_SKIP_SECONDS:
            return None
        return {"position": position, "duration": duration}

    async def save_position(self, episode_session: str, position: float, duration: float | None) -> None:
        if not episode_session:
            return
        positions = await self.section("positions", {})
        if not isinstance(positions, dict):
            positions = {}
        # An episode watched to (nearly) the end is not resumable — drop it.
        if duration and position >= duration - self.RESUME_END_SKIP_SECONDS:
            positions.pop(episode_session, None)
        else:
            positions[episode_session] = {
                "position": round(float(position), 2),
                "duration": round(float(duration), 2) if duration else None,
                "timestamp": time.time(),
            }
        await self.put_section("positions", positions)

    # ------------------------------------------------------------------
    # Cloudflare clearance (durable — survives reboots; this is what makes
    # a returning user's boot skip the Turnstile webview entirely)
    # ------------------------------------------------------------------

    async def get_clearance(self) -> dict | None:
        entry = await self.section("clearance", None)
        if not isinstance(entry, dict) or not entry.get("cookies"):
            return None
        return entry

    async def save_clearance(self, cookies: str, user_agent: str) -> None:
        if not cookies:
            return
        await self.put_section(
            "clearance",
            {"cookies": cookies, "user_agent": user_agent, "timestamp": time.time()},
        )

    async def clear_clearance(self) -> None:
        await self.put_section("clearance", None)

    # ------------------------------------------------------------------
    # Offline downloads (one row per episode; progress is throttled in
    # memory by the DownloadManager, not flushed here per segment)
    # ------------------------------------------------------------------

    async def get_downloads(self) -> dict:
        entries = await self.section("downloads", {})
        return entries if isinstance(entries, dict) else {}

    async def save_download(self, episode_session: str, row: dict) -> None:
        entries = await self.get_downloads()
        merged = dict(row)
        merged.setdefault("updated_at", time.time())
        entries[episode_session] = merged
        await self.put_section("downloads", entries)

    async def save_download_error(self, episode_session: str, message: str) -> None:
        entries = await self.get_downloads()
        row = dict(entries.get(episode_session) or {})
        row.update(
            {
                "state": "partial",
                "error": message,
                "updated_at": time.time(),
            }
        )
        entries[episode_session] = row
        await self.put_section("downloads", entries)

    async def remove_download(self, episode_session: str) -> None:
        entries = await self.get_downloads()
        if episode_session in entries:
            entries.pop(episode_session, None)
            await self.put_section("downloads", entries)
