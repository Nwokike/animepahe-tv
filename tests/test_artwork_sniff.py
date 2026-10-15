"""Artwork geometry tests — the stdlib sniffer and the shape decision table.

The synthetic-header battery is the same one proven against the live CDNs
(anikato portrait / kusonime landscape / kayoanime landscape all parsed
from the first 4 KiB), so these tests pin the exact contract the probe
relies on.
"""

import base64
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.artwork import (
    DATA_URI_HEAD_CHARS,
    FALLBACK_MODE,
    LANDSCAPE,
    PORTRAIT,
    PROBE_REFERERS,
    SEED_MODES,
    artwork_default_key,
    decide_mode,
    default_mode,
    majority_shape,
    probe_referer,
    shape_from_bytes,
    shape_from_data_uri,
    shape_of,
    sniff_dimensions,
)


# ---------------------------------------------------------------- builders --
def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def _jpeg(width: int, height: int, app1_extra: bytes = b"") -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    app1 = b""
    if app1_extra:
        app1 = b"\xff\xe1" + struct.pack(">H", len(app1_extra) + 2) + app1_extra
    sof = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + app0 + app1 + sof + b"\xff\xd9"


def _webp_vp8(width: int, height: int) -> bytes:
    return (
        b"RIFF"
        + (22).to_bytes(4, "little")
        + b"WEBP"
        + b"VP8 "
        + (14).to_bytes(4, "little")
        + b"\x00\x00\x00"
        + b"\x9d\x01\x2a"
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
    )


def _webp_vp8l(width: int, height: int) -> bytes:
    bits = (width - 1) | ((height - 1) << 14)
    return (
        b"RIFF"
        + (17).to_bytes(4, "little")
        + b"WEBP"
        + b"VP8L"
        + (9).to_bytes(4, "little")
        + b"\x2f"
        + bits.to_bytes(4, "little")
    )


def _webp_vp8x(width: int, height: int) -> bytes:
    return (
        b"RIFF"
        + (18).to_bytes(4, "little")
        + b"WEBP"
        + b"VP8X"
        + (10).to_bytes(4, "little")
        + b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )


def _gif(width: int, height: int) -> bytes:
    return b"GIF89a" + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00" * 4


# ------------------------------------------------------------------ sniffer --
def test_png_dimensions():
    assert sniff_dimensions(_png(600, 900)) == (600, 900)
    assert shape_from_bytes(_png(600, 900)) == PORTRAIT


def test_jpeg_dimensions():
    assert sniff_dimensions(_jpeg(1200, 675)) == (1200, 675)
    assert shape_from_bytes(_jpeg(1200, 675)) == LANDSCAPE


def test_jpeg_sof_found_after_a_large_exif_block():
    padded = _jpeg(1200, 675, app1_extra=b"\x00" * 8192)
    assert sniff_dimensions(padded) == (1200, 675)


def test_jpeg_without_sof_abstains():
    # SOI, one segment, then scan data — no frame header anywhere.
    scan = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00" + b"\xff\xda"
    assert sniff_dimensions(scan) is None


def test_webp_all_three_variants():
    assert sniff_dimensions(_webp_vp8(640, 480)) == (640, 480)
    assert sniff_dimensions(_webp_vp8l(360, 640)) == (360, 640)
    assert sniff_dimensions(_webp_vp8x(1919, 1079)) == (1919, 1079)
    assert shape_from_bytes(_webp_vp8l(360, 640)) == PORTRAIT


def test_gif_dimensions():
    assert sniff_dimensions(_gif(300, 200)) == (300, 200)
    assert shape_from_bytes(_gif(300, 450)) == PORTRAIT


def test_junk_and_truncation_never_raise():
    assert sniff_dimensions(b"") is None
    assert sniff_dimensions(b"\x00" * 64) is None
    assert sniff_dimensions(_png(600, 900)[:12]) is None
    assert sniff_dimensions(_jpeg(1200, 675)[:20]) is None
    assert sniff_dimensions(_webp_vp8(640, 480)[:18]) is None
    assert sniff_dimensions(_gif(300, 200)[:4]) is None


