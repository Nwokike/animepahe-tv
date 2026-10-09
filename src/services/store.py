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
