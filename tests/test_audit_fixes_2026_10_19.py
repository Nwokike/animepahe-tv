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
        '("multi": True), never from a list hardcoded in the screen'
    )
    assert "_multi_valued_keys" in source


def test_the_sort_pill_offers_no_all_option():
    """'There is no such thing as sort all.' The sort group never gets
    the synthetic "All" chip — and it lands on the site's own first real
    option instead. A FILTER group does offer it (that is how a filter
    clears)."""
    import screens.discover_screen as ds

    sort_spec = {
        "key": "orderby",
        "label": "Sort",
        "kind": "choice",
        "direction": True,
        "options": [
            {"value": "modified", "label": "Recently updated"},
            {"value": "date", "label": "Newest"},
        ],
    }
    filter_spec = {
        "key": "categories",
        "label": "Category",
        "kind": "choice",
        "multi": True,
        "options": [{"value": "14893", "label": "DVD"}],
    }

    def _labels(spec, selected):
        items = ds._filter_menu(spec, selected, lambda k, v: None)
        return [item.content.value for item in items]

    assert _labels(sort_spec, "modified") == ["Recently updated", "Newest"], (
        "a sort group must not offer 'All'"
    )
    assert _labels(filter_spec, "") == ["All", "DVD"], "a filter clears with 'All'"


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
    assert "_NO_ALL_KEYS" not in source.split('if any(spec.get("direction")')[1][:400]


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
    is unreachable by the remote.

    Checked against the CONTROLS the header actually builds, not the
    source text: the guarded subclasses (GuardedIconButton /
    GuardedTextButton) subclass flet's Button family precisely so this
    still holds, and a source-text match would pass while the built
    control was a Container — the false-pass this project has been bitten
    by before (docs/testing-findings.md, the ft.Markdown size= lesson).
    """
    import dataclasses

    import flet as ft

    from components.app_header import app_header

    class _State:
        current_source_name = "anikato"
        theme_mode = ft.ThemeMode.DARK
        update_available = False
        update_data = None
        viewport_version = 0

    class _Controller:
        def open_backend_picker(self):
            pass

    class _Page:
        theme_mode = ft.ThemeMode.DARK
        width = 1280

    header = app_header(_State(), _Page(), _Controller(), on_back=lambda: None)

    # The focusable classes in the installed flet, read from the package.
    focusable = set()
    for name in dir(ft):
        obj = getattr(ft, name, None)
        if not isinstance(obj, type):
            continue
        with contextlib.suppress(Exception):
            fields = {f.name for f in dataclasses.fields(obj)}
        if fields and "on_focus" in fields and "on_blur" in fields:
            focusable.add(name)
    assert "Container" not in focusable, (
        "if flet 1.0.4 ever gives Container a focus state this test can be "
        "relaxed — the assertion is the point"
    )

    def _walk(control):
        yield control
        for child in getattr(control, "controls", None) or []:
            yield from _walk(child)
        content = getattr(control, "content", None)
        if content is not None and not isinstance(content, list):
            yield from _walk(content)

    interactive = [c for c in _walk(header) if getattr(c, "on_click", None) is not None]
    assert interactive, "the header must offer clickable controls"
    for control in interactive:
        assert any(base.__name__ in focusable for base in type(control).__mro__), (
            f"an interactive header control is not focusable by D-pad: {type(control).__name__}"
        )

    # And the pills carry a focus ring (built by _focus_sides/_chip_style,
    # which live beside app_header in the same module).
    import components.app_header as header_module

    assert "ft.ControlState.FOCUSED" in inspect.getsource(header_module), (
        "a focusable control still needs a visible focus cue"
    )


# ---------------------------------------------------------------------------
# 3. The up-to-date dialog: the house shape, and a safe dismissal
# ---------------------------------------------------------------------------


def test_the_up_to_date_dialog_BUILDS_and_shows_its_notes():
    """The house shape (Sherlock, DDGS, KTV all build it this way): the
    notes are MARKDOWN and the outer column scrolls.

    This test CONSTRUCTS the dialog. A source-text check could not catch
    what the 2026-10-19 re-audit found: `ft.Markdown(..., size=12)`
    raises TypeError on flet 1.0.4 (Markdown has no `size` field), so the
    version pill — the most-tapped control in the header — died on tap
    while the suite stayed green."""
    from components import update_dialog

    class _Page:
        width = 1280

        def show_dialog(self, dlg):
            self.dlg = dlg

        def pop_dialog(self):
            pass

        def update(self):
            pass

        def run_task(self, handler, *args, **kwargs):
            handler(*args)

    page = _Page()
    captured = {}
    update_dialog.show_app_dialog = lambda p, dlg: captured.setdefault("dlg", dlg)
    update_dialog.close_app_dialog = lambda p: True
    update_dialog.show_update_dialog(page, None)

    dlg = captured["dlg"]
    assert dlg is not None, "the up-to-date dialog must open"

    # Walk the tree: the notes must be a real ft.Markdown, and the
    # column that holds them must scroll.
    stack = [dlg]
    markdowns = []
    scrolling = []
    while stack:
        node = stack.pop()
        if isinstance(node, ft.Markdown):
            markdowns.append(node)
        if isinstance(node, ft.Column) and getattr(node, "scroll", None):
            scrolling.append(node)
        stack.extend(getattr(node, "controls", []) or [])
        inner = getattr(node, "content", None)
        if inner is not None:
            stack.append(inner)
    assert markdowns, "the notes are markdown (real bullets, tappable links)"
    assert scrolling, "the notes scroll — a fixed box clipped 60% of them"

    # The markdown carries the house's extension set and a link handler.
    md = markdowns[0]
    assert md.extension_set == ft.MarkdownExtensionSet.GITHUB_WEB
    assert md.on_tap_link is not None, "a link in the changelog is tappable"
    assert not hasattr(md, "size"), "ft.Markdown has no size field in flet 1.0.4"


def test_the_up_to_date_dialog_dismisses_through_the_registry():
    """An unconditional page.pop_dialog() closes whatever sits on top —
    a SnackBar standing above the dialog — and orphans the dialog
    itself. The app's registry pops only if THIS dialog is topmost."""
    from components import update_dialog

    source = inspect.getsource(update_dialog)
    assert "close_app_dialog(page)" in source, "the dismissal goes through the app's own registry"
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
    assert "if score is not None" in source, "the star renders only for a published rating"
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
        "a per-worker counter resets when the segment moves to another worker"
    )
    assert downloads.MAX_SEGMENT_ATTEMPTS == 3


