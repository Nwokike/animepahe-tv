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

import flet as ft

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.artwork import LANDSCAPE, PORTRAIT
from core.tokens import CARD_ASPECT_LANDSCAPE, CARD_ASPECT_PORTRAIT
from services.artwork_probe import cached_shape
from services.hls_proxy import image_url

__all__ = ["aspect_for", "card_media", "card_frame"]

FROSTED_BLUR = 18
FROSTED_SCRIM_OPACITY = 0.45


def aspect_for(mode: str) -> float:
    return CARD_ASPECT_LANDSCAPE if mode == LANDSCAPE else CARD_ASPECT_PORTRAIT


def card_media(
    src: str,
    mode: str,
    *,
    placeholder: ft.Control | None = None,
    error_content: ft.Control | None = None,
    opacity: float = 1.0,
    provider: str = "",
) -> ft.Control:
    """The image layer for one card cell.

    ``placeholder`` shows when the item has no art at all (every provider
    shows something — the caller passes the backend's own fallback per the
    house law); ``error_content`` shows when a URL fails to load.
    ``provider`` feeds the display route's referer when the platform wraps
    the image (web CORS / guarded hosts)."""
    if not src:
        return placeholder or ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH)
    # Shape comes from the RAW URL (the shape memo keys on it); only the
    # control's src goes through the display route.
    shape = cached_shape(src)
    display = image_url(src, provider)
    if shape not in (LANDSCAPE, PORTRAIT) or shape == mode:
        return ft.Image(
            src=display,
            fit=ft.BoxFit.COVER,
            expand=True,
            opacity=opacity,
            error_content=error_content,
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
                    error_content=error_content,
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
