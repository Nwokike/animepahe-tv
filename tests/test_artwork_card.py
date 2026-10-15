"""card_media — the shape rule and the frosted fill, unit-tested.

The frame itself is covered by test_focusable_cards (focus chain + aspect
per mode); this file pins the media decision: cover-crop unless the item's
own known shape disagrees with the screen, in which case the true-aspect
copy is shown over a blurred backdrop — never cut.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from components.artwork_card import aspect_for, card_frame, card_media
from core.artwork import LANDSCAPE, PORTRAIT
from services import artwork_probe


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def _images(control):
    if isinstance(control, ft.Image):
        yield control
    for child in getattr(control, "controls", []) or []:
        yield from _images(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _images(content)


def _blurred_containers(control):
    if isinstance(control, ft.Container) and control.blur:
        yield control
    for child in getattr(control, "controls", []) or []:
        yield from _blurred_containers(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _blurred_containers(content)


def test_aspect_mapping():
    assert aspect_for(LANDSCAPE) == 1.67
    assert aspect_for(PORTRAIT) == 0.67


def test_unknown_shape_keeps_the_house_cover_crop():
    media = card_media("https://cdn.example/unprobed.jpg", PORTRAIT)
    assert isinstance(media, ft.Image)
    assert media.fit == ft.BoxFit.COVER


def test_known_matching_shape_is_a_plain_cover_image():
    url = "https://cdn.example/matches.jpg"
    artwork_probe._mem[artwork_probe.CACHE_PREFIX + url] = PORTRAIT
    try:
        media = card_media(url, PORTRAIT)
        assert isinstance(media, ft.Image)
        assert media.fit == ft.BoxFit.COVER
    finally:
        artwork_probe._mem.clear()


def test_known_mismatch_becomes_the_frosted_fill():
    url = "https://cdn.example/portrait-in-wide.jpg"
    artwork_probe._mem[artwork_probe.CACHE_PREFIX + url] = PORTRAIT
    try:
        media = card_media(url, LANDSCAPE)
        images = list(_images(media))
        assert len(images) == 2, "blow-up + true-aspect copy"
        assert images[0].fit == ft.BoxFit.COVER
        assert images[1].fit == ft.BoxFit.CONTAIN
        assert list(_blurred_containers(media)), "a blurred backdrop layer"
    finally:
        artwork_probe._mem.clear()


def test_data_uri_mismatch_frosts_without_any_network_or_memo():
    uri = "data:image/png;base64," + base64.b64encode(_png(266, 400)).decode()
    media = card_media(uri, LANDSCAPE)
    images = list(_images(media))
    assert len(images) == 2  # sniffed locally: portrait art in a wide cell


def test_empty_src_shows_the_caller_fallback_or_a_surface():
    plain = card_media("", LANDSCAPE)
    assert isinstance(plain, ft.Container)
    assert plain.bgcolor == ft.Colors.SURFACE_CONTAINER_HIGH

    fallback = ft.Container(content=ft.Text("no art"))
    assert card_media("", LANDSCAPE, placeholder=fallback) is fallback


def test_card_frame_carries_aspect_focus_and_click():
    clicked = []
    frame = card_frame(
        mode=LANDSCAPE,
        media=ft.Container(),
        overlay=[ft.Text("layer")],
        on_click=lambda e: clicked.append(True),
    )
    assert frame.content.aspect_ratio == 1.67
    assert frame.on_focus is not None and frame.on_blur is not None
