"""Session-alive guards — background work must not write into a dead session.

Observed live: a load finishing after a flet hot reload raised "An attempt
to fetch destroyed session." from deep inside Observable notify, cascading
through its own error path (three stacked tracebacks), and the promo
rotation repeated the crash every tick. These tests pin the guard and the
loader wiring that uses it.
"""

import ast
import inspect
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flet.controls.context import _context_page

from core.state import AppState
from core.tasks import session_alive, ui_set


class _DeadPage:
    @property
    def session(self):
        raise RuntimeError("An attempt to fetch destroyed session.")


class _LivePage:
    def __init__(self):
        self.session = object()


def _with_page(page):
    token = _context_page.set(page)
    try:
        return session_alive()
    finally:
        _context_page.reset(token)


def test_no_context_page_is_not_alive():
    assert _with_page(None) is False


def test_a_destroyed_session_is_not_alive():
    assert _with_page(_DeadPage()) is False


def test_a_live_session_is_alive():
    assert _with_page(_LivePage()) is True


def test_ui_set_writes_even_with_a_dead_session():
    state = AppState()
    token = _context_page.set(_DeadPage())
    try:
        ui_set(state, "is_loading", False)  # must not raise
    finally:
        _context_page.reset(token)
    assert state.is_loading is False


def test_ui_set_notifies_normally_with_a_live_session():
    state = AppState()
    token = _context_page.set(_LivePage())
    try:
        ui_set(state, "is_loading", True)
    finally:
        _context_page.reset(token)
    assert state.is_loading is True


def _body_of(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def test_the_three_loaders_check_the_session_before_committing():
    import main as app_main

    for loader in (
        app_main.AppController.load_latest,
        app_main.AppController.load_episodes,
        app_main.AppController.load_search,
    ):
        source = _body_of(loader)
        assert "session_alive()" in source, f"{loader.__name__} lost its guard"
        tree = ast.parse(source)
        assert any(  # ui_set keeps the loading flag honest for the next session
            isinstance(node, ast.Name) and node.id == "ui_set" for node in ast.walk(tree)
        ), f"{loader.__name__} no longer uses ui_set for its flag"