def test_the_backoff_does_not_hold_the_cross_job_permit():
    """The JOB slot is held for the whole job (max_parallel bounds jobs),
    NOT per fetch: segment workers fetch freely inside their job, and a
    worker waiting out its backoff holds no global slot at all."""
    from services import downloads

    worker = inspect.getsource(downloads.DownloadManager._worker)
    assert "async with self._job_limiter" not in worker, (
        "segment workers must not take the cross-job slot per fetch — "
        "that collapsed every job's 6 workers to max_parallel fetches"
    )
    run = inspect.getsource(downloads.DownloadManager._run)
    assert "async with self._job_limiter" in run, "the job slot wraps the whole job"
    sleep = worker.index("await asyncio.sleep(")
    # The sleep happens outside any limiter: no slot is held while waiting.
    assert "_job_limiter" not in worker[sleep : sleep + 200]


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

    assert hasattr(AppState, "viewport_version"), "the observable counter the resize bumps"
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
    assert "bottom=0" in block, "the poster needs BOTH insets to be a fully positioned Stack child"


# ---------------------------------------------------------------------------
# 8. The provider order follows what each source costs the user
# ---------------------------------------------------------------------------


def test_the_provider_order_is_the_one_the_owner_asked_for():
    """AniKato → Kayoanime → AnimePahe → AnimeOut (owner's order,
    2026-10-19).

    The order is not a preference list: it is what each source COSTS.
    AniKato's catalogue is plain SSR/JSON and its stream (megaplay) needs
    no clearance; Kayoanime is plain WordPress + Drive; AnimePahe's
    catalogue is Cloudflare-walled and needs the verification gate;
    AnimeOut's file host is walled behind a challenge and then a plain
    nginx 403, so it can serve art and titles but not episodes.
    """
    from services.providers.base import PROVIDER_ORDER

    assert PROVIDER_ORDER == ("anikato", "kayoanime", "animepahe", "animeout")


