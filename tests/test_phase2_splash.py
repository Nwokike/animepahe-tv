"""Phase 2 startup gate — the splash and its state flags.

The shell must show a branded full-screen splash until the backend is
resolved and the first home fetch has been attempted; screens' own
first-load effects are gated implicitly because they never mount while the
splash shows. These tests pin the flags, the branch order (after all hooks,
before any content branch), and the splash's shape.
"""

import inspect
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

import app_shell
from core.state import AppState


def test_state_carries_the_startup_gate():
    state = AppState()
    assert state.startup_ready is False
    assert state.startup_stage == ""


def _walk(control):
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)


def test_the_splash_is_a_branded_full_screen_gate():
    state = AppState()
    state.startup_stage = "Finding a source…"
    splash = app_shell._startup_splash(state)
    nodes = list(_walk(splash))
    assert isinstance(splash, ft.Container) and splash.expand is True
    assert any(isinstance(n, ft.Image) and n.src == "icon.png" for n in nodes)
    assert any(isinstance(n, ft.ProgressRing) for n in nodes)
    assert any(
        isinstance(n, ft.Text) and n.value == "Finding a source…" for n in nodes
    )


def test_appshell_shows_the_splash_after_all_hooks_and_before_any_content():
    source = textwrap.dedent(inspect.getsource(app_shell.AppShell))
    overlay_at = source.find("_use_resolve_overlay(")
    splash_at = source.find("if not state.startup_ready:")
    content_at = source.find('if active_view == "anime":')
    assert -1 not in (overlay_at, splash_at, content_at)
    assert overlay_at < splash_at < content_at, (
        "the splash must sit after every hook (unconditional hook order) "
        "and before the first content branch"
    )


def test_the_shell_subscribes_both_gate_fields():
    source = textwrap.dedent(inspect.getsource(app_shell.AppShell))
    assert "_ = state.startup_ready" in source
    assert "_ = state.startup_stage" in source
