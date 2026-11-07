"""The pre-play quality picker is a minimal modal BOTTOM SHEET (owner,
2026-11-07): not a centered AlertDialog, no tip text, no Cancel button —
choosing a row dismisses the sheet as the player takes over.

Verified against the installed flet 1.1.0.dev4: BottomSheet is a
DialogControl shown through the same page.show_dialog/use_dialog portal
the shell already hosts, and ListTile has no on_focus/on_blur (rows must
stay ft.Button for TV D-pad focus).
"""

import inspect
from types import SimpleNamespace

import flet as ft

import app_shell


def _fake_state():
    return SimpleNamespace(
        quality_choices=[
            {"label": "1080p - SUB (JPN)", "url": "u1"},
            {"label": "720p - SUB (JPN)", "url": "u2"},
        ],
        quality_resolving=False,
        pending_playback={
            "has_kwik_files": True,
            "anime_session": "a",
            "episode_session": "e",
        },
    )


def _fake_controller():
    calls = []
    return SimpleNamespace(
        choose_quality=lambda i: calls.append(("choose", i)),
        earn_kwik_qualities=lambda a, e: calls.append(("more", a, e)),
        close_dialog=lambda: calls.append(("close",)),
        _calls=calls,
    )


def test_quality_picker_is_a_bottom_sheet_not_a_dialog():
    sheet = app_shell._build_quality_dialog(_fake_state(), _fake_controller())
    assert isinstance(sheet, ft.BottomSheet)
    assert not isinstance(sheet, ft.AlertDialog)
    assert sheet.show_drag_handle is True
    assert sheet.dismissible is True
    assert sheet.scrollable is True
    # Scrim tap / swipe-down must clear the state flags, or the sheet
    # resurrects on the next render (on_dismiss -> controller.close_dialog).
    assert sheet.on_dismiss is not None


def test_quality_sheet_rows_stay_uniform_focusable_buttons():
    sheet = app_shell._build_quality_dialog(_fake_state(), _fake_controller())
    rows = [c for c in sheet.content.controls if isinstance(c, ft.Button)]
    # two qualities + the "More qualities" row
    assert len(rows) == 3
    assert all(type(r) is ft.Button for r in rows)
    labels = [r.content for r in rows[:2]]
    assert "·  Best" in labels[0] and "·  Best" not in labels[1]


def test_quality_sheet_has_no_cancel_button_or_tip_copy():
    block = inspect.getsource(app_shell._build_quality_dialog)
    assert "actions=" not in block
    assert 'content="Cancel"' not in block
    assert "ft.TextButton(" not in block
    assert "Tip:" not in block


def test_choose_quality_drives_the_resolve_overlay_while_re_resolving():
    """Selecting a site-source quality closes the sheet first, then the
    "Resolving stream…" overlay covers the kwik re-resolve — no dead gap
    between the sheet sliding away and the player view mounting."""
    src = inspect.getsource(app_shell)  # sanity: builder lives in the shell
    assert "_build_quality_dialog" in src
    import main as app_main

    src = inspect.getsource(app_main.AppController.choose_quality)
    assert 'state.resolve_stage = "Resolving stream…"' in src
    assert "state.is_resolving = True" in src
    assert "state.is_resolving = False" in src
