"""The player branch must route a pre-open failure to the error card.

Regression coverage for T0.6: `state.player_error` used to be set by
play_downloaded and never rendered (the shell only branched on
`player_open` and the player itself never read the state), so a missing
download left the UI looking like the tap did nothing.
"""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import app_shell
from core.state import AppState


class _FakeController:
    """Only what the error-card callbacks touch."""

    def __init__(self):
        self._app_controller = self
        self.played: list[str] = []

    async def play_downloaded(self, episode_session: str):
        self.played.append(episode_session)


def _find_texts(control, out=None):
    if out is None:
        out = []
    text = getattr(control, "value", None)
    if isinstance(text, str):
        out.append(text)
    for child in getattr(control, "controls", None) or []:
        _find_texts(child, out)
    for child in getattr(control, "content", None) or [] if isinstance(
        getattr(control, "content", None), list
    ) else []:
        _find_texts(child, out)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, list):
        _find_texts(content, out)
    return out


def _find_buttons(control, out=None):
    if out is None:
        out = []
    if type(control).__name__ == "OutlinedButton":
        out.append(control)
    for child in getattr(control, "controls", None) or []:
        _find_buttons(child, out)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, list):
        _find_buttons(content, out)
    return out


def test_player_error_renders_card_not_player():
    state = AppState()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    state.current_episode_session = "ep123"

    card = app_shell._build_player(state, _FakeController())
    texts = _find_texts(card)
    assert "The downloaded file is missing." in texts
    assert "Playback unavailable" in texts
    buttons = _find_buttons(card)
    labels = [
        b.content if isinstance(b.content, str) else getattr(b.content, "value", "")
        for b in buttons
    ]
    assert "Retry" in labels
    assert "Go Back" in labels


def test_no_player_error_keeps_building_the_player():
    """player_error is the only branch condition; None must fall through.

    The player itself lives behind a @ft.component FocusScope (needs a live
    renderer), so this asserts the guard, not the player mount — the spec
    round trip is covered by test_player_spec.py.
    """
    state = AppState()
    state.player_open = True
    state.player_error = None
    state.player_spec = {"resource": "https://cdn/index.m3u8", "title": "Frieren"}

    built = {}

    class _FakePlayer:
        def __init__(self, **kwargs):
            built.update(kwargs)

    import components.player.immersive_player as ip

    original = ip.ImmersivePlayer
    ip.ImmersivePlayer = _FakePlayer
    try:
        try:
            app_shell._build_player(state, _FakeController())
        except RuntimeError as ex:
            # FocusScope construction is the renderer-bound tail; reaching it
            # proves the error branch did not fire.
            assert "renderer" in str(ex)
    finally:
        ip.ImmersivePlayer = original
    assert built["resource"] == "https://cdn/index.m3u8"
    assert built["title"] == "Frieren"


def test_retry_clears_error_and_replays():
    state = AppState()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    state.current_episode_session = "ep123"
    controller = _FakeController()

    card = app_shell._build_player(state, controller)
    retry = next(
        b
        for b in _find_buttons(card)
        if isinstance(b.content, str) and b.content == "Retry"
    )

    async def _run():
        retry.on_click(None)
        await asyncio.sleep(0)

    asyncio.run(_run())
    assert state.player_error is None
    assert controller.played == ["ep123"]


def test_go_back_clears_error_and_closes_player():
    state = AppState()
    state.player_open = True
    state.player_error = "The downloaded file is missing."

    card = app_shell._build_player(state, _FakeController())
    back = next(
        b
        for b in _find_buttons(card)
        if isinstance(b.content, str) and b.content == "Go Back"
    )
    back.on_click(None)
    assert state.player_error is None
    assert state.player_open is False
