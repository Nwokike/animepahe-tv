"""artwork_card — one frame, two shapes, and the honest fill for art that
does not match its cell.

Every listing surface builds its cards through here so the shapes can never
drift again: portrait or landscape, set on the inner container, wrapped in
the D-pad focus chain (a flat FilledButton + focus zoom — Container cards
are unreachable on TV in flet 1.0.4), col passed through for the
ResponsiveRow.

When an item's own shape is known (the probe's session memo, or a free local
sniff of a data: URI) and disagrees with the screen's mode, the media layer
becomes the frosted fill: the same image blown up and blurred behind, a
darkened scrim, and the true-aspect copy centered on top — shown, never cut.
"""

import re

import flet as ft

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.artwork import LANDSCAPE, PORTRAIT
from core.theme import AppColors
from core.tokens import CARD_ASPECT_LANDSCAPE, CARD_ASPECT_PORTRAIT
from services.artwork_probe import cached_aspect, cached_shape
from services.hls_proxy import image_url

__all__ = [
    "art_fallback",
    "aspect_for",
    "card_frame",
    "card_media",
    "monogram",
]

FROSTED_BLUR = 18
FROSTED_SCRIM_OPACITY = 0.45
# How much ratio mismatch still counts as "the same shape" (25%: a 16:9
# image in a 3:2 cell crops a hairline; a 2:3 poster in a 16:9 cell does
# not, and gets the frosted fill instead of being cut in half).
FILL_TOLERANCE = 0.25

# The no-art panel's proportions, in one place so every surface matches.
ART_TILE = 46
ART_TILE_RADIUS = 14
ART_TILE_ACCENT = 0.16
ART_TILE_BORDER = 0.35
ART_WATERMARK_OPACITY = 0.10
ART_WASH_OPACITY = 0.16


