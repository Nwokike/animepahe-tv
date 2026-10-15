"""Artwork geometry — the shape layer behind the two grid patterns.

The owner's law (docs/testing-findings.md): every backend shows at least one
image, and every list renders in the shape its own artwork actually is — a
landscape grid for wide stills/banners, a portrait grid for posters. The
screen decides automatically; there is no user option. Nothing crosses
between backends: the decision only ever looks at the selected backend's
own items, and the no-art fallback uses that backend's own series art.

This module is pure stdlib: a header sniffer for the four image formats
these CDNs actually serve (JPEG/PNG/WebP/GIF) plus the decision helpers the
screens call. Remote bytes arrive via services/artwork_probe.py; animepahe's
art arrives as data: URIs and is sniffed locally without any network.
"""

import base64
import binascii
from collections.abc import Mapping, Sequence

__all__ = [
    "DATA_URI_HEAD_CHARS",
    "FALLBACK_MODE",
    "HEAD_LIMIT",
    "LANDSCAPE",
    "PORTRAIT",
    "PROBE_REFERERS",
    "SEED_MODES",
    "artwork_default_key",
    "decide_mode",
    "default_mode",
    "majority_shape",
    "probe_referer",
    "shape_from_bytes",
    "shape_from_data_uri",
    "shape_of",
    "sniff_dimensions",
]

LANDSCAPE = "landscape"
PORTRAIT = "portrait"

# Read caps: enough for every header these formats need (JPEG SOF usually
# lands inside the first 4 KiB even with a big EXIF block; PNG/WebP/GIF are
# fixed-offset). 64 KiB is the probe's per-request ceiling.
HEAD_LIMIT = 65536
DATA_URI_HEAD_CHARS = 65532  # 4-base64-chars per 3 bytes, divisible by 4

# Vote rules for a screen-level decision: at least 3 parsed shapes and a
# 60% supermajority, otherwise the learned/seed default stands.
MIN_VOTES = 3
MAJORITY = 0.6

# Static first-paint seeds, per provider and surface, from the certified
# backend maps plus live probes (anikato posters 266x400 portrait;
# kusonime featured 1919x1079 and kayoanime 1280x720 landscape; animepahe
# stills landscape + posters portrait). Detection refines these within a
# second and the learned default remembers the result across launches.
SEED_MODES: dict[str, dict[str, str]] = {
    "animepahe": {
        "latest": LANDSCAPE,
        "search": PORTRAIT,
        "episodes": LANDSCAPE,
    },
    "anikato": {
        "latest": PORTRAIT,
        "search": PORTRAIT,
        "discover": PORTRAIT,
        "episodes": PORTRAIT,
    },
    "kusonime": {
        "latest": LANDSCAPE,
        "search": LANDSCAPE,
        "episodes": LANDSCAPE,
    },
    "animeout": {
        "latest": LANDSCAPE,
        "search": LANDSCAPE,
        "episodes": LANDSCAPE,
    },
    "kayoanime": {
        "latest": LANDSCAPE,
        "search": LANDSCAPE,
        "episodes": LANDSCAPE,
    },
}

# Unknown provider: keep the geometry the app shipped with (nothing looks
# worse than today before detection lands).
FALLBACK_MODE: dict[str, str] = {
    "latest": LANDSCAPE,
    "search": PORTRAIT,
    "discover": PORTRAIT,
    "episodes": LANDSCAPE,
}

# Image hosts are hotlink-tolerant generally, but these referers are the
# sites' own base URLs and cost nothing.
PROBE_REFERERS: dict[str, str] = {
    "animepahe": "https://animepahe.com/",
    "anikato": "https://anikototv.to/",
    "kusonime": "https://kusonime.com/",
    "animeout": "https://www.animeout.xyz/",
    "kayoanime": "https://kayoanime.com/",
}

_SOF_MARKERS = frozenset(
    (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)
)