def test_the_order_is_the_one_the_ui_and_the_startup_share():
    """The picker, the startup gate and the router all read the SAME
    order — there is no second list to drift."""
    import app_shell
    import main as app_main

    for module, name in ((app_shell, "app_shell"), (app_main, "main")):
        source = inspect.getsource(module)
        assert "PROVIDER_ORDER" in source, f"{name} reads the shared order"

    shell = inspect.getsource(app_shell)
    assert "for n in PROVIDER_ORDER" in shell, "the picker lists the sources in the shared order"


# ---------------------------------------------------------------------------
# 9. The WordPress providers
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


def test_the_header_is_one_bar_and_the_narrow_cluster_pans_like_the_filter_bar():
    """The header NEVER stacks into two lines, and on a small screen its
    action cluster pans sideways EXACTLY the way Discover's filter bar
    does — no arrow, no dead space between the icons.

    The mechanism, which three attempts missed (owner, 2026-10-20: "I am
    still not able to scroll header horizontally... learn from the filter
    part of discover cause it scrolls horizontally perfectly"): a
    scrollable Row nested DIRECTLY inside another Row gets an unbounded
    main axis from Flutter, sizes to its full content width, and
    overflows instead of scrolling — every ScrollMode value looks
    identical on it. Discover's filter bar works because its scrollable
    Row sits inside a BOUNDED box. So the narrow header's cluster must be
    that same shape: a bounded viewport (``Container(expand=True)``)
    holding the scrollable Row. Nothing else.

    Two things the owner explicitly rejected here, and this test pins
    their absence (2026-10-23): the chevron indicator — "the arrow is
    supposed to only show when there is more things to show... That's why
    I told you not to do it", because a correct overflow-aware one is the
    complexity the header must not carry — and the gaps between the
    icons ("remove those distances between them"): ``spacing=0``, the
    controls' own touch targets supply the separation.

    Wide keeps the house's expanding spacer and the right-hugging
    cluster; nothing overflows there, so no viewport is needed. A stacked
    Column is the "falling over" bug this pins.
    """
    import flet as ft

    from components.app_header import app_header

    class _State:
        current_source_name = "anikato"
        theme_mode = ft.ThemeMode.DARK
        update_available = False
        update_data = None
        viewport_version = 0

    class _Controller:
        def open_backend_picker(self):
            pass

    class _Page:
        theme_mode = ft.ThemeMode.DARK

        def __init__(self, width):
            self.width = width

    narrow = app_header(_State(), _Page(360), _Controller())
    wide = app_header(_State(), _Page(1280), _Controller())

    def _root(control):
        return getattr(control, "content", None)

    def _walk(control):
        yield control
        for child in getattr(control, "controls", None) or []:
            yield from _walk(child)
        content = getattr(control, "content", None)
        if content is not None and not isinstance(content, list):
            yield from _walk(content)

    # --- both widths: ONE horizontal Row, never a stack ---
    for label, header in (("narrow", narrow), ("wide", wide)):
        root = _root(header)
        assert isinstance(root, ft.Row), (
            f"the {label} header must be one Row — a stacked Column is the "
            "'falling over' the owner rejected"
        )
        assert root.scroll in (None, ft.ScrollMode.HIDDEN), (
            f"the {label} header must not scroll itself — its CLUSTER does"
        )

    # --- narrow: the filter bar's shape ---
    #
    # The cluster IS the bounded viewport: an expanded Container wrapping
    # the scrollable Row — a scrollable Row directly inside the outer
    # header Row would be unbounded again and the bug would be back.
    narrow_root = _root(narrow)
    narrow_clusters = [
        c
        for c in narrow_root.controls
        if isinstance(c, ft.Container)
        and c.expand
        and isinstance(c.content, ft.Row)
        and getattr(c.content, "scroll", None) == ft.ScrollMode.AUTO
    ]
    assert narrow_clusters, (
        "the narrow cluster must be an expanded Container holding the "
        "scrollable Row — the Discover filter bar's exact shape; a "
        "scrollable Row beside a spacer is unbounded and never scrolls"
    )
    assert narrow_clusters[0].content.spacing == 0, (
        "the owner ordered the dead space between the header icons gone"
    )

    # --- wide: the house's original shape ---
    wide_root = _root(wide)
    spacers = [c for c in wide_root.controls if isinstance(c, ft.Container) and c.expand]
    assert spacers, (
        "the wide header keeps the house's expand spacer so the title "
        "keeps its place and the cluster hugs the right edge"
    )
    wide_clusters = [
        c
        for c in wide_root.controls
        if isinstance(c, ft.Row) and getattr(c, "scroll", None) == ft.ScrollMode.AUTO
    ]
    assert wide_clusters, "the wide action cluster scrolls horizontally"
    assert wide_clusters[0].spacing == 0, "no dead space between the icons"

    # --- the arrow stays out, at EVERY width ---
    chevrons = [
        c for c in _walk(narrow) if getattr(c, "icon", None) == ft.Icons.CHEVRON_RIGHT_ROUNDED
    ] + [c for c in _walk(wide) if getattr(c, "icon", None) == ft.Icons.CHEVRON_RIGHT_ROUNDED]
    assert chevrons == [], (
        "the owner removed the pan chevron — it showed even when nothing "
        "overflowed; an overflow-aware one is complexity the header must "
        "not carry again"
    )


