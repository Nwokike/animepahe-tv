"""Task helper — never bare `asyncio.create_task` (house pattern).

Wraps task creation with a done-callback that logs failures, so a background
coroutine that raises never disappears silently the way a bare task does.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def spawn(coro, name: str = "bg-task") -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task):
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning(
                "Background task %r failed: %s", name, exc, exc_info=exc
            )

    task.add_done_callback(_done)
    return task
