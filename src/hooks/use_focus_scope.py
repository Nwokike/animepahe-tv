"""FocusScope — Back/Escape delivery that never depends on which button holds focus.

Ported from KTV: a KeyboardListener with autofocus=True wrapping the player.
Without autofocus the overlay swallows the first Back press on TV. This is
NOT a focus-trapping scope — D-pad traversal stays with Flutter's native
focus system; only the Back/Escape keys are intercepted.
"""

import flet as ft

_KEYS = {"Back", "Escape", "BrowserBack", "Go Back", "Browser Back"}


@ft.component
def FocusScope(content, on_back) -> ft.Control:
    def _handler(e: ft.KeyboardEvent):
        if e.key in _KEYS:
            page = ft.context.page
            if page is not None:
                page.run_task(on_back)

    return ft.KeyboardListener(
        content=content,
        autofocus=True,
        on_key_down=_handler,
    )
