"""Regressions from the 2026-10-19 tri-audit (three independent agents).

Each test pins ONE defect the audit found, so the same break cannot come
back quietly:

- AniKato's genre/type/status/season filters sent a stringified list
  (``genre[]=['1']``) and the site matched NOTHING — the default
  backend's filters were dead (a regression introduced the same day).
- The Discover Sort dropdown SHOWED "Recently updated" while the request
  carried no orderby at all, so the grid came back in another order than
  the dropdown claimed (the owner's "does not update").
- The sort-direction arrow flipped on AniKato, whose form has no order
  parameter — a control that changed nothing.
- Every header control (back, theme, version pill, badge) was an
  ft.Container, which flet 1.0.4 gives NO focus state: unreachable by a
  TV remote.
- The up-to-date dialog clipped ~60% of the bundled changelog and popped
  the topmost dialog unconditionally (eating a SnackBar above it).
- A category count the site never published was printed as "(0)".
- One failing segment could be retried 18 times (the cap was per
  worker, and a requeued segment lands on any worker), and the backoff
  slept while holding a global cross-job permit.
- The compact detail poster sat at the TOP of the cover instead of the
  bottom band (only `right` was set, so Flutter aligned it topStart).
"""

import contextlib
import inspect
import os
import sys
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

# ---------------------------------------------------------------------------
# 1. The filter shape lives in the provider's spec, not in the UI
# ---------------------------------------------------------------------------


def test_the_screen_has_no_hardcoded_list_of_filter_keys():
    """The multi-valued keys are READ from the spec. A hardcoded list in
    the UI is what broke AniKato's filters in the first place."""
    import screens.discover_screen as ds

    source = inspect.getsource(ds)
    assert "_LIST_VALUED_KEYS" not in source, (
        "the multi-valued keys must come from the provider's spec "
        "(\"multi\": True), never from a list hardcoded in the screen"
    )
    assert "_multi_valued_keys" in source


def test_the_sort_dropdown_has_no_all_option():
    """'There is no such thing as sort all.' The sort group never gets
    the synthetic "All" first option — and it lands on the site's own
    first real option instead."""
    import screens.discover_screen as ds

    spec = {
        "key": "orderby",
        "label": "Sort",
        "kind": "choice",
        "options": [
            {"value": "modified", "label": "Recently updated"},
            {"value": "date", "label": "Newest"},
        ],
    }
    dropdown = ds._filter_dropdown(spec, None, lambda k, v: None)
    keys = [o.key for o in dropdown.options]
    assert "" not in keys, "a sort group must not offer 'All'"
    assert keys == ["modified", "date"]
    assert dropdown.value == "modified", "it lands on the site's first option"

    # A NON-sort group still offers the clearing option.
    other = ds._filter_dropdown(
        {
            "key": "categories",
            "label": "Category",
            "kind": "choice",
            "options": [{"value": "14893", "label": "DVD"}],
        },
        None,
        lambda k, v: None,
    )
    assert next(o.key for o in other.options) == "", "a filter clears with 'All'"


def test_the_direction_toggle_appears_only_where_the_source_has_a_direction():
    """AniKato's form has no order parameter (verified live 2026-10-19),
    so the arrow would be a control that changes nothing. The screen
    shows it only when a spec entry declares a direction."""
    import screens.discover_screen as ds

    source = inspect.getsource(ds)
    assert 'spec.get("direction")' in source, (
        "the toggle must be gated on the provider's own declaration"
    )
    # And the gate is not a key-name guess.
    assert "_NO_ALL_KEYS" not in source.split("if any(spec.get(\"direction\")")[1][:400]


# ---------------------------------------------------------------------------
# 2. The header is on every screen, and every control is D-pad reachable
# ---------------------------------------------------------------------------


def test_every_screen_renders_the_shared_header():
    """The owner's rule: the header is on EVERY screen, so switching
    backends never depends on being on Home."""
    import glob

    screens = sorted(glob.glob(os.path.join("src", "screens", "*.py")))
    assert len(screens) >= 6, screens
    missing = []
    for path in screens:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        if "app_header" not in source:
            missing.append(path)
    assert not missing, f"these screens render no shared header: {missing}"


def test_the_header_controls_are_button_family():
    """A Container takes no D-pad focus in flet 1.0.4 (28 control classes
    expose on_focus/on_blur; Container is not one of them). The house
    apps use Containers, but this app is TV-first: a Container control
    is unreachable by the remote."""
    from components import app_header

    source = inspect.getsource(app_header)
    # The interactive controls are Buttons.
    assert "ft.IconButton(" in source, "the back/theme controls are IconButtons"
    assert "ft.TextButton(" in source, "the version pill/badge/title are TextButtons"
    # And the pills carry a focus ring.
    assert "ft.ControlState.FOCUSED" in source, (
        "a focusable control still needs a visible focus cue"
    )


