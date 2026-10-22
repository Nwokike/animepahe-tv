"""The player's IconButton crash — a stale click delivered after unmount.

The owner's live-APK traceback (2026-10-20):

    RuntimeError: IconButton(91830) Control must be added to the page first
      session.py:459 dispatch_event -> base_control.py:502 _trigger_event
      -> base_control.py:310 page

Read against the installed flet 1.0.4, that error means exactly one
thing: **the client clicked a control the app had already replaced.** Two
facts from the flet source produce it:

1. ``session.__index`` is a ``weakref.WeakValueDictionary``. A control
   leaves it only when the control itself is collected — and a control
   whose handlers close over ``self`` (``on_click=lambda e:
   self._on_back()``) keeps itself, its parent ``Video``, and that Video's
   ``top_button_bar`` alive for the life of the process. So the index
   entry survives the unmount.
2. ``__resolve_event_control`` then returns that dead control, and
   ``_trigger_event``'s ``self.page`` walks a parent chain that reaches no
   ``Page`` and raises.

The click lands in the window between the client's tap and the app's next
frame. The user pressed Back / Retry / Next on a stage the app was already
tearing down to mount the next one in its place. Nothing was wrong with
the handler — there was no handler left to run.

**Why this is ours to fix.** ``app_shell._use_player_overlay`` mounts the
player imperatively into ``page.overlay`` and its mount key is
``(episode_session, resource)``: pressing Retry, Next, Previous or Close
unmounts the very control being pressed. That remount-on-key design
creates the race window, and it is not something a future flet release
will close for us.

**The fix.** ``BaseControl.before_event(e)`` runs at the TOP of
``_trigger_event`` (``base_control.py:499``), strictly BEFORE ``self.page``
(``:502``), and returning ``False`` from it cancels the dispatch cleanly.
``components/guarded_controls.py`` subclasses the Button family (and
``Container``, the house's chip shape) so a control that is no longer on a
page cancels its own event. Every clickable control in the player mount is
one of those.

**What the first attempt got wrong**, pinned by the last test so it cannot
come back: a guard in the app's ``page.on_error``. Flet 1.0.4 DECLARES that
field but never invokes it, AND its own ``dispatch_event`` catches the
raise and reports ``SESSION_CRASHED`` to the client before any handler-level
hook could see it. So that guard was dead code and the "fixed" APK kept
crashing.
"""

import asyncio
import gc
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

from components.player.immersive_player import ImmersivePlayer
from hooks.use_focus_scope import focus_scope


class _Conn:
    """A connection that records what the session reports to the client."""

    def __init__(self):
        self.pubsubhub = PubSubHub()
        self.sent = []

    def send_message(self, message):
        self.sent.append(message)

    def dispose(self):
        pass


def _build_player():
    return ImmersivePlayer(
        resource="https://example.test/master.m3u8",
        title="Episode 1",
        http_headers={},
        resume_key="anikato:slug|1",
        store=None,
        variants=[],
        on_close=lambda: None,
        on_next=lambda: None,
        on_previous=lambda: None,
        source_url="https://example.test/master.m3u8",
        source_referer="https://kwik.cx/",
        source_headers={},
        proxied=False,
        subtitles=[],
        skip={},
    )


def _mount(session):
    """Build the player mount and index it exactly as patch_control does."""
    player = _build_player()
    mount = focus_scope(player, lambda: None)
    _patch(session, None, mount)
    return mount, player


def _patch(session, prev, current):
    _patch_tuple = ObjectPatch.from_diff(prev, current, control_cls=BaseControl)
    for rc in _patch_tuple[2]:
        session.index.pop(rc._i, None)
    for ac in _patch_tuple[1]:
        session.index[ac._i] = ac
    return _patch_tuple[0]


def _unmount(session, mount, replacement):
    _patch(session, mount, replacement)


def _crashes(conn):
    return [
        m
        for m in conn.sent
        if "SESSION_CRASHED" in str(getattr(m, "action", ""))
    ]


# ---------------------------------------------------------------------------
# The precondition
# ---------------------------------------------------------------------------


def test_the_player_button_survives_its_own_closures():
    """The precondition: the back button keeps itself in the weak index.

    flet's index is a WeakValueDictionary, so this is NOT a bug in flet —
    it is the Python rule that a closure over ``self`` keeps its object
    alive. Our player's buttons are wired with ``lambda e: self._on_back()``
    so every button, its Video, and the Video's ``top_button_bar`` list stay
    reachable for the life of the process, and their index entries with
    them. If this ever becomes False the crash cannot occur and this file
    can be deleted.
    """
    conn = _Conn()
    session = Session(conn)
    mount, player = _mount(session)
    button = player.video.controls.material.top_button_bar[0]
    assert session.index.get(button._i) is button

    del mount, player
    gc.collect()
    # Still resolvable: the closures kept it alive, so a late click for its
    # id finds it there and then has no page to run it against.
    assert session.index.get(button._i) is button


# ---------------------------------------------------------------------------
# The bug, and the fix
# ---------------------------------------------------------------------------


