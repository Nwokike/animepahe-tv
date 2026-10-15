"""AppShell — adaptive navigation + content (house pattern, Sherlock/KTV).

Navigation follows Material 3 window classes:
- <600dp (phone portrait): bottom NavigationBar
- 600-839dp: compact left NavigationRail
- >=840dp and every Android TV: left NavigationRail (TV forces the rail
  regardless of measured width — no TV app puts primary nav at the bottom)

Cross-promo lives in native slots (hero card + "More from us" shelf), never
between content and navigation — an ad sandwiched against nav is the pattern
both AdMob policy and TV focus design call out as wrong.
"""

import asyncio

import flet as ft
from flet import context as flet_context

from core.tasks import spawn
from core.theme import AppColors
from screens.anime_detail_screen import AnimeDetailScreen
from screens.downloads_screen import DownloadsScreen
from screens.home_screen import HomeScreen
from screens.search_screen import SearchScreen
from screens.discover_screen import DiscoverScreen
from screens.settings_screen import SettingsScreen
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

_TABS = ("Home", "Discover", "Downloads", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.EXPLORE_ROUNDED,
    ft.Icons.DOWNLOAD_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)

# Material 3 window size class boundary (dp): below it, bottom bar.
_RAIL_MIN_WIDTH = 600


def _is_tv(page) -> bool:
    if page is None:
        return False
    platform = getattr(page, "platform", None)
    return platform is not None and platform == ft.PagePlatform.ANDROID_TV


def _use_rail(page) -> bool:
    if _is_tv(page):
        return True
    width = getattr(page, "width", None) or 0
    return width >= _RAIL_MIN_WIDTH