def monogram(title: str) -> str:
    """One or two initials from a title — "Black Clover" -> "BC". Empty
    input is a valid input (the panel draws a neutral glyph instead)."""
    words = [w for w in re.split(r"[^0-9A-Za-z]+", title or "") if w]
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def art_fallback(
    title: str = "",
    *,
    mode: str = PORTRAIT,
    badge: str = "",
    show_title: bool = False,
) -> ft.Control:
    """The no-artwork panel: a deliberate typographic cover.

    Shown when an item has no image at all or its URL cannot load. Every
    layer sets an app-palette colour — no Material-default tint can leak
    through (the purple/blank box the owner rejected), and no broken-image
    glyph is ever drawn. The title's initials become the mark; the card's
    own overlay (or the details column, via ``show_title``) carries the
    words, so the panel never duplicates them unless asked."""
    mono = monogram(title)
    tile = ft.Container(
        width=ART_TILE,
        height=ART_TILE,
        border_radius=ART_TILE_RADIUS,
        bgcolor=ft.Colors.with_opacity(ART_TILE_ACCENT, AppColors.PRIMARY),
        border=ft.Border.all(1, ft.Colors.with_opacity(ART_TILE_BORDER, AppColors.PRIMARY)),
        alignment=ft.Alignment.CENTER,
        content=(
            ft.Text(mono, size=16, weight=ft.FontWeight.W_800, color=AppColors.PRIMARY)
            if mono
            else ft.Icon(ft.Icons.LIVE_TV_ROUNDED, size=20, color=AppColors.PRIMARY)
        ),
    )
    layers: list[ft.Control] = [
        # The brand wash: a quiet diagonal of the app's own rose, so the
        # panel reads as designed rather than as a missing image.
        ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[
                    ft.Colors.with_opacity(ART_WASH_OPACITY, AppColors.PRIMARY),
                    ft.Colors.TRANSPARENT,
                ],
            ),
            expand=True,
        ),
    ]
    if mode == LANDSCAPE:
        # The card's overlay already prints title + episode at the left
        # and the play glyph at the right — the initials ride the centre
        # as a watermark instead of a tile, so nothing collides.
        layers.append(
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Text(
                    mono or "•",
                    size=64,
                    weight=ft.FontWeight.W_900,
                    color=ft.Colors.with_opacity(ART_WATERMARK_OPACITY, ft.Colors.ON_SURFACE),
                ),
            )
        )
    elif show_title:
        # A text-first cover for surfaces with no overlay of their own
        # (the detail screen's poster box): mark, title, metadata chip.
        layers.append(
            ft.Container(
                alignment=ft.Alignment.CENTER,
                padding=14,
                content=ft.Column(
                    [
                        tile,
                        ft.Text(
                            title or "Untitled",
                            size=14,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=3,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Container(
                            content=ft.Text(
                                badge,
                                size=10,
                                weight=ft.FontWeight.W_700,
                                color=AppColors.PRIMARY,
                            ),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                            border_radius=8,
                            bgcolor=ft.Colors.with_opacity(0.14, AppColors.PRIMARY),
                            visible=bool(badge),
                        ),
                    ],
                    spacing=10,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    else:
        layers.append(
            ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                padding=ft.Padding.only(top=18),
                content=tile,
            )
        )
        layers.append(
            ft.Container(
                alignment=ft.Alignment.BOTTOM_RIGHT,
                padding=ft.Padding.only(right=10, bottom=10),
                content=ft.Icon(
                    ft.Icons.MOVIE_FILTER_ROUNDED,
                    size=36,
                    color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                ),
            )
        )
    return ft.Container(
        content=ft.Stack(controls=layers, expand=True),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        expand=True,
    )


def aspect_for(mode: str) -> float:
    return CARD_ASPECT_LANDSCAPE if mode == LANDSCAPE else CARD_ASPECT_PORTRAIT


def card_media(
    src: str,
    mode: str,
    *,
    title: str = "",
    placeholder: ft.Control | None = None,
    error_content: ft.Control | None = None,
    opacity: float = 1.0,
    provider: str = "",
) -> ft.Control:
    """The image layer for one card cell.

    No art at all, and art whose URL cannot load, both fall to the same
    rich typographic panel (``art_fallback``) — the caller can still pass
    its own ``placeholder``/``error_content`` to override either, but the
    default is never a blank or broken-image box. ``title`` feeds the
    panel's monogram; ``provider`` feeds the display route's referer when
    the platform wraps the image (web CORS / guarded hosts)."""
    fallback = art_fallback(title, mode=mode)
    if not src:
        return placeholder or fallback
    # Shape comes from the RAW URL (the shape memo keys on it); only the
    # control's src goes through the display route.
    shape = cached_shape(src)
    display = image_url(src, provider)
    error = error_content or fallback
    # Adaptive fill: when the probe knows the real ratio, a crop within
    # FILL_TOLERANCE of the cell is just a hairline — COVER fills the cell
    # (no empty space, the owner's ask). Only a genuinely different shape
    # (a portrait poster in a landscape cell, or vice versa) gets the
    # frosted fill that shows the whole image. A square (shape None but a
    # ratio known) rides the same test.
    aspect = cached_aspect(src)
    cell = aspect_for(mode)
    if aspect is not None:
        # The ratio is the authority when it is known.
        fills = abs(aspect - cell) / cell <= FILL_TOLERANCE
    else:
        # Coarse fallback: an unknown shape keeps the house cover-crop.
        fills = shape not in (LANDSCAPE, PORTRAIT) or shape == mode
    if fills:
        return ft.Image(
            src=display,
            fit=ft.BoxFit.COVER,
            expand=True,
            opacity=opacity,
            error_content=error,
        )
    # Mismatch: frosted fill — blurred blow-up behind, scrim, true-aspect copy.
    return ft.Stack(
        controls=[
            ft.Image(src=display, fit=ft.BoxFit.COVER, expand=True, opacity=opacity),
            ft.Container(blur=FROSTED_BLUR, expand=True),
            ft.Container(
                bgcolor=ft.Colors.with_opacity(FROSTED_SCRIM_OPACITY, ft.Colors.BLACK),
                expand=True,
            ),
            ft.Container(
                content=ft.Image(
                    src=display,
                    fit=ft.BoxFit.CONTAIN,
                    expand=True,
                    opacity=opacity,
                    error_content=error,
                ),
                alignment=ft.Alignment.CENTER,
                padding=12,
                expand=True,
            ),
        ],
        expand=True,
    )


def card_frame(
    *,
    mode: str,
    media: ft.Control,
    overlay: list[ft.Control],
    on_click,
    col: dict | None = None,
    gradient: ft.Control | None = None,
    padding: int | None = None,
    radius: int = 16,
) -> ft.Control:
    """The focusable frame every card shares: media, optional gradient,
    overlay layers, the shape, and the D-pad focus chain.

    Portrait cards use 8px padding inset (giving 16px total breathing room
    per card) to match nkiri-tv density exactly."""
    card_padding = padding if padding is not None else (8 if mode == PORTRAIT else 4)
    layers: list[ft.Control] = [media]
    if gradient is not None:
        layers.append(gradient)
    layers.extend(overlay)
    return attach_focus_zoom(
        ft.FilledButton(
            content=ft.Container(
                content=ft.Stack(controls=layers, expand=True),
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                aspect_ratio=aspect_for(mode),
            ),
            style=card_button_style(padding=card_padding, radius=radius),
            animate_scale=card_focus_scale(),
            col=col,
            on_click=on_click,
        )
    )
