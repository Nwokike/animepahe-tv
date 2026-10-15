"""Durable app state: search history + continue watching.

Per the storage contract (see `.flet/README.md`), durable data lives in
`FLET_APP_STORAGE_DATA` — it survives app updates and is not purgeable by
the OS, unlike the regenerable cache tier. That is exactly what history
and resume positions need.

Writes are atomic and durable: a temp file beside the target, f.flush()
and os.fsync(f.fileno()) to ensure bits reach disk, then `os.replace`
(renaming across directories can fail across filesystems).
"""

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time

from core.artwork import LANDSCAPE, PORTRAIT, artwork_default_key
from core.storage import app_data_dir

logger = logging.getLogger(__name__)

SEARCH_HISTORY_LIMIT = 20
CONTINUE_WATCHING_LIMIT = 20


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
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class JsonStore:
    """A single JSON document with typed sections and atomic writes."""

    def __init__(self, filename: str = "app-state.json"):
        self.path = os.path.join(app_data_dir(), filename)
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
    # Generic key/value settings (presentation defaults the player reads
    # at construction time: subtitle size, aspect fit)
    # ------------------------------------------------------------------

    async def save_setting(self, key: str, value) -> None:
        async with self._lock:
            await self._ensure_loaded()
            settings = self._data.get("settings")
            if not isinstance(settings, dict):
                settings = {}
                self._data["settings"] = settings
            settings[key] = value
            self._dirty = True
            await self._flush()

    def get_setting(self, key: str, default=None):
        """Sync read — the player builds its video control (and reads
        these) inside a plain constructor, before any coroutine runs.

        Startup has already loaded the document by then; the cold read
        below only covers a first-run open and cannot interleave with a
        write, because a sync call never yields to the loop.
        """
        if not self._loaded:
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self._data = raw
                self._loaded = True
            except (OSError, ValueError):
                self._data = {}
        settings = self._data.get("settings")
        if not isinstance(settings, dict):
            return default
        value = settings.get(key)
        return default if value is None else value

    # ------------------------------------------------------------------
    # Search history (most-recent-first, deduped, capped)
    # ------------------------------------------------------------------

    async def get_search_history(self) -> list[dict]:
        """Recent SEARCHES as {title, session, ts} — newest first.

        `title` is the anime the user actually opened (e.g. "Black Clover
        Season 1"), not the string they typed, so re-opening a result is one
        tap. Rows saved before this shape (bare strings) migrate on read.
        """
        history = await self.section("search_history", [])
        if not isinstance(history, list):
            return []
        rows: list[dict] = []
        for item in history:
            if isinstance(item, dict) and item.get("title"):
                rows.append(
                    {
                        "title": str(item["title"])[:200],
                        "session": str(item.get("session") or "")[:120],
                        "ts": float(item.get("ts") or 0),
                    }
                )
            elif isinstance(item, str) and item.strip():
                # v1 rows: the typed query, no session to open directly.
                rows.append({"title": item.strip()[:200], "session": "", "ts": 0.0})
        return rows

    async def add_search(self, query: str) -> None:
        """Record a typed query (fallback when nothing was opened)."""
        query = (query or "").strip()
        if not query:
            return
        await self.add_search_selection(query, "")

    async def add_search_selection(self, title: str, session: str = "") -> None:
        """Record the ANIME that was opened from search, MRU-deduped."""
        title = (title or "").strip()
        if not title:
            return
        history = await self.get_search_history()
        if session:
            history = [r for r in history if r.get("session") != session]
        else:
            history = [
                r for r in history if r.get("title", "").lower() != title.lower()
            ]
        history.insert(
            0, {"title": title[:200], "session": session[:120], "ts": time.time()}
        )
        del history[SEARCH_HISTORY_LIMIT:]
        await self.put_section("search_history", history)

    async def remove_search(self, title: str, session: str = "") -> None:
        history = await self.get_search_history()
        history = [
            r
            for r in history
            if not (r.get("title") == title and r.get("session") == session)
        ]
        await self.put_section("search_history", history)

    async def clear_search_history(self) -> list[dict]:
        """Clear and return the cleared rows — the Undo restores exactly
        what was there (deep copy, MRU order intact)."""
        history = await self.get_search_history()
        await self.put_section("search_history", [])
        return [dict(r) for r in history]

    async def restore_search_history(self, rows: list[dict]) -> None:
        """Undo a clear: put the exact rows back."""
        rows = [r for r in rows if isinstance(r, dict) and r.get("title")]
        await self.put_section("search_history", rows[:SEARCH_HISTORY_LIMIT])

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
                key=lambda kv: kv[1].get("timestamp", 0)
                if isinstance(kv[1], dict)
                else 0,
                reverse=True,
            )
        )
        for stale in list(entries.keys())[CONTINUE_WATCHING_LIMIT:]:
            entries.pop(stale, None)
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
        # The row travels whole — the rate (and any later fields) ride
        # with it instead of being rebuilt away here.
        return entry

    async def save_position(
        self,
        episode_session: str,
        position: float,
        duration: float | None,
        rate: float | None = None,
    ) -> None:
        if not episode_session:
            return
        positions = await self.section("positions", {})
        if not isinstance(positions, dict):
            positions = {}
        row = {
            "position": round(float(position), 2),
            "duration": round(float(duration), 2) if duration else None,
            "timestamp": time.time(),
        }
        # The chosen playback speed rides the resume record so the next
        # open continues at the same rate (additive; absent = 1.0).
        if rate:
            row["rate"] = round(float(rate), 2)
        # An episode watched to (nearly) the end is not resumable — drop it.
        if duration and position >= duration - self.RESUME_END_SKIP_SECONDS:
            positions.pop(episode_session, None)
        else:
            positions[episode_session] = row
        await self.put_section("positions", positions)

    # ------------------------------------------------------------------
    # Cloudflare clearance (durable — survives reboots; this is what makes
    # a returning user's boot skip the Turnstile webview entirely)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Cloudflare clearance (durable — survives reboots; this is what makes
    # a returning user's boot skip the Turnstile webview entirely).
    # Host-keyed: each walled host keeps its own clearance, so solving
    # one never invalidates another's.
    # ------------------------------------------------------------------

    _DEFAULT_CLEARANCE_HOST = "animepahe"

    async def get_clearance(self, host: str | None = None) -> dict | None:
        host = host or self._DEFAULT_CLEARANCE_HOST
        entry = await self.section("clearance", None)
        if not isinstance(entry, dict):
            return None
        # Pre-host shape: a single flat record, which was animepahe's.
        if "cookies" in entry or "user_agent" in entry:
            return entry if host == self._DEFAULT_CLEARANCE_HOST else None
        keyed = entry.get(host)
        return keyed if isinstance(keyed, dict) and keyed.get("cookies") else None

    async def save_clearance(
        self, cookies: str, user_agent: str, host: str | None = None
    ) -> None:
        if not cookies:
            return
        host = host or self._DEFAULT_CLEARANCE_HOST
        existing = await self.section("clearance", None)
        keyed: dict = {}
        if isinstance(existing, dict) and "cookies" not in existing:
            keyed = dict(existing)
        elif isinstance(existing, dict):
            # Migrate the flat record into the keyed shape under its host.
            keyed = {self._DEFAULT_CLEARANCE_HOST: dict(existing)}
        keyed[host] = {
            "cookies": cookies,
            "user_agent": user_agent,
            "timestamp": time.time(),
        }
        await self.put_section("clearance", keyed)

    async def clear_clearance(self, host: str | None = None) -> None:
        """Drop one host's clearance (or all of them when unset)."""
        host = host or self._DEFAULT_CLEARANCE_HOST
        existing = await self.section("clearance", None)
        if not isinstance(existing, dict):
            return
        if "cookies" in existing or "user_agent" in existing:
            # The pre-host flat record is animepahe's.
            if host == self._DEFAULT_CLEARANCE_HOST:
                await self.put_section("clearance", None)
            return
        existing.pop(host, None)
        await self.put_section("clearance", existing or None)

    # ------------------------------------------------------------------
    # Theme mode (durable — the 3-way cycle must survive a restart)
    # ------------------------------------------------------------------

    async def get_theme_mode(self) -> str | None:
        mode = await self.section("theme_mode", None)
        return mode if isinstance(mode, str) else None

    async def save_theme_mode(self, mode: str) -> None:
        await self.put_section("theme_mode", mode)

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

    # ------------------------------------------------------------------
    # Favorites — WHOLE anime, keyed by anime_session (an episode session
    # is never a favorite). Ordered newest-first at read time.
    # ------------------------------------------------------------------

    FOLLOWS_LIMIT = 200

    async def get_follows(self) -> dict:
        """Follows (was FAVORITES — the 1.0.4 file's section is migrated
        on read so nobody's library is lost)."""
        async with self._lock:
            await self._ensure_loaded()
            entries = self._data.get("follows")
            if entries is None:
                legacy = self._data.get("favorites")
                if isinstance(legacy, dict):
                    # One-time migration: the 1.0.4 file's section becomes
                    # follows and the old name is retired on disk.
                    self._data["follows"] = legacy
                    self._data.pop("favorites", None)
                    self._dirty = True
                    await self._flush()
                    return dict(legacy)
                return {}
            return dict(entries) if isinstance(entries, dict) else {}

    async def is_following(self, anime_session: str) -> bool:
        if not anime_session:
            return False
        return anime_session in await self.get_follows()

    async def get_follow_progress(self, anime_session: str) -> int:
        """The highest episode number already notified for a follow."""
        row = (await self.get_follows()).get(anime_session) or {}
        try:
            return int(float(row.get("last_seen_episode") or 0))
        except (TypeError, ValueError):
            return 0

    async def set_follow_progress(self, anime_session: str, episode: int) -> None:
        """Record the newest notified episode so a re-check doesn't
        re-alert (additive — rows without it read as 0)."""
        follows = await self.get_follows()
        row = follows.get(anime_session)
        if row is None:
            return
        row["last_seen_episode"] = int(episode)
        await self.put_section("follows", follows)

    async def add_follow(self, row: dict) -> None:
        anime_session = row.get("anime_session")
        if not anime_session:
            return
        follows = await self.get_follows()
        # Never persist a base64 data: URI — one poster bloats the store.
        poster = row.get("poster") or ""
        if poster.startswith("data:"):
            poster = ""
        entry = dict(row)
        entry["poster"] = poster
        entry["anime_session"] = anime_session
        entry["added_at"] = time.time()
        follows[anime_session] = entry
        if len(follows) > self.FOLLOWS_LIMIT:
            oldest = sorted(
                follows.items(),
                key=lambda kv: kv[1].get("added_at", 0)
                if isinstance(kv[1], dict)
                else 0,
            )
            for session, _ in oldest[: len(follows) - self.FOLLOWS_LIMIT]:
                follows.pop(session, None)
        await self.put_section("follows", follows)

    async def remove_follow(self, anime_session: str) -> None:
        follows = await self.get_follows()
        if anime_session in follows:
            follows.pop(anime_session, None)
            await self.put_section("follows", follows)

    async def toggle_follow(self, row: dict) -> bool:
        """Returns the NEW follow state.

        Re-read-after-write: a rapid double-tap asks twice, and the
        second answer must be read from the store as it is NOW, not
        from the answer the first tap produced (the clobber KTV's
        utils/favorites.py fixed)."""
        anime_session = row.get("anime_session")
        if not anime_session:
            return False
        if await self.is_following(anime_session):
            await self.remove_follow(anime_session)
        else:
            await self.add_follow(row)
        return await self.is_following(anime_session)

    # ------------------------------------------------------------------
    # Playback preference: hand streams to KTV Player (the old app's only
    # mode) instead of the in-app player.
    # ------------------------------------------------------------------

    async def get_external_player(self) -> bool:
        return bool(await self.section("external_player", False))

    async def save_external_player(self, enabled: bool) -> None:
        await self.put_section("external_player", bool(enabled))

    # ------------------------------------------------------------------
    # Rewarded-ad early access (episode_key -> unlocked_at timestamp).
    # Rewards are purchasable currency: the row is all the bookkeeping
    # needed, and clearing app data resets it.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Content source (auto vs pinned provider)
    # ------------------------------------------------------------------

    async def get_backend(self) -> str:
        return str(await self.section("backend", "auto"))

    async def save_backend(self, name: str) -> None:
        await self.put_section("backend", str(name or "auto"))

    async def get_artwork_defaults(self) -> dict:
        """Learned shape per backend+surface — what the next launch paints
        before any probe lands. A corrupt value reads as {}."""
        value = await self.section("artwork_defaults", {})
        return value if isinstance(value, dict) else {}

    async def save_artwork_default(self, provider: str, surface: str, mode: str) -> None:
        """Remember what a backend's lists actually detected as.

        Only landscape/portrait are stored; anything else is ignored so a
        bad caller can never poison the first-paint defaults.
        """
        if mode not in (LANDSCAPE, PORTRAIT):
            return
        current = await self.get_artwork_defaults()
        key = artwork_default_key(provider, surface)
        if current.get(key) == mode:
            return
        current[key] = mode
        await self.put_section("artwork_defaults", current)