def test_the_quality_rows_are_flat():
    """The house's option list is flat rows, not filled buttons. A bare
    ft.Button wears Flutter's M3 ElevatedButton defaults (a fill, a
    shadow, a 20-radius pill), so the rows must carry the flat style."""
    import flet as ft

    import app_shell

    style = app_shell._flat_row_style()
    assert style.elevation == 0, "no shadow on a flat row"
    assert style.bgcolor == ft.Colors.TRANSPARENT, "no fill on a flat row"
    assert style.side[ft.ControlState.FOCUSED].width == 2.5, (
        "the flat row still carries the house focus ring"
    )


def test_the_filter_bar_is_one_line_that_scrolls():
    """The house's bar (KTV's components/filter_bar.py): ONE horizontal
    line, no `wrap`, `scroll=AUTO`, its own 8/4 padding. It must never
    drop to a second line, and it must not live inside the page's
    vertical scroll (which would carry it away with the grid).

    The owner's report: "all the filter are in one line... instead of it
    to be in different lines." This test builds the bar from a real spec
    and walks it.
    """
    import flet as ft

    import screens.discover_screen as ds

    spec = [
        {
            "key": "genre",
            "label": "Genre",
            "kind": "choice",
            "multi": True,
            "options": [{"value": "1", "label": "Action"}],
        },
        {
            "key": "type",
            "label": "Type",
            "kind": "choice",
            "multi": True,
            "options": [{"value": "tv", "label": "TV"}],
        },
        {
            "key": "season",
            "label": "Season",
            "kind": "choice",
            "multi": True,
            "options": [{"value": "fall", "label": "Fall"}],
        },
    ]

    # The bar's own row, exactly as the screen builds it.
    controls = []

    def _recorder(picked):
        return lambda k, v: picked.append(v)

    for s in spec:
        picked = []
        controls.append(
            ds._menu_button(
                ds._selection_label(s, None),
                ft.Icons.FILTER_LIST_OUTLINED,
                False,
                ds._filter_menu(s, None, _recorder(picked)),
                compact=True,
            )
        )

    for control in controls:
        assert isinstance(control, ft.PopupMenuButton), "the trigger is the house's PopupMenuButton"
        pill = control.content
        assert isinstance(pill, ft.Container), "the pill is the house's Container"
        assert pill.border is not None, "the pill is outlined"
        assert pill.padding == ft.Padding.symmetric(horizontal=8, vertical=8), (
            "the pill wears the house's 8/8 padding"
        )

    # The bar that holds them: no wrap, horizontal scroll.
    assert not hasattr(ds, "filter_row"), "the screen builds the row internally"

    source = inspect.getsource(ds.DiscoverScreen)
    bar = source[source.index("    # ONE horizontal line of pills") :]
    bar = bar[: bar.index("    results = state.discover_results")]
    assert "wrap=True" not in bar, "the pill row must never wrap"
    assert "scroll=ft.ScrollMode.AUTO" in bar, "the pill row pans sideways"
    assert "vertical=ft.ScrollMode.AUTO" not in bar.split("def ")[0], (
        "the bar itself does not get its own vertical scroll"
    )
