"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests).

Ordering: newest version FIRST. ``latest_version()`` returns the first
key, and the ``notes_for`` fallback serves the newest entry — never
``reversed()`` on this dict.

House pattern: KTV ``core/changelog.py`` and Sherlock's
``core/changelog.py``; the header version pill opens this dialog, so
users get a changelog on a phone the same way they do in those apps.
"""

from types import MappingProxyType
from typing import Final

CHANGELOG: Final = MappingProxyType(
    {
        "2.0.1": (
            "- Subtitles show on their own again on phones: the source's "
            "default track is re-applied until the player actually loads it, "
            "so AniKato's English subs no longer need a manual switch away "
            "and back\n"
            "- The external player handoff now carries each source's own "
            "headers, so AniKato, Kayoanime and AnimeOut open in KTV Player "
            "instead of only Animepahe"
        ),
        "2.0.0": (
            "- One app, four independent backends: AniKato, AnimeOut, "
            "AnimePahe and Kayoanime, each with its own catalogue, artwork, "
            "playback and Cloudflare story. One is resolved at startup and "
            "the app IS that source; switching re-runs the whole gate\n"
            "- The art decides the shape: grids, shelves and cards sniff "
            "the serving source's artwork and swap between landscape and "
            "portrait on their own\n"
            "- A unified header on every screen — the source switcher, the "
            "health badge, the version pill and the theme cycle — so you can "
            "change backend from anywhere\n"
            "- Downloads repaired: a single file handle per download (the "
            "old per-chunk truncation corrupted every file), honest live "
            "progress, resumable transfers and a failed job that says so\n"
            "- Discover filters are dropdowns generated from the serving "
            "site's own vocabulary, and the grid card size is one shared "
            "contract shared with Home, Search and the episode grid\n"
            "- Safe areas at the shell root, so the header no longer runs "
            "under the status bar\n"
            "- A walled source raises a verification gate instead of an "
            "empty catalogue, and the view a blocked fetch lands on keeps "
            "its back control inside the header"
        ),
    }
)


def latest_version() -> str:
    """The newest version key (the first entry)."""
    for version in CHANGELOG:
        return version
    return ""


def notes_for(version: str) -> str:
    """The entry for `version`; the newest entry when it is unknown (a
    first launch of a new build still deserves a changelog)."""
    if version in CHANGELOG:
        return CHANGELOG[version]
    return CHANGELOG[latest_version()] if CHANGELOG else ""
