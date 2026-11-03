"""Task helper — never bare `asyncio.create_task` (house pattern).

Wraps task creation with a done-callback that logs failures, so a background
coroutine that raises never disappears silently the way a bare task does.
"""

import asyncio
import logging

import flet as ft

logger = logging.getLogger(__name__)


def spawn(coro, name: str = "bg-task") -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task):
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Background task %r failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_done)
    return task


def session_alive() -> bool:
    """Whether a UI session still exists for a background task to write to.

    Background loads outlive hot reload / app close; their state writes
    travel Observable -> component -> ``page.session``, which raises
    "An attempt to fetch destroyed session." once the session is gone —
    observed live as a triple crash cascade in load_latest. Callers check
    this before committing UI state.
    """
    try:
        page = ft.context.page
    except (RuntimeError, LookupError, AttributeError):
        return False
    if page is None:
        return False
    try:
        # The ACCESS is the probe: it raises RuntimeError once the session
        # is destroyed. Assigning to a throwaway keeps the expression's
        # effect while satisfying the useless-expression lint (B018).
        _ = page.session
    except RuntimeError:
        return False
    return True


def ui_set(state, name: str, value) -> None:
    """Set an AppState flag so a live session gets the notify, and a dead
    one gets a quiet write (the value must stay correct for the NEXT
    session, but notifying a destroyed session raises inside flet)."""
    if session_alive():
        setattr(state, name, value)
    else:
        object.__setattr__(state, name, value)