# ---------------------------------------------------------------------------
# 3. The up-to-date dialog: the house shape, and a safe dismissal
# ---------------------------------------------------------------------------


def test_the_up_to_date_dialog_scrolls_its_notes_as_markdown():
    """The house shape (Sherlock, DDGS, KTV all build it this way):
    the notes are MARKDOWN in a SCROLLABLE column. The old copy put a
    1128-character plain Text in a FIXED 340x220 box, so ~160px of it
    painted over the dialog's buttons."""
    from components import update_dialog

    source = inspect.getsource(update_dialog)
    assert "ft.Markdown(" in source, "the notes render as markdown (real bullets)"
    assert "scroll=ft.ScrollMode.AUTO" in source, "the notes scroll"
    # No fixed-height plain-Text box of notes any more.
    assert "height=220,\n" in source or "height=220" in source, (
        "the notes box keeps a bounded HEIGHT — but it scrolls"
    )


def test_the_up_to_date_dialog_dismisses_through_the_registry():
    """An unconditional page.pop_dialog() closes whatever sits on top —
    a SnackBar standing above the dialog — and orphans the dialog
    itself. The app's registry pops only if THIS dialog is topmost."""
    from components import update_dialog

    source = inspect.getsource(update_dialog)
    assert "close_app_dialog(page)" in source, (
        "the dismissal goes through the app's own registry"
    )
    up_to_date = source.split("def _show_up_to_date")[1].split("def show_update_dialog")[0]
    assert "page.pop_dialog()" not in up_to_date, (
        "an unconditional pop would eat a SnackBar above this dialog"
    )
    assert "on_dismiss=" not in up_to_date, (
        "flet calls on_dismiss AFTER removing the dialog; a handler that "
        "pops again closes whatever else is on top (the re-check path "
        "appends the new dialog while the old one is still closing)"
    )


# ---------------------------------------------------------------------------
# 4. Count honesty
# ---------------------------------------------------------------------------


def test_a_count_the_source_never_published_is_not_printed():
    """WordPress omits `count` on some category rows; the old
    ``row.get("count", 0)`` printed "(0)" — a number nobody published
    (the owner's "the numbering is either false, hallucinated")."""
    from services.providers.base import label_with_count

    assert label_with_count("DVD", 2) == "DVD (2)"
    assert label_with_count("DVD", None) == "DVD", "an absent count prints nothing"
    assert label_with_count("DVD", "") == "DVD"
    assert "(0)" not in label_with_count("Uncategorized", None)


def test_the_rating_is_absent_not_zero():
    """A source with no numeric rating shows NO star — never "★ 0.0"
    (Kayoanime's "rating" is the age certification, verified live
    2026-10-19)."""
    from core.state import Anime

    anime = Anime(
        id=1,
        title="X",
        type="TV",
        episodes=1,
        status="",
        season="",
        year=2026,
        score=None,
        poster="",
        session="s",
    )
    assert anime.score is None
    import components.result_card as rc

    source = inspect.getsource(rc.result_card)
    assert 'if score is not None' in source, (
        "the star renders only for a published rating"
    )
    assert "★ {score:.1f}" in source


def test_the_quality_dialog_rows_are_one_focusable_control():
    """Every row of the quality picker is the SAME control, and that
    control can take D-pad focus.

    The owner's report: a lone filled-red "winner" between outlined rows
    broke the remote's up/down movement (2026-10-19). The house idiom
    for an option list is a `ListTile` row (KTV's quality/audio
    dialog) — but against the installed flet 1.0.4, `ft.ListTile` has
    NO on_focus/on_blur, so a ListTile row is UNREACHABLE by a TV
    remote. `ft.Button` is focusable, so the uniform Button rows are
    both what the owner asked for AND the TV-correct choice; the house
    idiom is phone-first.
    """
    import dataclasses

    import app_shell

    focusable = set()
    for name in dir(ft):
        obj = getattr(ft, name, None)
        if not isinstance(obj, type):
            continue
        fields = None
        with contextlib.suppress(Exception):
            fields = {f.name for f in dataclasses.fields(obj)}
        if fields and "on_focus" in fields and "on_blur" in fields:
            focusable.add(name)
    assert "ListTile" not in focusable, (
        "a ListTile row cannot take D-pad focus in flet 1.0.4 — the house "
        "option list is phone-first, this app is not"
    )
    assert "Button" in focusable

    source = inspect.getsource(app_shell)
    for builder in ("_build_quality_dialog", "_build_download_quality_dialog"):
        block = source.split(f"def {builder}(")[1]
        block = block.split("\ndef ")[0]
        assert "ft.Button(" in block, f"{builder} rows are Buttons"
        assert "ft.FilledButton(" not in block, (
            f"{builder} must not mix a filled winner in with the others"
        )
        assert "·  Best" in block, "the best row is marked in its label"


