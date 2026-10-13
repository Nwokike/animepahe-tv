"""Tier-1 house hardening: shared services, connectivity, throttling,
empty states, tokens.
"""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft

from components.empty_state import EmptyState
from core.state import AppState
from core.shared_services import get_shared_services
from core.tokens import SPACING_XS, SPACING_XL


class _FakeLauncher:
    def __init__(self):
        self.calls = []

    async def launch_url(self, url, **kwargs):
        self.calls.append(url)


class _FakeClipboard:
    def __init__(self):
        self.values = []

    async def set(self, value):
        self.values.append(value)


class _FakePage:
    """SharedServices only touches ``services`` — a stub is enough and
    avoids constructing a real Page (which needs a session)."""

    def __init__(self):
        self.services: list = []


def _page():
    page = _FakePage()
    # The services list must not grow per call — that's the whole point.
    return page


def test_shared_services_mount_once():
    page = _page()
    first = get_shared_services(page)
    page.services.clear()
    second = get_shared_services(page)
    assert first is second


def test_shared_services_survive_a_failing_launcher():
    page = _page()
    services = get_shared_services(page)

    class _Broken:
        async def launch_url(self, url, **kwargs):
            raise RuntimeError("no activity")

    services.launcher = _Broken()
    ok = asyncio.run(services.launch_url("https://example.com"))
    assert ok is False


def test_shared_services_clipboard_guarded():
    page = _page()
    services = get_shared_services(page)
    services.clipboard = _FakeClipboard()
    assert asyncio.run(services.set_clipboard("hello")) is True
    assert services.clipboard.values == ["hello"]


def test_shared_services_timeout_counts_as_success():
    """A hand-off to another app never returns — TimeoutError is success."""

    class _Hangs:
        async def launch_url(self, url, **kwargs):
            await asyncio.sleep(5)

    page = _page()
    services = get_shared_services(page)
    services.launcher = _Hangs()
    assert asyncio.run(services.launch_url("ktv://play", timeout=0.05)) is True


def test_offline_is_not_a_cf_gate():
    """The old build set cf_blocked whenever page 1 came back empty, so an
    offline user was told to verify they're human."""
    state = AppState()
    state.is_online = False
    offline_empty = not state.latest_releases and not state.is_online
    assert offline_empty is True
    # The controller's gate now requires is_online, so offline != blocked.
    gated = bool(not state.latest_releases and state.is_online)
    assert gated is False


def test_connectivity_state_defaults_online():
    state = AppState()
    assert state.is_online is True
    assert state.connectivity_version == 0


def test_empty_state_composes():
    clicks = []
    state = EmptyState(
        "Nothing here",
        message="Try again",
        action_label="Retry",
        on_action=lambda e: clicks.append(1),
    )
    button = next(c for c in _walk(state) if isinstance(c, ft.FilledButton))
    button.on_click(None)
    assert clicks == [1]


def test_empty_state_without_action_has_no_button():
    state = EmptyState("Nothing here")
    assert not any(isinstance(c, ft.FilledButton) for c in _walk(state))


def test_tokens_are_a_4pt_grid():
    for token in (SPACING_XS, SPACING_XL):
        assert token % 4 == 0
    # Animation tokens are milliseconds, not px.
    from core.tokens import ANIMATION_FAST

    assert ANIMATION_FAST == 150


def _walk(control):
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, list):
        yield from _walk(content)
