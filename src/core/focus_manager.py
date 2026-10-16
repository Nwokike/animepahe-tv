import contextlib

import flet as ft

_BACK_KEYS = ("Escape", "Go Back", "Browser Back", "Backspace", "Back", "BrowserBack")

# Key names that mean "erase a character" when a text field has focus —
# they must not also mean "navigate away" (the search fields type them
# hundreds of times a session).
_TEXT_INPUT_TYPES = tuple(
    t
    for t in (
        getattr(ft, "TextField", None),
        getattr(ft, "SearchBar", None),
        getattr(ft, "CupertinoTextField", None),
    )
    if t is not None
)


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
        # The previously installed handler still gets its event — and if
        # it is async, its result is awaited on the loop (the old code
        # dropped the coroutine on the floor).
        if self._previous is not None and callable(self._previous):
            try:
                result = self._previous(e)
                if hasattr(result, "__await__"):
                    # run_task takes a coroutine FUNCTION and calls it;
                    # pass the awaiting wrapper plus the coroutine as its
                    # argument (not the coroutine object itself).
                    self.page.run_task(_await_coroutine, result)
            except Exception:
                pass
        if e.key in _BACK_KEYS and not self._is_text_editing(e) and self._back_handler:
            # Never break key dispatch on a handler failure.
            with contextlib.suppress(Exception):
                self._back_handler()

    @staticmethod
    def _is_text_editing(e: ft.KeyboardEvent) -> bool:
        """Backspace while a text field holds focus deletes a character —
        it must not navigate away from the user's half-typed query."""
        if e.key != "Backspace":
            return False
        control = getattr(e, "control", None)
        if control is None:
            return False
        return isinstance(control, _TEXT_INPUT_TYPES)

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
                with contextlib.suppress(Exception):
                    await scrollable.scroll_to(scroll_key=control_key, duration=200)

        return _on_focus


async def _await_coroutine(result):
    """Schedule a bare coroutine (a previous handler returning one)."""
    await result