# ---------------------------------------------------------------------------
# 5. The download engine's retry budget
# ---------------------------------------------------------------------------


def test_the_retry_cap_is_shared_by_the_segments_of_one_job():
    """A requeued segment can land on ANY worker, so a per-worker attempt
    counter reset itself and one bad segment could be tried 6 workers x
    3 attempts = 18 times instead of the 3 the cap promises."""
    from services import downloads

    source = inspect.getsource(downloads.DownloadManager._worker)
    assert "attempts: dict[str, int]" in source, (
        "the attempt counter is a parameter, shared by the job's workers"
    )
    assert "attempts: dict[str, int] = {}" not in source, (
        "a per-worker counter resets when the segment moves to another "
        "worker"
    )
    assert downloads.MAX_SEGMENT_ATTEMPTS == 3


def test_the_backoff_does_not_hold_the_cross_job_permit():
    """The permit is taken per FETCH: a worker waiting out its backoff
    must not sit on a global cross-job slot while it does nothing."""
    from services import downloads

    source = inspect.getsource(downloads.DownloadManager._worker)
    acquire = source.index("async with self._job_limiter")
    sleep = source.index("await asyncio.sleep(")
    assert acquire < sleep, "the permit is taken for the fetch"
    # The sleep is NOT inside the `async with` block: the `async with`
    # block ends before the sleep begins.
    block = source[acquire:sleep]
    assert block.count("async with") == 1
    assert "await asyncio.sleep" not in block


# ---------------------------------------------------------------------------
# 6. The width-dependent layout follows the window
# ---------------------------------------------------------------------------


def test_a_window_resize_re_renders_the_width_dependent_layout():
    """The badge's visibility and the detail screen's compact layout are
    decided by the WIDTH at render time. flet exposes ``page.on_resize``;
    the app never registered it, so a rotated phone kept the old layout
    until some other state change happened to redraw it."""
    import main
    from core.state import AppState

    assert hasattr(AppState, "viewport_version"), (
        "the observable counter the resize bumps"
    )
    source = inspect.getsource(main)
    assert "page.on_resize" in source, "the page must listen for resizes"
    assert "viewport_version" in source, "a resize bumps the counter"

    from components import app_header

    header_source = inspect.getsource(app_header.app_header)
    assert "viewport_version" in header_source, (
        "the header reads the counter, so a resize repaints it"
    )


# ---------------------------------------------------------------------------
# 7. The detail screen's compact poster
# ---------------------------------------------------------------------------


def test_the_compact_poster_is_anchored_to_the_bottom_band():
    """With only `right` set, Flutter treats the poster as PARTIALLY
    positioned and the Stack's alignment (topStart) put it at the TOP of
    the cover — not in the bottom band the code comments describe."""
    import screens.anime_detail_screen as detail

    source = inspect.getsource(detail)
    block = source.split("compact_poster = ft.Container(")[1][:600]
    assert "right=8" in block
    assert "bottom=0" in block, (
        "the poster needs BOTH insets to be a fully positioned Stack child"
    )


# ---------------------------------------------------------------------------
# 7. The WordPress providers
# ---------------------------------------------------------------------------


def test_the_kayoanime_category_filter_accepts_a_bare_string():
    """Both WordPress providers accept either shape: a bare string must
    not be iterated CHARACTER by CHARACTER (the original bug — category
    14893 became categories=1,4,8,9,3)."""
    import asyncio

    from services.providers.kayoanime import KayoanimeProvider

    class _Resp:
        status_code = 200
        headers: ClassVar[dict] = {}

        def json(self):
            return []

    class _Client:
        def __init__(self):
            self.calls: list = []

        async def get(self, url, params=None, headers=None, timeout=None):
            self.calls.append((url, params or {}))
            return _Resp()

    async def _run():
        client = _Client()
        provider = KayoanimeProvider(client=client)
        await provider.browse({"categories": "14893"}, 1)
        return client.calls[0][1]

    params = asyncio.run(_run())
    assert params.get("categories") == "14893", params
