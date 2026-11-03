"""Render-probe: instantiate the player and find controls that use absolute
positioning (left/top/right/bottom) outside a Stack or page.overlay."""

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

import flet as ft
from flet.controls.context import _context_page


class _Session:
    def __init__(self):
        self.connection = type("C", (), {"send_message": lambda *a, **k: None})()


class _Page:
    def __init__(self):
        self.session = _Session()
        self.platform = ft.PagePlatform.WINDOWS
        self.theme_mode = ft.ThemeMode.DARK
        self.overlay: list = []
        self.services: list = []

    def update(self):
        pass

    def show_dialog(self, dlg):
        pass

    def pop_dialog(self):
        pass

    def run_task(self, *a, **k):
        pass


ABSOLUTE = ("left", "top", "right", "bottom")


def _absolutely_positioned(control) -> list[str]:
    out = []
    for name in ABSOLUTE:
        val = getattr(control, name, None)
        if val is not None:
            out.append(f"{name}={val}")
    return out


def walk(control, parent_is_stack, path, offenders):
    name = type(control).__name__
    here = f"{path}/{name}"
    is_stack = isinstance(control, ft.Stack)
    bad = _absolutely_positioned(control)
    if bad and not parent_is_stack:
        offenders.append((here, bad))
    controls = getattr(control, "controls", None)
    if controls is not None and not isinstance(controls, (list, tuple)):
        # Not a layout list (e.g. AdaptiveVideoControls) — probe its fields.
        for field in ("material", "material_desktop", "cupertino", "cupertino_desktop"):
            sub = getattr(controls, field, None)
            if sub is not None:
                walk(sub, False, f"{here}.{field}", offenders)
        controls = None
    for i, child in enumerate(controls or []):
        walk(child, is_stack, f"{here}[{i}]", offenders)
    content = getattr(control, "content", None)
    if content is not None:
        walk(content, is_stack, f"{here}.content", offenders)


page = _Page()
token = _context_page.set(page)
try:
    from components.player.immersive_player import ImmersivePlayer

    player = ImmersivePlayer(
        resource="http://127.0.0.1:1/fake.m3u8",
        title="Probe - Episode 1 - (1080p)",
        variants=[{"label": "1080p", "uri": "http://x/y.m3u8"}],
        skip={"intro": {"start": 5, "end": 85}},
    )
    offenders = []
    walk(player, parent_is_stack=False, path="player", offenders=offenders)
    print("absolute-positioning offenders:", len(offenders))
    for where, bad in offenders:
        print("  ", where, bad)
    # Also probe the mounted overlay node shape the shell uses.
    node = ft.Container(content=player, expand=True)
    offenders2 = []
    walk(node, parent_is_stack=False, path="mount", offenders=offenders2)
    print("through the mount container:", len(offenders2))
    for where, bad in offenders2:
        print("  ", where, bad)
finally:
    _context_page.reset(token)
