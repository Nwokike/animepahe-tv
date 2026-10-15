"""Source stamping — each list carries the provider that painted it.

The artwork defaults are learned per provider+surface, so `latest_source`
and `search_source` must be assigned right where the rows land (episodes
already stamp `current_source_name`). This is a structural guard: if a
refactor drops the assignment, the learned defaults silently stop keying.
"""

import ast
import inspect
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from core.state import AppState


def _assigns_in(fn, attr: str) -> list[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == attr
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "state"
                ):
                    hits.append(ast.unparse(node.value))
    return hits


def test_state_carries_the_stamps():
    state = AppState()
    assert state.latest_source == ""
    assert state.search_source == ""


def test_load_latest_stamps_the_serving_provider():
    values = _assigns_in(app_main.AppController.load_latest, "latest_source")
    assert values, "load_latest no longer stamps latest_source"
    assert any("last_winner" in v for v in values)


def test_load_search_stamps_the_serving_provider():
    values = _assigns_in(app_main.AppController.load_search, "search_source")
    assert values, "load_search no longer stamps search_source"
    assert any("last_winner" in v for v in values)
