"""Wiring smoke test: every ControllerMethods attribute the shell/screens
call must exist on AppController.

Catches the failure mode where main() wires methods.toggle_favorite to
controller.toggle_favorite but the controller method was never written —
the tap then dies with AttributeError at runtime, and nothing else notices.
"""

import ast
import inspect
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import main as app_main
from state.controller_ctx import ControllerMethods


def _methods_wired_in_main() -> set[str]:
    """Every `methods.<name> = ...` assignment in main()."""
    source = inspect.getsource(app_main.main)
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "methods"
                ):
                    names.add(target.attr)
    return names


def test_every_wired_method_exists_on_the_controller():
    controller = app_main.AppController.__new__(app_main.AppController)
    missing = []
    for name in sorted(_methods_wired_in_main()):
        if name.startswith("_"):
            continue  # private handles (e.g. _app_controller), not actions
        if not hasattr(controller, name):
            missing.append(name)
    assert not missing, f"main() wires methods that AppController lacks: {missing}"


def test_every_spawned_method_is_awaitable_or_returns():
    """Anything main() passes to spawn() must be a coroutine FUNCTION —
    create_task(None) / a sync return raises at runtime."""
    controller = app_main.AppController.__new__(app_main.AppController)
    source = inspect.getsource(app_main.main)
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [
            t
            for t in node.targets
            if isinstance(t, ast.Attribute)
            and isinstance(t.value, ast.Name)
            and t.value.id == "methods"
        ]
        if not targets:
            continue
        name = targets[0].attr
        if name.startswith("_"):
            continue
        # Is the assignment's value a spawn(...) of a controller method?
        spawned = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "spawn"
            for n in ast.walk(node.value)
        )
        if not spawned:
            continue
        if not inspect.iscoroutinefunction(getattr(controller, name, None)):
            bad.append(name)
    assert not bad, f"spawn()ed but not coroutine functions: {bad}"


def test_every_controller_method_slot_has_a_wiring_or_is_documented():
    """ControllerMethods slots are the public surface screens call; any slot
    the shell assigns is covered by the previous tests, so this just guards
    against a slot that nothing wires and nothing documents."""
    slots = {
        name
        for name in ControllerMethods.__dataclass_fields__
    }
    wired = _methods_wired_in_main()
    shell_assigned = {"go_home", "open_search", "open_downloads", "open_settings",
                      "open_anime", "back", "close_player", "play_adjacent",
                      "choose_quality", "open_sheet", "close_dialog"}
    uncovered = slots - wired - shell_assigned
    assert not uncovered, f"ControllerMethods slots never wired: {sorted(uncovered)}"
