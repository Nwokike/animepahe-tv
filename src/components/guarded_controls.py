"""Guarded controls — a Button that cancels its own event when unmounted.

**The bug this closes (the owner's live-APK crash, 2026-10-20):**

    RuntimeError: IconButton(91830) Control must be added to the page first
      session.py:459 dispatch_event -> base_control.py:502 _trigger_event
      -> base_control.py:310 page

Read against the installed flet 1.0.4, that traceback means exactly one
thing: the client tapped a control the app had already replaced. Two
facts from the flet source produce it:

1. ``session.__index`` is a ``weakref.WeakValueDictionary``. A control
   leaves it only when the control itself is collected — and a control
   whose handlers close over ``self`` (``on_click=lambda e:
   self._on_back()``) keeps itself, its parent ``Video`` and that Video's
   ``top_button_bar`` alive for the life of the process. So the index
   entry survives the unmount.
2. ``__resolve_event_control`` then returns that dead control, and
   ``_trigger_event``'s ``self.page`` walks a parent chain that reaches
   no ``Page`` and raises.

The click lands in the window between the client's tap and the app's next
frame. The user pressed Back / Retry / Next on a stage the app was
already tearing down to mount the next one in its place. Nothing was
wrong with the handler — there was no handler left to run.

**Where the race is created.** ``app_shell._use_player_overlay`` mounts
the player imperatively into ``page.overlay``, and its mount key is
``(episode_session, resource)``: pressing Retry, Next, Previous or Close
unmounts the very control being pressed and mounts a fresh stage. The
removal reaches the client asynchronously, so a queued or double tap is
delivered to a control that is no longer in the tree.

**Why the fix is a ``before_event`` guard, not something louder.**
Flet calls ``BaseControl.before_event(e)`` at the TOP of
``_trigger_event`` (``base_control.py:499``), strictly *before* it touches
``self.page`` (``:502``). Returning ``False`` from it cancels the
dispatch cleanly. Returning ``False`` when the control has no page is
therefore the exact, minimal intervention: the superseded tap becomes a
no-op instead of a session crash.

The alternative — a guard in the app's error handler — does not work,
because flet's ``dispatch_event`` catches the raise itself and reports
``SESSION_CRASHED`` to the client; an after-the-fact handler never sees
it. (A first attempt guarded ``Page.on_error``, which flet 1.0.4 declares
but never invokes; that guard was dead code and the APK kept crashing.
``tests/test_stale_control_events.py`` pins both facts.)

**The rule.** A control that is not on a page cancels its own event and
returns ``False``. Everything else — a live control, any real handler
exception — behaves exactly as flet intended.
"""

from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger(__name__)


def _is_mounted(control: ft.BaseControl) -> bool:
    """Does this control still sit in a live page tree?

    ``.page`` walks the parent chain and RAISES ``RuntimeError`` when it
    reaches nothing — it never returns ``None``, so a ``None`` guard
    around it is dead code. The bare attribute access below is the probe:
    its VALUE is irrelevant, only whether it raises.
    """
    try:
        # The attribute access IS the probe — only the raise carries
        # information, so the value is returned straight out.
        return getattr(control, "page", None) is not None
    except RuntimeError:
        return False


class GuardedIconButton(ft.IconButton):
    """An ``IconButton`` that cancels its own click once unmounted.

    Replace ``ft.IconButton`` with this on any control the app mounts
    into ``page.overlay`` and replaces by key — the player's Back, the
    error card's Retry and Go Back, the resolve stage's Cancel — so a
    tap that arrives after the replacement is a no-op.

    The override is three lines and performs no work on the hot path: a
    live control's ``.page`` lookup succeeds on the first try and the
    event proceeds unchanged.
    """

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            # A superseded tap: the control that was pressed is gone and
            # its replacement is already mounted. Log at debug for the
            # terminal and cancel — never a user-visible error.
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


class GuardedTextButton(ft.TextButton):
    """A ``TextButton`` with the same unmount guard (the version pill,
    the source pill, and the header's other chips)."""

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


class GuardedOutlinedButton(ft.OutlinedButton):
    """An ``OutlinedButton`` with the same unmount guard (the player
    error card's Retry and Go Back)."""

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


class GuardedButton(ft.Button):
    """Any Button-family control with the same guard, for call sites that
    build one of the other variants directly."""

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


class GuardedContainer(ft.Container):
    """A ``Container`` with the same unmount guard.

    ``ft.Container`` is NOT among flet's focusable classes — it has no
    ``on_focus``/``on_blur`` — so it is never used for anything a TV
    remote must reach. It IS the house's chip shape for the tap-only
    controls that sit beside them (the player's quality / audio / speed
    chips and the Skip-intro chip), and those are just as capable of
    receiving a superseded tap, so they carry the same guard.
    """

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


class GuardedFilledButton(ft.FilledButton):
    """A ``FilledButton`` with the same unmount guard (the search form's
    primary action, which rebuilds on every keystroke)."""

    def before_event(self, e) -> bool | None:
        if not _is_mounted(self):
            logger.debug("stale control event (superseded tap): %s", self)
            return False
        return None


__all__ = [
    "GuardedButton",
    "GuardedContainer",
    "GuardedFilledButton",
    "GuardedIconButton",
    "GuardedOutlinedButton",
    "GuardedTextButton",
]