def _startup_splash(state) -> ft.Control:
    """The startup gate: brand mark, spinner, and the stage line
    ("Finding a source…", "Loading releases…"). CollabShell's shape —
    a full-screen column on the app background."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Image(src="icon.png", width=140, height=140, fit=ft.BoxFit.CONTAIN),
                ft.Container(height=24),
                ft.ProgressRing(
                    width=40, height=40, stroke_width=3, color=ft.Colors.PRIMARY
                ),
                ft.Container(height=10),
                ft.Text(
                    state.startup_stage or "",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )


@ft.component
def AppShell() -> ft.Control:
    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)
    active_tab, set_active_tab = ft.use_state("Home")
    active_view, set_active_view = ft.use_state("tabs")  # tabs | anime | player
    _ = state.episodes_version
    _ = state.player_open
    _ = state.startup_ready  # the splash gate re-renders when it flips
    _ = state.startup_stage

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    def _open_anime(session: str):
        # Full-screen branch (Sherlock's results-view pattern): nav bar
        # hides, an AppBar with a back button appears.
        set_active_view("anime")
        # load_anime resolves the header (poster/title/metadata) before
        # the episodes load, so cold-opened details don't sit on "Loading...".
        controller.load_anime(session)

    # The controller drives navigation by mutating these closures in place
    # (identity must survive — see controller_ctx.py).
    controller.go_home = lambda: set_active_tab("Home")

    def _open_search():
        # The Discover tab hosts both surfaces; the Home header's search
        # action opens the search one.
        set_active_tab("Discover")
        state.discover_showing_search = True

    controller.open_search = _open_search
    controller.open_discover = lambda: setattr(state, "discover_showing_search", False)
    controller.open_downloads = lambda: set_active_tab("Downloads")
    controller.open_settings = lambda: set_active_tab("Settings")
    controller.open_anime = _open_anime
    controller.back = lambda: set_active_view("tabs")
    controller.close_player = lambda: set_active_view("anime")
    controller.play_adjacent = lambda delta: _play_adjacent(delta)
    controller.choose_quality = lambda idx: _choose_quality(idx)

    def _play_adjacent(delta):
        from core.tasks import spawn

        spawn(controller._app_controller.play_adjacent(delta), name="play-adjacent")

    def _choose_quality(index):
        from core.tasks import spawn

        spawn(controller._app_controller.choose_quality(index), name="choose-quality")

    def _on_tab(name: str):
        set_active_tab(name)

    # Dialog portal (Sherlock pattern): one dialog whose identity survives
    # re-renders; screens open sheets through the controller instead of
    # calling page.show_dialog ad hoc. THREE owners share it — the play
    # quality dialog, the download quality dialog, and an imperative
    # sheet (the search-confirm) — so the portal tracks WHO owns it.
    # Clearing on a flag alone is wrong: it would dismiss whichever
    # dialog happened to be open as soon as another flag flipped.
    active_dialog, set_active_dialog = ft.use_state(None)
    portal_owner, set_portal_owner = ft.use_state(None)
    sheet, set_sheet = ft.use_state(None)
    # The quality dialog also rebuilds when its resolving flag flips, so the
    # spinner/disabled state lands without remounting the whole shell.
    dialog_resolving, set_dialog_resolving = ft.use_state(False)
    if state.quality_dialog_open:
        if portal_owner != "quality" or dialog_resolving != state.quality_resolving:
            set_portal_owner("quality")
            set_dialog_resolving(state.quality_resolving)
            set_active_dialog(_build_quality_dialog(state, controller))
    elif state.download_choice_open:
        if portal_owner != "download":
            set_portal_owner("download")
            set_active_dialog(_build_download_quality_dialog(state, controller))
    elif state.backend_picker_open:
        if portal_owner != "backend":
            set_portal_owner("backend")
            set_active_dialog(_build_backend_picker(state, controller))
    elif sheet is not None:
        if portal_owner != "sheet":
            set_portal_owner("sheet")
            set_active_dialog(sheet)
    else:
        if portal_owner is not None or active_dialog is not None:
            set_portal_owner(None)
            set_active_dialog(None)
            set_dialog_resolving(False)
    try:
        ft.use_dialog(active_dialog)
    except RuntimeError:
        pass

    def _close_dialog():
        """Close whichever dialog is open.

        The flag-driven dialogs (play quality, download quality) are owned
        by the controller's state, so clearing the imperative sheet alone
        leaves their flags set — the elif chain above then rebuilds the
        same dialog on the next render, and neither Cancel nor global Back
        would ever dismiss it."""
        set_sheet(None)
        if state.quality_dialog_open or state.pending_playback is not None:
            state.quality_dialog_open = False
            state.quality_choices = None
            state.pending_playback = None
            state.episodes_version += 1
        if state.download_choice_open or state.pending_download is not None:
            state.download_choice_open = False
            state.download_choices = None
            state.pending_download = None
        if state.backend_picker_open:
            state.backend_picker_open = False

    controller.open_sheet = lambda d: set_sheet(d)
    controller.close_dialog = _close_dialog

    # Publish what global Back should do (the controller's FocusManager
    # reads this on every keypress; the closures above are the actions).
    if controller._app_controller is not None:
        controller._app_controller.ui_state = {
            "dialog_open": active_dialog is not None,
            "view": active_view,
            "player_open": state.player_open,
        }

    # The player mounts imperatively into page.overlay rather than being
    # rendered here: controls built inside a @ft.component render are frozen
    # after mount, and the player rewrites itself constantly (overlay
    # visibility, retry buttons, playback rate, quality swap). KTV mounts
    # its player in a ft.View for the same reason; page.views is gone in
    # flet 1.0.4, so page.overlay is the equivalent top-level slot.
    _use_player_overlay(state, controller)

    # Stream resolution takes seconds — the overlay is how the tap is
    # acknowledged (KTV's rule: anything slower than a beat gets a spinner).
    _ = state.busy_version
    _use_resolve_overlay(state, controller)

    # Startup gate (CollabShell's pattern): the shell shows the splash
    # until the backend is resolved and the first home fetch has been
    # attempted — so the first thing anyone sees is never a half-loaded
    # app or a CF challenge window. Past all hooks, so hook order stays
    # unconditional while the splash is up.
    if not state.startup_ready:
        return _startup_splash(state)

    if active_view == "anime":
        body = AnimeDetailScreen()
        chrome = _detail_appbar(controller)
        show_nav = False
    else:
        if active_tab == "Home":
            body = HomeScreen()
        elif active_tab == "Discover":
            # One tab, two surfaces: the filtered catalog and search.
            body = SearchScreen() if state.discover_showing_search else DiscoverScreen()
        elif active_tab == "Downloads":
            body = DownloadsScreen()
        else:
            body = SettingsScreen()
        chrome = None
        show_nav = True

    rail_destinations = [
        ft.NavigationRailDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]  # The bar takes NavigationBarDestination objects — feeding it rail
    # destinations serializes the wrong wire type and the bottom bar
    # renders empty on phones.
    bar_destinations = [
        ft.NavigationBarDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    selected = _TABS.index(active_tab)

    if _use_rail(page):
        rail_or_bar = ft.NavigationRail(
            destinations=rail_destinations,
            selected_index=selected,
            on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            min_width=72,
            bgcolor=ft.Colors.SURFACE,
            use_indicator=True,
            indicator_color=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
        )
        content = ft.Column(
            [
                chrome if chrome is not None else ft.Container(width=0, height=0),
                ft.Container(content=body, expand=True),
            ],
            spacing=0,
            expand=True,
        )
        if show_nav:
            return ft.Row(
                [rail_or_bar, ft.VerticalDivider(width=1), content],
                spacing=0,
                expand=True,
            )
        return ft.Column([content], spacing=0, expand=True)

    return ft.Column(
        [
            ft.Container(content=body, expand=True),
            ft.NavigationBar(
                destinations=bar_destinations,
                selected_index=selected,
                on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            ),
        ],
        spacing=0,
        expand=True,
    )


# The live player (so Back can run its bounded position save), the overlay
# node mounted for it, and the key currently mounted — without the first a
# remote Back discards the resume position; without the rest, the overlay
# leaks or shows a stale stage.
_active_player = None
_active_mount = None
_active_key = None


def _play_adjacent(delta: int, controller) -> None:
    """Next/previous episode from inside the player (module level so the
    overlay mount can reach it)."""
    from core.tasks import spawn

    app_controller = getattr(controller, "_app_controller", None)
    if app_controller is not None:
        spawn(app_controller.play_adjacent(delta), name="play-adjacent")


def _in_overlay(page, node) -> bool:
    """Identity membership — controls are dataclasses, so ``in`` compares by
    value and would match a structurally-equal node."""
    return node is not None and any(node is m for m in page.overlay)


_resolve_mount = None
_resolve_stage_shown = None


def _use_resolve_overlay(state, controller) -> None:
    """Mount the "Resolving stream…" stage into page.overlay.

    Imperative (same reasoning as the player): it must be replaceable when
    the stage text changes without re-rendering the whole shell, and it has
    to sit above the detail screen the tap came from.
    """
    global _resolve_mount, _resolve_stage_shown

    try:
        page = flet_context.page
    except Exception:
        page = None
    if page is None:
        return

    stage = state.resolve_stage if state.is_resolving else None
    if stage is None:
        if _resolve_mount is not None and _in_overlay(page, _resolve_mount):
            page.overlay.remove(_resolve_mount)
            page.update()
        _resolve_mount = None
        _resolve_stage_shown = None
        return

    if stage == _resolve_stage_shown and _in_overlay(page, _resolve_mount):
        return  # already showing this stage

    if _resolve_mount is not None and _in_overlay(page, _resolve_mount):
        page.overlay.remove(_resolve_mount)

    _resolve_mount = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
                ft.Container(height=16),
                ft.Text(
                    stage,
                    size=15,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(height=8),
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda e: controller.cancel_resolve(),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        ),
    )
    _resolve_stage_shown = stage
    page.overlay.append(_resolve_mount)
    page.update()


def _unmount_player_overlay(page) -> None:
    global _active_player, _active_mount, _active_key

    mount, _active_mount, _active_player, _active_key = (
        _active_mount,
        None,
        None,
        None,
    )
    if mount is not None and page is not None and _in_overlay(page, mount):
        page.overlay.remove(mount)
        page.update()


def _use_player_overlay(state, controller) -> None:
    """Mount/unmount the player in page.overlay as playback state changes.

    Controls built inside a @ft.component render are frozen after mount,
    and ImmersivePlayer rewrites itself constantly (overlay visibility,
    retry buttons, playback rate, quality swap). KTV mounts its player in
    a ft.View for exactly this reason; page.views is gone in flet 1.0.4, so
    page.overlay is the equivalent top-level slot. The key comparison is
    what makes retries and episode switches remount instead of reusing a
    stale stage.
    """
    global _active_player, _active_mount, _active_key

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None
    if page is None:
        return

    if not state.player_open:
        _unmount_player_overlay(page)
        return

    error = getattr(state, "player_error", None)
    spec = getattr(state, "player_spec", None) or {}
    if error:
        key = ("error", error)
    else:
        key = ("play", spec.get("episode_session"), spec.get("resource"))

    if key == _active_key and _in_overlay(page, _active_mount):
        return  # already showing exactly this stage
    _unmount_player_overlay(page)

    if error:
        mount = _build_player_error(state, controller, error)
        player = None
    else:
        from components.player.immersive_player import ImmersivePlayer
        from services.store import get_store

        player = ImmersivePlayer(
            resource=spec.get("resource", ""),
            title=spec.get("title", ""),
            http_headers=spec.get("source_headers"),
            resume_key=spec.get("episode_session"),
            store=get_store(),
            variants=spec.get("variants") or [],
            on_close=lambda: _close_player(),
            on_next=lambda: _play_adjacent(1, controller),
            on_previous=lambda: _play_adjacent(-1, controller),
            source_url=spec.get("source_url"),
            source_referer=spec.get("source_referer"),
            source_headers=spec.get("source_headers"),
            proxied=spec.get("proxied", False),
            subtitles=spec.get("subtitles") or [],
            skip=spec.get("skip") or {},
        )
        # The controller owns the proxy; the player needs it to rebuild a
        # url when a quality or an audio track is pinned.
        app_controller = getattr(controller, "_app_controller", None)
        player.hls_proxy = getattr(app_controller, "hls_proxy", None)
        # focus_scope is a plain FUNCTION (KTV's form): the old
        # @ft.component FocusScope rendered a frozen subtree — the exact
        # crash class this overlay mount exists to avoid.
        from hooks.use_focus_scope import focus_scope

        mount = focus_scope(player, lambda: _player_back())

    _active_player, _active_mount, _active_key = player, mount, key
    page.overlay.append(mount)
    page.update()


def _build_player_error(state, controller, message: str) -> ft.Control:
    """Playback couldn't start: same black stage as the player so the
    transition never flashes the app behind it."""
    session = getattr(state, "current_episode_session", "")

    def _retry():
        state.player_error = None
        state.episodes_version += 1
        spawn(
            controller._app_controller.play_downloaded(session),
            name="retry-downloaded",
        )

    def _back():
        state.player_error = None
        state.player_open = False
        state.episodes_version += 1

    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.BLACK,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=64, color=AppColors.ERROR),
                ft.Container(height=16),
                ft.Text(
                    "Playback unavailable",
                    size=20,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(height=8),
                ft.Text(
                    message,
                    size=14,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            content="Retry",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda e: _retry(),
                        ),
                        ft.OutlinedButton(
                            content="Go Back",
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            on_click=lambda e: _back(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )


async def _player_back():
    # Back from the remote/keyboard: let the player save its position
    # (bounded, 3s) before the shell tears it down.
    player = _active_player
    if player is not None:
        try:
            await player.handle_close()
        except Exception:
            pass
    await _async_close_player()


async def _async_close_player():
    global _active_player, _active_mount, _active_key

    from flet import context as flet_context

    from state.app_state import state

    # Save + stop the native player FIRST: this runs for programmatic closes
    # (Next/Previous, controller.close_player) as well as Back, and skipping
    # it loses the resume position and lets audio bleed into the next episode.
    player = _active_player
    if player is not None:
        try:
            await asyncio.wait_for(player.handle_close(), timeout=3.0)
        except Exception:
            pass

    mount = _active_mount
    _active_mount = None
    _active_player = None
    _active_key = None
    state.player_open = False
    state.episodes_version += 1
    # Unmount the overlay node the shell mounted imperatively.
    if mount is not None:
        try:
            page = flet_context.page
        except Exception:
            page = None
        if page is not None and _in_overlay(page, mount):
            try:
                page.overlay.remove(mount)
                page.update()
            except Exception:
                pass


def _close_player():
    from flet import context as flet_context

    page = flet_context.page
    if page is None:
        return
    page.run_task(_player_back)


def _detail_appbar(controller) -> ft.Control:
    return ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: controller.back(),
            tooltip="Back",
        ),
        title=ft.Text("Anime", weight=ft.FontWeight.W_600),
        bgcolor=ft.Colors.TRANSPARENT,
        center_title=False,
    )


def _build_download_quality_dialog(state, controller) -> ft.Control:
    """Which rendition to save offline — the same list the play dialog
    shows, because a silent sources[0] downloads whatever the provider
    listed first (a 360p when a 1080p exists). The best is filled in as
    the recommendation."""
    choices = state.download_choices or []
    pending = state.pending_download or {}
    buttons = []
    for i, choice in enumerate(choices):
        is_first = i == 0
        buttons.append(
            (
                ft.FilledButton(
                    content=choice["label"],
                    icon=ft.Icons.RECOMMEND_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                    on_click=lambda e, i=i: controller.choose_download_quality(i),
                )
                if is_first
                else ft.OutlinedButton(
                    content=choice["label"],
                    on_click=lambda e, i=i: controller.choose_download_quality(i),
                )
            )
        )
    label = f"{pending.get('title', '')} — Episode {pending.get('episode_num', '?')}"
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(
            f"Download quality — {label}".strip(" —"),
            weight=ft.FontWeight.W_600,
        ),
        content=ft.Column(
            controls=[
                ft.Text(
                    "Saved in the format the source serves — nothing is converted.",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                *buttons,
            ],
            tight=True,
            spacing=10,
        ),
        actions=[
            ft.TextButton(
                content="Cancel",
                on_click=lambda e: controller.close_dialog(),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _build_backend_picker(state, controller) -> ft.Control:
    """Which provider is serving, every provider's live health, and
    one-tap pinning — the header badge's destination. The health rows are
    the router's own breaker state, so the picker explains a switch
    instead of just announcing one."""
    health = controller.sources_status() if hasattr(controller, "sources_status") else {}
    providers = sorted({*health, state.current_source_name} - {""})
    current = (state.current_source_name or "").strip()

    def _row(name: str) -> ft.Control:
        h = health.get(name) or {}
        rec = str(h.get("state") or "")
        colour = (
            AppColors.ERROR
            if rec == "open"
            else AppColors.WARNING
            if rec == "half_open"
            else AppColors.SUCCESS
        )
        detail = "never probed"
        if h.get("checked_at"):
            latency = h.get("latency_ms")
            detail = f"{latency:.0f}ms" if isinstance(latency, (int, float)) else "—"
            if h.get("last_error"):
                detail += f" · {str(h['last_error'])[:40]}"
        selected = current == name
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=8, height=8, border_radius=4, bgcolor=colour),
                    ft.Container(width=8),
                    ft.Text(name.capitalize(), size=13, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Text(detail, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        "serving now" if selected else "tap to pin",
                        size=11,
                        color=ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            border_radius=8,
            border=ft.Border.all(
                1.5 if selected else 1,
                ft.Colors.PRIMARY if selected else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
            ),
            ink=True,
            on_click=lambda e, n=name: controller.pin_backend(n),
        )

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Content source", weight=ft.FontWeight.W_700),
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text("Automatic", size=13, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.Text(
                                "any healthy source, in order",
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                "active" if not current else "tap to choose",
                                size=11,
                                color=ft.Colors.PRIMARY if not current else ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=10),
                    border_radius=8,
                    border=ft.Border.all(
                        1.5 if not current else 1,
                        ft.Colors.PRIMARY if not current else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                    ),
                    ink=True,
                    on_click=lambda e: controller.pin_backend("auto"),
                ),
                *[_row(name) for name in providers],
                ft.Text(
                    "A pinned source still fails over — the pin only changes who goes first.",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=8,
        ),
        actions=[
            ft.TextButton(
                content="Close", on_click=lambda e: controller.close_dialog()
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _build_quality_dialog(state, controller) -> ft.Control:
    """Select Quality & Audio — every site source the scraper found, best
    first, exactly the list the original build showed. Nothing is filtered:
    an anime with 3 qualities in 2 languages shows all of them. The best
    pick is simply filled in as the recommended default, and the m3u8
    variants of whatever is chosen live in the player's own settings sheet.
    """
    choices = state.quality_choices or []
    # A site-source choice re-resolves through kwik (seconds): disable the
    # buttons and show the spinner while it happens.
    resolving = bool(getattr(state, "quality_resolving", False))
    buttons = []
    for i, choice in enumerate(choices):
        is_first = i == 0
        buttons.append(
            (
                ft.FilledButton(
                    content=choice["label"],
                    icon=ft.Icons.RECOMMEND_ROUNDED,
                    disabled=resolving,
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                    on_click=lambda e, i=i: controller.choose_quality(i),
                )
                if is_first
                else ft.OutlinedButton(
                    content=choice["label"],
                    disabled=resolving,
                    on_click=lambda e, i=i: controller.choose_quality(i),
                )
            )
        )
    return ft.AlertDialog(
        modal=True,
        title=ft.Row(
            [
                ft.Text(
                    "Select Quality & Audio",
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
                ft.ProgressRing(
                    width=16,
                    height=16,
                    stroke_width=2,
                    visible=resolving,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Column(
            controls=[
                ft.Text(
                    "Tip: If the player does not start, try again. Make sure "
                    "you already have the player installed.",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                *buttons,
            ],
            tight=True,
            spacing=10,
        ),
        actions=[
            ft.TextButton(
                content="Cancel",
                on_click=lambda e: controller.close_dialog(),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
