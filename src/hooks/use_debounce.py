"""Debounce hook — KTV's implementation, verbatim.

Used for search filtering and any input that must not trigger work on every
keystroke. The timer is cancelled and rescheduled on each new value, so only
the settled value flows to consumers.
"""

import asyncio

import flet as ft

from core.tasks import spawn


def use_debounce(value, delay_ms: int = 250):
    debounced, set_debounced = ft.use_state(value)
    timer = ft.use_ref(None)

    def _cancel_and_schedule():
        old = timer.current
        if old is not None and not old.done():
            old.cancel()

        async def _after_delay():
            await asyncio.sleep(delay_ms / 1000.0)
            set_debounced(value)

        timer.current = spawn(_after_delay(), name="debounce")

    def _cleanup():
        old = timer.current
        if old is not None and not old.done():
            old.cancel()

    ft.use_effect(_cancel_and_schedule, [value], cleanup=_cleanup)
    return debounced
