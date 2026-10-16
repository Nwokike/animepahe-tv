"""Storage tiers — one resolver for the three places flet gives an app.

The `.flet/README.md` contract (flet's own canon): **data** is durable and
survives updates (the store, downloads); **cache** is regenerable and the OS
may purge it on a device under storage pressure (TTL entries, poster
thumbnails); **temp** is throwaway scratch (flet points `tempfile` there,
and our atomic writes deliberately place their scratch file beside the
target instead, so the final `os.replace` can never cross filesystems).

Every caller resolves through here so the tiers cannot drift into different
layouts again. In a packaged app `FLET_APP_STORAGE_*` are always set; when
they are not (plain `python src/main.py`, or an import from elsewhere) the
fallback is the same `.flet/storage/<tier>` tree `flet run` uses — under the
app namespace, so both ways of running share one dev store — resolved from
the repo root, never from the current directory.
"""

import math
import os

APP_NAMESPACE = "animepahe"

_DATA_ENV = "FLET_APP_STORAGE_DATA"
_CACHE_ENV = "FLET_APP_STORAGE_CACHE"
_TEMP_ENV = "FLET_APP_STORAGE_TEMP"

__all__ = [
    "APP_NAMESPACE",
    "app_cache_dir",
    "app_data_dir",
    "cache_dir",
    "data_dir",
    "dir_size",
    "format_size",
    "temp_dir",
]


def _repo_root() -> str:
    # src/core/storage.py -> core -> src -> repo root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve(env_name: str, tier: str) -> str:
    base = os.getenv(env_name)
    if base:
        return base
    return os.path.join(_repo_root(), ".flet", "storage", tier)


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def data_dir() -> str:
    """The durable tier itself (env first, dev fallback second)."""
    return _ensure(_resolve(_DATA_ENV, "data"))


def cache_dir() -> str:
    """The regenerable tier itself — purgeable by the OS on a device."""
    return _ensure(_resolve(_CACHE_ENV, "cache"))


def temp_dir() -> str:
    """Throwaway scratch. Available for transient files that need a path."""
    return _ensure(_resolve(_TEMP_ENV, "temp"))


def app_data_dir(*parts: str) -> str:
    """This app's namespace inside the durable tier (store, downloads)."""
    return _ensure(os.path.join(data_dir(), APP_NAMESPACE, *parts))


def app_cache_dir(*parts: str) -> str:
    """This app's namespace inside the regenerable tier (TTL cache, posters)."""
    return _ensure(os.path.join(cache_dir(), APP_NAMESPACE, *parts))


def dir_size(path: str) -> int:
    """Total bytes under a directory, never raising (0 for a missing one).

    Used by Settings to show what the cache tier actually occupies — the
    app owns its own cleanup (the OS may purge the tier at any time, and
    Android's guidance is explicit that an app must not rely on it).
    """
    total = 0
    for root, _dirs, files in os.walk(path) if os.path.isdir(path) else ():
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def format_size(num_bytes: int) -> str:
    """A compact human size: "0 B", "512 KB", "1.4 MB".

    Garbage and negatives clamp to "0 B" (the ffmpeg app's format_bytes
    discipline) — a size row must never render "nan" or "-3 MB".
    """
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    if math.isnan(size) or math.isinf(size) or size < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} GB"
