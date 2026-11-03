"""TTL cache: a single JSON file in the regenerable storage tier.

Replaces the old SQLite cache. Per the storage contract (see
`.flet/README.md`), cache-class data lives in `FLET_APP_STORAGE_CACHE` —
the OS may purge it on a device under storage pressure, and everything here
is rebuildable (a purged poster is re-fetched, a purged verdict re-probed).

Writes are atomic and coalesced: a temp file beside the target, then
`os.replace` (a rename across two directories can fail when they sit on
different filesystems), and a short debounce so bursts of writes flush once.
"""

import asyncio
import json
import logging
import os
import tempfile
import time

from core.storage import app_cache_dir

logger = logging.getLogger(__name__)


def _read_json_file(path: str):
    """Blocking read for asyncio.to_thread (ASYNC230)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: str, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            logger.debug("suppressed")
        raise


class Cache:
    def __init__(self, filename: str = "ttl-cache.json"):
        self.path = os.path.join(app_cache_dir(), filename)
        self._data: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._sweep_task: asyncio.Task | None = None
        self._dirty = False
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = await asyncio.to_thread(_read_json_file, self.path)
            if isinstance(raw, dict):
                self._data = raw
        except (OSError, ValueError):
            # Missing or corrupt cache is normal (first run, or the OS purged
            # it) — start empty rather than failing.
            self._data = {}

    async def _flush(self) -> None:
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        _atomic_write_json(self.path, self._data)
        self._dirty = False

    async def get(self, key: str) -> str | None:
        async with self._lock:
            await self._ensure_loaded()
            entry = self._data.get(key)
            if entry is None or not isinstance(entry, dict):
                return None
            if entry.get("expires", 0) <= time.time():
                self._data.pop(key, None)
                self._dirty = True
                await self._flush()
                return None
            value = entry.get("value")
            return value if value is None else str(value)

    async def set(self, key: str, value: str, ttl: int = 3600):
        async with self._lock:
            await self._ensure_loaded()
            self._data[key] = {"value": value, "expires": int(time.time()) + ttl}
            self._dirty = True
            await self._flush()

    async def clear(self):
        async with self._lock:
            self._data = {}
            self._dirty = True
            await self._flush()

    async def sweep_expired(self):
        async with self._lock:
            await self._ensure_loaded()
            now = time.time()
            expired = [
                k
                for k, v in self._data.items()
                if not isinstance(v, dict) or v.get("expires", 0) <= now
            ]
            for key in expired:
                self._data.pop(key, None)
            if expired:
                self._dirty = True
                await self._flush()

    async def start_sweep(self, interval: int = 300):
        if self._sweep_task and not self._sweep_task.done():
            self._sweep_task.cancel()
            try:
                await self._sweep_task

            except asyncio.CancelledError:
                logger.debug("suppressed")

        async def _sweep_loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.sweep_expired()

                except Exception:
                    logger.debug("suppressed")

        self._sweep_task = asyncio.create_task(_sweep_loop())

    async def close(self):
        if self._sweep_task:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                logger.debug("suppressed")
            self._sweep_task = None
        async with self._lock:
            await self._flush()