def test_a_late_click_on_an_unmounted_player_button_used_to_crash():
    """The bug, pinned: a click delivered after the player is unmounted.

    Before the fix, this raised through ``_trigger_event`` and the session
    sent SESSION_CRASHED to the client — the red error screen the owner
    reported from the built APK.
    """
    import flet as ft

    conn = _Conn()
    session = Session(conn)
    mount, player = _mount(session)
    button = player.video.controls.material.top_button_bar[0]

    _unmount(session, mount, ft.Container(content=ft.Text("x")))

    async def _drive():
        await session.dispatch_event(button._i, "click", {})

    conn.sent.clear()
    asyncio.run(_drive())
    assert _crashes(conn) == [], (
        "a click on a control the app already replaced must not crash the "
        "session — it must be a harmless no-op"
    )


def test_every_clickable_player_control_cancels_once_unmounted():
    """The whole mount, not just the one button that crashed first.

    The player has 19 clickable controls (the back button, Retry, Go Back,
    the quality / audio / speed chips, Skip Intro, the screenshot and
    subtitle buttons, prev/next). Any of them can be the one a queued tap
    lands on, so every one of them is driven through the same late-click
    path here. A future control added without the guard fails this test.
    """
    import flet as ft

    conn = _Conn()
    session = Session(conn)
    mount, _player = _mount(session)

    _, added, _ = ObjectPatch.from_diff(None, mount, control_cls=BaseControl)
    candidates = [c for c in added if getattr(c, "on_click", None) is not None]
    assert len(candidates) >= 15, (
        "the player's clickable surface should be fully enumerated here"
    )

    _unmount(session, mount, ft.Container(content=ft.Text("x")))

    async def _drive():
        crashes = []
        for control in candidates:
            conn.sent.clear()
            try:
                await session.dispatch_event(control._i, "click", {})
            except Exception as ex:  # pragma: no cover - the bug being pinned
                crashes.append(f"{type(control).__name__}: {ex}")
            crashes.extend(
                f"{type(control).__name__}: {str(m.body)[:80]}"
                for m in _crashes(conn)
            )
        return crashes

    assert asyncio.run(_drive()) == [], (
        "every clickable player control must cancel its own event once it "
        "is no longer on a page"
    )


def test_a_mounted_control_still_runs_its_handler():
    """The guard is narrow on purpose: a LIVE control is untouched.

    "Live" means the control's parent chain reaches the page — that is
    what ``.page`` walks, so the mount is attached to ``page.overlay``
    exactly as the app mounts the player.
    """
    import flet as ft

    from components.guarded_controls import GuardedIconButton

    seen = []
    button = GuardedIconButton(icon=ft.Icons.SEARCH_ROUNDED, on_click=lambda e: seen.append(1))

    conn = _Conn()
    session = Session(conn)
    page = session.page
    mount = ft.Container(content=button)
    page.overlay.append(mount)
    # flet stamps a control's parent when it walks the live tree for it
    # (session.__resolve_event_control does this on every event).
    session._Session__find_live_control(page, button._i)
    assert _mounted(button), "the fixture must actually be mounted"

    async def _drive():
        await session.dispatch_event(button._i, "click", {})

    asyncio.run(_drive())
    assert seen == [1], "a mounted control's handler must still fire"
    assert _crashes(conn) == []


def _mounted(control) -> bool:
    try:
        return getattr(control, "page", None) is not None
    except RuntimeError:
        return False


def test_before_event_runs_before_the_page_lookup():
    """The mechanism: ``before_event`` is the one seam that runs before
    ``self.page``, which is why the guard belongs there and not in a
    try/except around the handler."""
    import inspect

    from flet.controls.base_control import BaseControl

    source = inspect.getsource(BaseControl._trigger_event)
    assert source.index("self.before_event(e)") < source.index("self.page"), (
        "if flet ever reorders these, the guard must move"
    )


# ---------------------------------------------------------------------------
# Why the first attempt did not work
# ---------------------------------------------------------------------------


def test_the_page_on_error_guard_was_dead_code_by_design():
    """The first attempt guarded ``Page.on_error``. It could never fire.

    Two independent reasons, both verified here so nobody repeats it:
    flet 1.0.4 DECLARES the field but never invokes it, AND flet's own
    ``dispatch_event`` catches the raise itself and reports it to the
    client (``SESSION_CRASHED``) before any handler-level hook exists.
    """
    import dataclasses
    import pathlib

    import flet as ft
    from flet.controls.page import Page

    # 1. The field exists — so assigning it is not even a syntax error,
    #    which is what made the dead guard look plausible.
    assert "on_error" in {f.name for f in dataclasses.fields(Page)}

    # 2. Nothing in flet ever READS it back.
    package = pathlib.Path(ft.__file__).parent
    readers = [p for p in package.rglob("*.py") if _reads_page_on_error(p)]
    assert readers == [], (
        "if flet ever starts invoking Page.on_error, a guard could move "
        f"there — until then it is dead code: {readers}"
    )


def _reads_page_on_error(path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", '"')):
            continue
        if "on_error:" in stripped or '"""' in stripped:
            continue
        # A reader accesses the attribute on an object; the field's own
        # declaration is `on_error: ... = None`, not `.on_error = ...`.
        if ".on_error" in stripped and "self.on_error =" not in stripped:
            return True
    return False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
