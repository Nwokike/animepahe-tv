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


def test_no_deprecated_flat_textfield_border_kwargs():
    """flet 1.0.4 deprecates the flat TextField border kwargs (removed in
    1.3.0) — they emit DeprecationWarnings on every render (the flet run
    log). Every TextField must use the OutlineInputBorder/ControlState
    map shape instead."""
    import ast

    deprecated = {
        "border_radius",
        "border_width",
        "border_color",
        "border_style",
        "focused_border_width",
        "focused_border_color",
    }
    problems: list[str] = []
    for path in _python_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if name != "TextField":
                continue
            for kw in node.keywords:
                if kw.arg in deprecated:
                    problems.append(
                        f"{os.path.basename(path)}:{node.lineno} "
                        f"TextField({kw.arg}=...) is deprecated in 1.0.4"
                    )
    assert not problems, "deprecated TextField kwargs:\n" + "\n".join(problems)


def test_the_outline_border_map_shape_is_warning_free():
    """The replacement shape every TextField must use constructs without
    a DeprecationWarning."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        field = ft.TextField(
            border={
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                    side=ft.BorderSide(width=1, color=ft.Colors.TRANSPARENT),
                    border_radius=16,
                ),
                ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                    side=ft.BorderSide(width=1.5, color="#F43F5E"),
                    border_radius=16,
                ),
            }
        )
    assert isinstance(field.border, dict)


def test_the_two_known_phantoms_stay_gone():
    """Verify that the API shapes used by search and settings screens are valid.
    In flet 1.0.4, OutlineInputBorder is now a real control class, while
    Dropdown uses on_select rather than on_change."""
    import inspect

    assert "on_change" not in inspect.signature(ft.Dropdown.__init__).parameters
    # and the shape that replaced them constructs
    border = ft.OutlineInputBorder(
        border_radius=16,
        side=ft.BorderSide(width=1, color=ft.Colors.TRANSPARENT),
    )
    field = ft.TextField(
        border=border,
        focused_border_width=1.5,
        focused_border_color="#F43F5E",
    )
    assert isinstance(field.border, ft.OutlineInputBorder)
    dropdown = ft.Dropdown(
        options=[ft.dropdown.Option("auto", "Automatic")], on_select=lambda e: None
    )
    assert dropdown.on_select is not None


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
