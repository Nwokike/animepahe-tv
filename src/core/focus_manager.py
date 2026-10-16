import contextlib

import flet as ft

_BACK_KEYS = ("Escape", "Go Back", "Browser Back", "Backspace", "Back", "BrowserBack")

# Keys the FIELD consumes while it holds focus: Backspace erases a
# character, Escape cancels the edit. Neither may navigate away.
_TEXT_INPUT_TYPES = tuple(
    t
    for t in (
        getattr(ft, "TextField", None),
        getattr(ft, "SearchBar", None),
        getattr(ft, "CupertinoTextField", None),
    )
    if t is not None
)


class FieldFocusTracker:
    """Is a text field being edited right now?

    The window-level keyboard event cannot always say (`e.control` is the
    reactive stream's idea of the focused control, and it is missing on
    some platforms) — so the fields THEMSELVES report focus. Dialog range
    inputs install this with `attach(field)`: while the field is focused,
    Escape/Restore cancels the edit (via `on_cancel`) instead of closing
    the dialog; a second Escape — focus already released — closes it.
    """

    def __init__(self):
        self.active = False
        self._cancel = None

    def attach(self, field: ft.TextField, on_cancel=None) -> ft.TextField:
        def _focus(_e):
            self.active = True

        def _blur(_e):
            self.active = False

        field.on_focus = _focus
        field.on_blur = _blur
        self._cancel = on_cancel
        return field

    def handle_back(self) -> bool:
        """True when the key was consumed by the focused field."""
        if not self.active:
            return False
        self.active = False
        if self._cancel is not None:
            with contextlib.suppress(Exception):
                self._cancel()
        # Drop the control's own focus so the NEXT Back reaches the dialog.
        return True


class FocusManager:
    """Global Back delivery. CHAINED, not overwritten: a plain
    `page.on_keyboard_event = …` would silently kill whatever handler
    was installed before (KTV's identity-guarded chaining pattern) —
    with more installers (shortcuts, scopes) appearing, the overwrite
    is a correctness bug, not a style choice."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._back_handler = None
        # An optional extra consumer for the window-level stream — the
        # player installs its key handler here. A KeyboardListener alone
        # is not enough for arrows: Flutter's focus system consumes them
        # for traversal before the listener ever sees the event (owner's
        # report: Space acted, seek/volume did not). page.on_keyboard_event
        # is the window-level handler and sees every physical key.
        self._key_consumer = None
        # The focused text field's tracker (see FieldFocusTracker).
        self.field_focus: FieldFocusTracker | None = None
        self._previous = getattr(page, "on_keyboard_event", None)
        # Keep the installed handler's identity: bound methods are fresh
        # objects on every attribute access, so an `is` check against a
        # re-access would never match.
        self._own = self._handle_keyboard
        page.on_keyboard_event = self._own

    def set_back_handler(self, handler: callable):
        self._back_handler = handler

    def set_key_consumer(self, handler: callable | None):
        """Install (or clear) the player's window-level key handler."""
        self._key_consumer = handler

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
            # A FOCUSED FIELD swallows the first Back: Escape ends the
            # edit and restores the field (an in-progress range input
            # must not be discarded by the same key that cancels typing),
            # and a dialog only closes on the second press.
            if self.field_focus is not None and self.field_focus.handle_back():
                return
            # Never break key dispatch on a handler failure.
            with contextlib.suppress(Exception):
                self._back_handler()
            return
        # Everything else goes to the player when it is open (it ignores
        # keys it has no use for). Back never double-fires: handled above.
        if self._key_consumer is not None and not self._is_text_editing(e):
            with contextlib.suppress(Exception):
                self._key_consumer(e)

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