def sniff_dimensions(buf: bytes) -> tuple[int, int] | None:
    """(width, height) from the leading bytes of a JPEG/PNG/WebP/GIF, else None.

    Never raises: any malformed input simply yields None (the caller keeps
    its default shape).
    """
    if len(buf) >= 24 and buf[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(buf[16:20], "big"), int.from_bytes(buf[20:24], "big")

    if len(buf) >= 4 and buf[:2] == b"\xff\xd8":
        i = 2
        while i + 4 <= len(buf):
            if buf[i] != 0xFF:
                i += 1
                continue
            marker = buf[i + 1]
            if marker == 0xFF:  # fill byte
                i += 1
                continue
            if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # standalones, no length
                i += 2
                continue
            seg_len = int.from_bytes(buf[i + 2 : i + 4], "big")
            if marker in _SOF_MARKERS and i + 9 <= len(buf):
                height = int.from_bytes(buf[i + 5 : i + 7], "big")
                width = int.from_bytes(buf[i + 7 : i + 9], "big")
                return width, height
            if marker == 0xDA:  # scan data starts; no SOF seen
                return None
            i += 2 + seg_len
        return None

    if len(buf) >= 16 and buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        fourcc = buf[12:16]
        if fourcc == b"VP8X" and len(buf) >= 30:
            width = 1 + int.from_bytes(buf[24:27], "little")
            height = 1 + int.from_bytes(buf[27:30], "little")
            return width, height
        if fourcc == b"VP8 " and len(buf) >= 30:
            width = int.from_bytes(buf[26:28], "little") & 0x3FFF
            height = int.from_bytes(buf[28:30], "little") & 0x3FFF
            return width, height
        if fourcc == b"VP8L" and len(buf) >= 25:
            bits = int.from_bytes(buf[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height
        return None

    if len(buf) >= 10 and buf[:6] in (b"GIF87a", b"GIF89a"):
        return int.from_bytes(buf[6:8], "little"), int.from_bytes(buf[8:10], "little")

    return None


def shape_of(width: int, height: int) -> str | None:
    """Classify dimensions; near-square abstains (it fits either grid)."""
    if width <= 0 or height <= 0:
        return None
    ratio = width / height
    if ratio > 1.15:
        return LANDSCAPE
    if ratio < 0.87:
        return PORTRAIT
    return None


def shape_from_bytes(buf: bytes) -> str | None:
    dims = sniff_dimensions(buf)
    return shape_of(*dims) if dims else None


def shape_from_data_uri(src: str) -> str | None:
    """Shape from a ``data:image/...;base64,`` URI without any network.

    Decodes only the leading chunk — enough for every header format — so a
    500 KB base64 poster costs a few microseconds.
    """
    if not src or not src.startswith("data:"):
        return None
    head, sep, payload = src.partition(",")
    if not sep or "base64" not in head:
        return None
    try:
        raw = base64.b64decode(payload[:DATA_URI_HEAD_CHARS])
    except (binascii.Error, ValueError):
        return None
    return shape_from_bytes(raw)


def majority_shape(shapes: Sequence[str | None]) -> str | None:
    """The supermajority shape among parsed votes, or None to keep the default."""
    votes = [s for s in shapes if s in (LANDSCAPE, PORTRAIT)]
    if len(votes) < MIN_VOTES:
        return None
    for candidate in (LANDSCAPE, PORTRAIT):
        if votes.count(candidate) / len(votes) >= MAJORITY:
            return candidate
    return None


def artwork_default_key(provider: str, surface: str) -> str:
    return f"{provider}:{surface}"


def default_mode(provider: str, surface: str, learned: Mapping[str, str] | None = None) -> str:
    """First-paint mode: learned > seed > the app's shipped geometry."""
    if learned:
        remembered = learned.get(artwork_default_key(provider, surface))
        if remembered in (LANDSCAPE, PORTRAIT):
            return remembered
    seed = SEED_MODES.get(provider, {}).get(surface)
    if seed in (LANDSCAPE, PORTRAIT):
        return seed
    return FALLBACK_MODE.get(surface, LANDSCAPE)


def decide_mode(
    shapes: Sequence[str | None],
    provider: str,
    surface: str,
    learned: Mapping[str, str] | None = None,
) -> str:
    """The screen-level mode: a detected supermajority wins, else the default."""
    detected = majority_shape(shapes)
    if detected:
        return detected
    return default_mode(provider, surface, learned)


def probe_referer(provider: str) -> str | None:
    return PROBE_REFERERS.get(provider)
