"""Storage tiers — env first, .flet dev fallback second, one layout for all.

Per `.flet/README.md`: data is durable, cache is regenerable/purgeable, temp
is throwaway. These tests pin that every consumer (store, TTL cache,
downloads, poster cache) resolves through core.storage with the same
namespace, and that the fallback never depends on the current directory.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import storage
from core.storage import (
    APP_NAMESPACE,
    app_cache_dir,
    app_data_dir,
    cache_dir,
    data_dir,
    temp_dir,
)
from services.cache import Cache
from services.downloads import DownloadManager
from services.store import JsonStore


def test_env_wins_for_every_tier(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "c"))
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path / "t"))
    assert data_dir() == str(tmp_path / "d")
    assert cache_dir() == str(tmp_path / "c")
    assert temp_dir() == str(tmp_path / "t")
    downloads = app_data_dir("downloads")
    assert downloads == os.path.join(str(tmp_path / "d"), APP_NAMESPACE, "downloads")
    assert os.path.isdir(downloads)


def test_fallback_is_the_flet_dev_tree_resolved_from_the_repo_root(monkeypatch, tmp_path):
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.delenv("FLET_APP_STORAGE_CACHE", raising=False)
    monkeypatch.delenv("FLET_APP_STORAGE_TEMP", raising=False)
    monkeypatch.chdir(tmp_path)  # must never depend on the current directory
    root = storage._repo_root()
    assert data_dir() == os.path.join(root, ".flet", "storage", "data")
    assert cache_dir() == os.path.join(root, ".flet", "storage", "cache")
    assert temp_dir() == os.path.join(root, ".flet", "storage", "temp")
    assert app_cache_dir("posters") == os.path.join(
        root, ".flet", "storage", "cache", APP_NAMESPACE, "posters"
    )


def test_consumers_share_the_same_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path))
    namespace = os.path.join(str(tmp_path), APP_NAMESPACE)
    assert JsonStore(filename="x.json").path == os.path.join(namespace, "x.json")
    assert Cache(filename="t.json").path == os.path.join(namespace, "t.json")
    assert DownloadManager._default_dir() == os.path.join(namespace, "downloads")
