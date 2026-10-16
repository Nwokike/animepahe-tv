"""FocusScope — Back/Escape delivery that never depends on which button holds focus.

A plain FUNCTION, not a @ft.component: KTV's form, and the reason the
component form is not used — the player overlay's rendered subtree is
frozen after mount, which is the exact crash class the overlay mount
avoids (see app_shell's player mount). Without autofocus the overlay
swallows the first Back press on TV. This is NOT a focus-trapping
scope — D-pad traversal stays with Flutter's native focus system; only
the Back/Escape keys are intercepted.
"""

import asyncio
import inspect

import flet as ft

_KEYS = {"Back", "Escape", "BrowserBack", "Go Back", "Browser Back", "Backspace"}


def focus_scope(content, on_back) -> ft.Control:
    """Wrap content in an autofocused KeyboardListener that routes
    Back/Escape to on_back and delegates playback shortcuts to content.handle_key."""

    def _handler(e):
        if e.key in _KEYS:
            # ft.context.page RAISES RuntimeError outside a live page
            # context — it never returns None, so the old `if page is
            # None` guard was dead code.
            try:
                page = ft.context.page
            except RuntimeError:
                return
            if page is None:
                return
            # run_task() only accepts coroutine FUNCTIONS; a lambda
            # returning a coroutine fails that check with a TypeError —
            # which is exactly what the old code passed, breaking player
            # Back entirely.
            if inspect.iscoroutinefunction(on_back):
                page.run_task(on_back)
            else:
                result = on_back()
                if asyncio.iscoroutine(result):

                    async def _run():
                        await result

                    page.run_task(_run)
            return

        # Forward desktop/TV playback shortcuts (Space, arrows, j/k/l,
        # volume, fullscreen, skip, etc.) to the player when the child
        # supports it. NOTE: arrows are usually eaten by Flutter's focus
        # traversal before this listener sees them — the window-level path
        # in core.focus_manager is the reliable one and forwards the same
        # handler. This branch stays for platforms where the listener does
        # receive them (no double-fire: the same event never reaches both
        # paths twice for one press... the manager forwards, the listener
        # forwards, and handle_key is idempotent per press by design).
        handler = getattr(content, "handle_key", None)
        if handler is not None and callable(handler):
            try:
                page = ft.context.page
            except RuntimeError:
                page = None
            if inspect.iscoroutinefunction(handler):
                if page:
                    page.run_task(handler, e)
            else:
                result = handler(e)
                if asyncio.iscoroutine(result) and page:

                    async def _run_key():
                        await result

                    page.run_task(_run_key)

    # The expanding Container is load-bearing (KTV's own note): Flet's
    # KeyboardListener extends Control, not LayoutControl, so an
    # `expand=True` on the listener itself is accepted and IGNORED — a
    # listener mounted straight onto the overlay gives the player Stack
    # underneath it no bounds at all (audio plays, the surface is empty).
    return ft.Container(
        content=ft.KeyboardListener(
            content=content,
            autofocus=True,
            on_key_down=_handler,
        ),
        expand=True,
    )


__all__ = ["focus_scope"]
