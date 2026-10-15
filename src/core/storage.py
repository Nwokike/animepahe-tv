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
