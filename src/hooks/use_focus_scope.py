"""FocusScope — Back/Escape delivery that never depends on which button holds focus.

Ported from KTV: a KeyboardListener with autofocus=True wrapping the player.
Without autofocus the overlay swallows the first Back press on TV. This is
NOT a focus-trapping scope — D-pad traversal stays with Flutter's native
focus system; only the Back/Escape keys are intercepted.
"""

import asyncio
import inspect

import flet as ft

_KEYS = {"Back", "Escape", "BrowserBack", "Go Back", "Browser Back"}


@ft.component
def FocusScope(content, on_back) -> ft.Control:
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
