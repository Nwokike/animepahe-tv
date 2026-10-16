"""use_grid_mode — the automatic screen-level grid decision.

There is no user option: a screen looks at the shape of its own artwork,
decides once, and swaps the whole screen when the answer lands. First paint
uses the learned/seed default (core.artwork), so the screen is never blank
or wrong-shaped while probes run.

The decision logic is pure (core.artwork) and tested there; this module is
only the wiring around it — read the learned defaults, probe up to
PROBE_COUNT of the screen's own images, settle the mode, remember a solid
detection for the next launch.
"""

import flet as ft

from core.artwork import (
    LANDSCAPE,
    PORTRAIT,
    artwork_default_key,
    default_mode,
    majority_shape,
)
from core.tasks import spawn
from services import artwork_probe

PROBE_COUNT = 12
SETTLE_MSG = "grid-mode"


def grid_sources(items, picker) -> list[str]:
    """The artwork URLs a screen's items would render, in order, blanks kept
    (a blank is the backend's own no-art fallback — handled by the cards)."""
    sources: list[str] = []
    for item in items:
        src = picker(item)
        sources.append(src if isinstance(src, str) else "")
    return sources


async def resolve_mode(
    sources: list[str],
    provider: str,
    surface: str,
    learned: dict | None = None,
    cache=None,
) -> tuple[str, str | None]:
    """(mode, strong_detection). ``strong`` is a detected supermajority worth
    remembering; None means the default stood."""
    shapes = await artwork_probe.shapes_for(sources[:PROBE_COUNT], provider=provider, cache=cache)
    strong = majority_shape(shapes)
    if strong:
        return strong, strong
    return default_mode(provider, surface, learned), None


def use_grid_mode(surface: str, sources: list[str], provider: str, state) -> str:
    """The screen's mode for this render — 'landscape' or 'portrait'.

    Re-resolves when the list identity or the serving provider changes; the
    effect's task is cancelled by the framework when it re-runs, so a stale
    probe can never swap a screen it no longer describes.
    """
    learned, set_learned = ft.use_state({})
    mode, set_mode = ft.use_state(None)
    key = "|".join(
        (
            surface,
            provider,
            str(len(sources)),
            sources[0] if sources else "",
            sources[-1] if sources else "",
        )
    )

    def _settle():
        set_mode(None)  # the new list paints with the default immediately

        async def _run():
            from services.store import get_store

            data = await get_store().get_artwork_defaults()
            set_learned(data)
            found, strong = await resolve_mode(
                sources, provider, surface, data, getattr(state, "cache", None)
            )
            set_mode(found)
            if strong and data.get(artwork_default_key(provider, surface)) != strong:
                set_learned({**data, artwork_default_key(provider, surface): strong})
                await get_store().save_artwork_default(provider, surface, strong)

        spawn(_run(), name="grid-mode")

    ft.use_effect(_settle, [key])

    if mode in (LANDSCAPE, PORTRAIT):
        return mode
    return default_mode(provider, surface, learned)