def test_shape_thresholds_abstain_near_square():
    assert shape_of(116, 100) == LANDSCAPE
    assert shape_of(115, 100) is None  # exactly 1.15 is not "> 1.15"
    assert shape_of(86, 100) == PORTRAIT
    assert shape_of(87, 100) is None  # exactly 0.87 is not "< 0.87"
    assert shape_of(100, 100) is None
    assert shape_of(0, 100) is None


# ---------------------------------------------------------------- data URIs --
def test_shape_from_data_uri_never_touches_the_network():
    uri = "data:image/png;base64," + base64.b64encode(_png(600, 900)).decode()
    assert shape_from_data_uri(uri) == PORTRAIT


def test_data_uri_with_a_huge_payload_still_parses_the_head():
    payload = _jpeg(1280, 720) + os.urandom(200_000)
    uri = "data:image/jpeg;base64," + base64.b64encode(payload).decode()
    assert len(uri) > DATA_URI_HEAD_CHARS
    assert shape_from_data_uri(uri) == LANDSCAPE


def test_bad_data_uris_abstain():
    assert shape_from_data_uri("https://cdn.example/poster.jpg") is None
    assert shape_from_data_uri("data:image/jpeg;base64") is None  # no comma
    assert shape_from_data_uri("data:text/plain,hello") is None  # not base64
    assert shape_from_data_uri("data:,") is None
    assert shape_from_data_uri("") is None


# ------------------------------------------------------------------- voting --
def test_majority_requires_three_votes_and_sixty_percent():
    assert majority_shape([LANDSCAPE, LANDSCAPE, LANDSCAPE, PORTRAIT]) == LANDSCAPE
    assert majority_shape([PORTRAIT, PORTRAIT, PORTRAIT]) == PORTRAIT
    assert majority_shape([LANDSCAPE, PORTRAIT]) is None  # only 2 votes
    assert majority_shape([LANDSCAPE, LANDSCAPE, None, None]) is None  # 2 parsed
    assert majority_shape([LANDSCAPE, LANDSCAPE, PORTRAIT, PORTRAIT, PORTRAIT]) == PORTRAIT
    assert majority_shape([LANDSCAPE, LANDSCAPE, LANDSCAPE, PORTRAIT, PORTRAIT, PORTRAIT]) is None
    assert majority_shape([]) is None
    assert majority_shape([None, None, None]) is None


def test_decide_mode_detection_beats_defaults():
    # The provider seed says landscape, but three portraits were detected.
    assert (
        decide_mode([PORTRAIT, PORTRAIT, PORTRAIT], "kayoanime", "latest") == PORTRAIT
    )
    assert decide_mode([LANDSCAPE, LANDSCAPE, LANDSCAPE], "anikato", "latest") == LANDSCAPE


def test_decide_mode_falls_back_in_order():
    assert default_mode("anikato", "latest") == PORTRAIT  # seed
    assert default_mode("unknown", "latest") == LANDSCAPE  # fallback geometry
    assert default_mode("unknown", "search") == PORTRAIT
    learned = {artwork_default_key("anikato", "latest"): LANDSCAPE}
    assert default_mode("anikato", "latest", learned) == LANDSCAPE  # learned beats seed
    assert decide_mode([None, None], "anikato", "latest", learned) == LANDSCAPE
    bad = {artwork_default_key("anikato", "latest"): "square"}
    assert default_mode("anikato", "latest", bad) == PORTRAIT  # invalid value ignored


def test_seed_and_referer_tables_are_well_formed():
    for provider, surfaces in SEED_MODES.items():
        for surface, mode in surfaces.items():
            assert mode in (LANDSCAPE, PORTRAIT), f"{provider}:{surface}"
    for surface in ("latest", "search", "discover", "episodes"):
        assert FALLBACK_MODE[surface] in (LANDSCAPE, PORTRAIT)
    assert set(PROBE_REFERERS) == set(SEED_MODES)
    assert probe_referer("anikato") == "https://anikototv.to/"
    assert probe_referer("unknown") is None
