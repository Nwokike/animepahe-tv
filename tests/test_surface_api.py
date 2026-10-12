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


def test_the_two_known_phantoms_stay_gone():
    """The exact names that crashed the search and settings screens."""
    assert not hasattr(ft, "OutlineInputBorder")
    # and the shape that replaced them constructs
    field = ft.TextField(
        border=ft.InputBorder.OUTLINE,
        border_radius=16,
        border_width=1,
        border_color=ft.Colors.TRANSPARENT,
        focused_border_width=1.5,
        focused_border_color="#F43F5E",
    )
    assert field.border is ft.InputBorder.OUTLINE
    dropdown = ft.Dropdown(
        options=[ft.dropdown.Option("auto", "Automatic")], on_select=lambda e: None
    )
    assert dropdown.on_select is not None
