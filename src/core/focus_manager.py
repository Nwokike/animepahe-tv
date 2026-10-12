import flet as ft

_BACK_KEYS = ("Escape", "Go Back", "Browser Back", "Backspace", "Back", "BrowserBack")


class FocusManager:
    """Global Back delivery. CHAINED, not overwritten: a plain
    `page.on_keyboard_event = …` would silently kill whatever handler
    was installed before (KTV's identity-guarded chaining pattern) —
    with more installers (shortcuts, scopes) appearing, the overwrite
    is a correctness bug, not a style choice."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._back_handler = None
        self._previous = getattr(page, "on_keyboard_event", None)
        # Keep the installed handler's identity: bound methods are fresh
        # objects on every attribute access, so an `is` check against a
        # re-access would never match.
        self._own = self._handle_keyboard
        page.on_keyboard_event = self._own

    def set_back_handler(self, handler: callable):
        self._back_handler = handler

    def _handle_keyboard(self, e: ft.KeyboardEvent):
        # The previously installed handler still gets its event.
        if self._previous is not None and callable(self._previous):
            try:
                self._previous(e)
            except Exception:
                pass
        if e.key in _BACK_KEYS:
            if self._back_handler:
                self._back_handler()

    def restore(self) -> None:
        """Give the page back the handler that was here before (an
        identity-guarded restore — only if ours is still installed)."""
        if getattr(self.page, "on_keyboard_event", None) is self._own:
            self.page.on_keyboard_event = self._previous

    @staticmethod
    def make_scroll_on_focus(scrollable: ft.ListView | ft.Column):
        async def _on_focus(e):
            control_key = getattr(e.control, "key", None)
            if control_key and hasattr(scrollable, "scroll_to"):
                try:
                    await scrollable.scroll_to(scroll_key=control_key, duration=200)
                except Exception:
                    pass

        return _on_focus
