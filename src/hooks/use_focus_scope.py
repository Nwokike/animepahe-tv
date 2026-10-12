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

_KEYS = {"Back", "Escape", "BrowserBack", "Go Back", "Browser Back"}


def focus_scope(content, on_back) -> ft.Control:
    """Wrap content in an autofocused KeyboardListener that routes
    Back/Escape to on_back."""

    def _handler(e):
        if e.key in _KEYS:
            page = ft.context.page
            if page is None:
                return
            # run_task() only accepts coroutine FUNCTIONS; a sync handler
            # would raise "handler must be a coroutine function".
            if inspect.iscoroutinefunction(on_back):
                page.run_task(on_back)
            else:
                result = on_back()
                if asyncio.iscoroutine(result):
                    page.run_task(lambda: result)

    return ft.KeyboardListener(
        content=content,
        autofocus=True,
        on_key_down=_handler,
    )


__all__ = ["focus_scope"]
