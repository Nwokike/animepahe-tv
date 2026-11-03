"""Guard: the app must not call a Flet API this installed version lacks.

This bug class has hit three times (OutlineInputBorder, Dropdown(on_change=),
webview.run_javascript_returning_result) — every one of them raised at
CONSTRUCTION time, which means the crash is on a screen the user just
opened, not on some unreachable branch.

Note what is NOT checked here: keyword arguments. Flet controls accept
many kwargs through their own machinery rather than the Python
signature, so a signature-based walk reports false positives
(ft.Padding(horizontal=...), ft.ButtonStyle(bgcolor=...)). What IS
reliable is the attribute's existence, and the construction smoke tests
below pin the specific shapes that broke.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft


def _python_files() -> list[str]:
    root = os.path.join(os.path.dirname(__file__), "..", "src")
    found: list[str] = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".py"):
                found.append(os.path.join(base, name))
    return found


def test_no_source_file_calls_an_ft_control_that_does_not_exist():
    """A plain ``ft.X`` reference where X is not on the module at all."""
    import ast

    problems: list[str] = []
    for path in _python_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ft"
                and not hasattr(ft, node.attr)
            ):
                problems.append(
                    f"{os.path.basename(path)}:{node.lineno} ft.{node.attr} does not exist"
                )
    assert not problems, "referenced missing ft attributes:\n" + "\n".join(problems)


def test_the_search_field_border_shape_constructs_warning_free():
    """The shape the search field uses constructs cleanly on the INSTALLED
    flet — the family is on the 1.x line, where the per-state
    OutlineInputBorder CLASS is the version's own API (the flat
    InputBorder.OUTLINE enum is deprecated there)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        field = ft.TextField(
            border=ft.OutlineInputBorder(
                border_radius=16,
                side=ft.BorderSide(1, ft.Colors.TRANSPARENT),
            ),
            border_width=1,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_width=1.5,
            focused_border_color="#F43F5E",
        )
    assert type(field.border).__name__ == "OutlineInputBorder"


def test_the_dropdown_callback_is_the_installed_ones():
    """The Dropdown callback kwarg src uses must exist on the installed
    flet — the rename (0.x ``on_change`` → ``on_select``) crashed the
    settings screen once already (2026-10-17). Pin the CONTRACT src
    relies on against the installed package, never a version number."""
    import inspect

    from screens import settings_screen

    params = inspect.signature(ft.Dropdown.__init__).parameters
    assert "on_select" in params or "on_change" in params
    # ...and src's own usage is written against one that exists.
    source = inspect.getsource(settings_screen)
    assert "on_select=_on_backend_change" in source
    assert "on_select" in params, "src uses on_select; the installed flet must have it"


def test_no_ft_icon_or_color_constant_is_a_phantom():
    """``ft.Icons.X`` / ``ft.Colors.X`` where the installed flet has no
    such attribute.

    This is the downloads-screen blocker of 2026-10-16: a single
    ``ft.Icons.DOWNLOAD_OUTLINE_ROUNDED`` (a name that exists in neither
    flet 1.0.4's enum nor any older line) sat on the "partial row" branch
    — the branch a user only reaches after a download fails or is
    interrupted. The screen then crashed on open for exactly that user,
    while every test fixture (complete/queued rows only) passed.
    """
    import re

    icons = set(dir(ft.Icons))
    colors = set(dir(ft.Colors))
    icon_pat = re.compile(r"ft\.Icons\.([A-Z0-9_]+)")
    color_pat = re.compile(r"ft\.Colors\.([A-Z0-9_]+)")
    problems: list[str] = []
    for path in _python_files():
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for match in icon_pat.finditer(text):
            if match.group(1) not in icons:
                problems.append(f"{path}: ft.Icons.{match.group(1)}")
        for match in color_pat.finditer(text):
            if match.group(1) not in colors:
                problems.append(f"{path}: ft.Colors.{match.group(1)}")
    assert not problems, "phantom flet constants:\n" + "\n".join(problems)


def test_every_download_row_state_builds():
    """The downloads screen renders a row for EVERY state combination —
    including the partial row with no live progress, which is the exact
    shape a killed/interrupted download leaves behind (and the branch the
    phantom icon hid in)."""
    from screens.downloads_screen import _episode_row

    class _Ctl:
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    controller = _Ctl()
    progress_cases = [
        None,
        {"state": "downloading", "percent": 42.5},
        {"state": "downloading", "percent": None},  # unknown length
        {"state": "queued"},
        {"state": "stopped", "bytes": 2048},
        {"state": "failed"},
        {"state": "complete"},
    ]
    for state in ("partial", "complete"):
        for progress in progress_cases:
            row = _episode_row(
                {"state": state, "episode_num": 8, "size_bytes": 3757},
                "s1",
                controller,
                progress,
            )
            assert row is not None
