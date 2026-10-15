"""Anime detail — backdrop, poster, metadata, episode grid.

Craft carried from the original view: the blurred-poster backdrop (poster at
30% + surface wash), 200x300 poster with shadow, responsive title, bullet
metadata row, and 1.67 episode cards with the focus-ring border reserve.

Data comes from the controller (Phase 1). Phase 2 makes this screen fetch
its own anime by session — today it reads state.episodes like the old view.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from components.pagination import pager as ft_pager
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _episode_card(
    ep,
    on_play,
    anime_session: str,
    now_playing: bool,
    state_glyph=None,
    menu_items=None,
) -> ft.Control:
    image = (
        ft.Image(src=ep.snapshot, fit=ft.BoxFit.COVER, expand=True)
        if ep.snapshot
        else ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH)
    )
    # Compact three-dot overflow (the KTV full-dialog treatment was
    # rejected): items are built per episode state, so the menu never
    # shows an action the current state can't honour.
    #
    # A SIBLING of the play button, not nested in its content: an
    # activatable control inside a Button's content swallows the card's
    # on_play on tap AND is unreachable for D-pad focus (focus sits on
    # the parent button). Overlaid in a Stack so the visual position is
    # unchanged.
    overflow = ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT_ROUNDED,
        icon_size=20,
        icon_color=ft.Colors.WHITE,
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip="Episode options",
        items=menu_items
        or [
            ft.PopupMenuItem(
                content="Play",
                icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                height=40,
                on_click=lambda e: on_play(anime_session, ep.session),
            )
        ],
    )
    content = ft.Stack(
        [
            image,
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.CENTER_LEFT,
                    end=ft.Alignment.CENTER_RIGHT,
                    colors=[
                        ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
                        ft.Colors.TRANSPARENT,
                    ],
                ),
                expand=True,
            ),
            ft.Container(
                padding=16,
                alignment=ft.Alignment.CENTER_LEFT,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Episode {ep.episode}",
                                    color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.BOLD,
                                    size=16,
                                ),
                                ft.Container(width=6),
                                ft.Container(
                                    content=ft.Text(
                                        "Filler",
                                        size=9,
                                        weight=ft.FontWeight.W_700,
                                        color=AppColors.WARNING,
                                    ),
                                    padding=ft.Padding.symmetric(
                                        horizontal=5, vertical=1
                                    ),
                                    border_radius=4,
                                    border=ft.Border.all(
                                        1,
                                        ft.Colors.with_opacity(0.4, AppColors.WARNING),
                                    ),
                                    visible=bool(ep.filler),
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            " • ".join(
                                [ep.duration or "24m"]
                                + (["SUB"] if getattr(ep, "subs", False) else [])
                                + (["DUB"] if getattr(ep, "dub", False) else [])
                                + (
                                    [_fmt_air_date(getattr(ep, "aired_ts", 0))]
                                    if getattr(ep, "aired_ts", 0)
                                    else []
                                )
                            ),
                            size=12,
                            color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=4,
                ),
            ),
            ft.Container(
                alignment=ft.Alignment.CENTER_RIGHT,
                padding=16,
                content=ft.Row(
                    [
                        state_glyph or ft.Container(width=0),
                        ft.Icon(
                            ft.Icons.EQUALIZER_ROUNDED
                            if now_playing
                            else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                            size=40,
                            color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        ],
        expand=True,
    )
    # Flat FilledButton so the D-pad can focus the episode (Container cards
    # are unreachable on TV in flet 1.0.4); the FOCUSED side + scale are
    # the focus ring. The menu is a Stack SIBLING — not button content, so
    # D-pad reaches it and a tap on it no longer plays the card.
    return ft.Stack(
        [
            attach_focus_zoom(
                ft.FilledButton(
                    content=content,
                    style=card_button_style(radius=16),
                    aspect_ratio=1.67,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    animate_scale=card_focus_scale(),
                    on_click=lambda e: on_play(anime_session, ep.session),
                )
            ),
            ft.Container(
                alignment=ft.Alignment.TOP_RIGHT,
                padding=ft.Padding.only(top=14, right=10),
                content=overflow,
            ),
        ],
        expand=True,
    )


@ft.component
def AnimeDetailScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.episodes_version
    _ = state.busy_version  # download-start spinners, quality resolving

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    anime_session = state.current_anime_session
    episodes = state.episodes

    # Title/poster come from the controller's resolution chain (in-memory
    # → Continue Watching store → nothing for a cold link). Phase 3 adds a
    # metadata endpoint that removes the last fallback.
    anime = state.selected_anime or {}
    title = anime.get("title") or "Loading..."
    poster = anime.get("poster")

    if not episodes and state.is_loading:
        return ft.Container(
            content=ft.ProgressRing(color=AppColors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    if not episodes:
        return EmptyState(
            "No episodes found",
            message="This series may have no releases yet — try again later.",
            icon=ft.Icons.MOVIE_FILTER_ROUNDED,
        )

    # The page's own cover when the source serves one, else the blurred
    # poster (the shape this screen always had).
    backdrop_src = anime.get("backdrop") or poster
    backdrop = ft.Stack(
        [
            ft.Image(src=backdrop_src, fit=ft.BoxFit.COVER, expand=True, opacity=0.3)
            if backdrop_src
            else ft.Container(bgcolor=ft.Colors.SURFACE),
            ft.Container(
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.SURFACE),
            ),
        ],
        expand=True,
    )

    poster_box = ft.Container(
        width=200,
        height=300,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        shadow=ft.BoxShadow(
            spread_radius=2,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            offset=ft.Offset(0, 10),
        ),
        content=ft.Image(src=poster, fit=ft.BoxFit.COVER, expand=True)
        if poster
        else ft.Container(
            content=ft.Icon(
                ft.Icons.MOVIE_ROUNDED, size=64, color=ft.Colors.ON_SURFACE_VARIANT
            ),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        ),
    )

    now_playing = {
        "anime": state.current_anime_session,
        "episode": state.current_episode_session,
    }
    downloads = state.downloads or {}
    download_progress = state.download_progress or {}

    def _episode_state(ep) -> tuple[object, list]:
        """(trailing state control, overflow menu items) for one episode.

        Download moved out from under the card and into a compact three-dot
        menu carried inside the row — one tap for play, one for everything
        else. The trailing slot only ever shows a *passive* state glyph
        (done check, or a spinner while a job is starting/running), never a
        second tappable button.
        """
        row = downloads.get(ep.session) or {}
        active = ep.session in download_progress
        starting = ep.session in state.starting_downloads
        done = row.get("state") == "complete"

        trailing: object = ft.Container(width=0)
        if done:
            trailing = ft.Icon(
                ft.Icons.DOWNLOAD_DONE_ROUNDED,
                size=18,
                color=AppColors.SUCCESS,
            )
        elif starting or active:
            # Source + kwik resolve before the job starts — spin instead of
            # looking like the tap did nothing.
            trailing = ft.ProgressRing(width=16, height=16, stroke_width=2)

        items = [
            ft.PopupMenuItem(
                content="Play",
                icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                height=40,
                on_click=lambda e, s=ep.session: controller.play_episode(
                    anime_session, s
                ),
            ),
        ]
        if done:
            items.append(
                ft.PopupMenuItem(
                    content="Play offline",
                    icon=ft.Icons.DOWNLOAD_DONE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.play_downloaded(s),
                )
            )
            items.append(
                ft.PopupMenuItem(
                    content="Delete download",
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.delete_download(s),
                )
            )
        elif active or starting:
            items.append(
                ft.PopupMenuItem(
                    content="Cancel download",
                    icon=ft.Icons.CLOSE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.cancel_download(s),
                )
            )
        else:
            items.append(
                ft.PopupMenuItem(
                    content="Download",
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.download_episode(
                        anime_session, s
                    ),
                )
            )
        # Broken-stream reporting: the watch page's own form works
        # anonymously, so the report is offered where the user actually is.
        items.append(
            ft.PopupMenuItem(
                content="Report a problem",
                icon=ft.Icons.FLAG_OUTLINED,
                height=40,
                on_click=lambda e, s=ep.session: _open_report(s),
            )
        )
        return trailing, items

    def _open_series_download():
        """The whole-series dialog: a range, a quality preset, and N
        independent queued jobs (each failure is its own episode's)."""
        controller.open_sheet(
            _build_series_download_dialog(
                state.episodes, controller, anime_session, state.downloads
            )
        )

    def _open_report(episode_session: str):
        """The site's own issue vocabulary, plus a note. An empty pick is
        the site's own validation message, surfaced verbatim.

        No hooks: this dialog is built inside an event handler, so the
        note rides a plain cell (a setter call would raise — use_state is
        render-time only). Checked issues are scoped per dialog open."""
        from core.tasks import spawn

        checked: set[str] = set()
        cell = {"note": ""}

        def _toggle_issue(value: str):
            if value in checked:
                checked.discard(value)
            else:
                checked.add(value)

        def _send():
            controller.close_dialog()
            spawn(
                controller.report_broken_stream(
                    anime_session, episode_session, sorted(checked), cell["note"]
                ),
                name="report-broken",
            )

        controller.open_sheet(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Report a problem", weight=ft.FontWeight.W_700),
                content=ft.Column(
                    [
                        ft.Text(
                            "This goes to the source's own report form.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        *[
                            ft.Checkbox(
                                label=label,
                                value=value in checked,
                                on_change=lambda e, v=value: _toggle_issue(v),
                            )
                            for value, label in _report_issues()
                        ],
                        ft.TextField(
                            hint_text="Anything else?",
                            multiline=True,
                            min_lines=2,
                            max_lines=4,
                            on_change=lambda e: cell.__setitem__(
                                "note", e.control.value or ""
                            ),
                        ),
                    ],
                    tight=True,
                    spacing=8,
                ),
                actions=[
                    ft.TextButton(
                        content="Cancel",
                        on_click=lambda e: controller.close_dialog(),
                    ),
                    ft.FilledButton(content="Send report", on_click=lambda e: _send()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def _render_ep_cards():
        cards = []
        for ep in episodes:
            state_glyph, menu_items = _episode_state(ep)
            cards.append(
                ft.Container(
                    content=_episode_card(
                        ep,
                        controller.play_episode,
                        anime_session,
                        now_playing["anime"] == anime_session
                        and now_playing["episode"] == ep.session,
                        state_glyph=state_glyph,
                        menu_items=menu_items,
                    ),
                    col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
                )
            )
        return cards

    grid = ft.ResponsiveRow(
        controls=_render_ep_cards(),
        spacing=12,
        run_spacing=12,
    )

    pager = ft_pager(
        page=state.episodes_page,
        has_more=state.episodes_has_more,
        on_prev=lambda e: controller.load_episodes(
            anime_session, state.episodes_page - 1
        ),
        on_next=lambda e: controller.load_episodes(
            anime_session, state.episodes_page + 1
        ),
        is_loading=state.is_loading,
    )

    # Favorites are per-ANIME, never per episode: one button in the header.
    _ = state.follows_version
    following = anime_session in (state.follows or {})

    def _toggle_follow():
        controller.toggle_follow(
            {
                "anime_session": anime_session,
                "title": title,
                "poster": poster or "",
                "type": anime.get("type", ""),
                "year": anime.get("year", 0),
                "status": anime.get("status", ""),
                "score": anime.get("score", 0),
            }
        )

    follow_button = attach_focus_zoom(
        ft.FilledButton(
            content=ft.Text("Following" if following else "Follow"),
            icon=ft.Icons.FAVORITE_ROUNDED
            if following
            else ft.Icons.FAVORITE_BORDER_ROUNDED,
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY if following else ft.Colors.TRANSPARENT,
                color=ft.Colors.WHITE if following else ft.Colors.ON_SURFACE,
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(1 if not following else 0, AppColors.PRIMARY),
            ),
            on_click=lambda e: _toggle_follow(),
        )
    )

    def _metadata_row(anime: dict) -> ft.Control:
        """year / type / status / N Episodes / score / studio, as the
        original."""
        parts = []
        if anime.get("year"):
            parts.append(str(anime["year"]))
        if anime.get("type"):
            parts.append(anime["type"])
        if anime.get("status"):
            parts.append(anime["status"])
        if anime.get("episodes"):
            parts.append(f"{anime['episodes']} Episodes")
        if anime.get("score"):
            parts.append(f"★ {float(anime['score']):.1f}")
        # Studios as well as the aired range — both parsed, neither shown
        # before now.
        studios = [
            str(s).strip() for s in (anime.get("studios") or []) if str(s).strip()
        ]
        if studios:
            parts.append("/".join(studios[:2]))
        if anime.get("aired"):
            parts.append(str(anime["aired"]))
        if not parts:
            return ft.Container(width=0, height=0)
        return ft.Text(
            " • ".join(parts),
            size=14,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

    def _genre_chips(anime: dict) -> ft.Control:
        """Genres as chips — the providers parse them, they just never
        reached a screen."""
        genres = [str(g).strip() for g in (anime.get("genres") or []) if str(g).strip()]
        if not genres:
            return ft.Container(width=0, height=0)
        return ft.Row(
            [
                ft.Container(
                    content=ft.Text(g, size=12, weight=ft.FontWeight.W_500),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    border_radius=14,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.25, ft.Colors.ON_SURFACE)
                    ),
                )
                for g in genres[:8]
            ],
            spacing=6,
            wrap=True,
        )

    def _synopsis_block(anime: dict) -> ft.Control:
        """Synopsis + the external ids. Clamped, not scrolled: the
        episodes grid below is the point of the screen."""
        synopsis = str(anime.get("synopsis") or "").strip()
        ids = []
        if anime.get("mal_id"):
            ids.append(f"MAL {anime['mal_id']}")
        if anime.get("anilist_id"):
            ids.append(f"AniList {anime['anilist_id']}")
        if not synopsis and not ids:
            return ft.Container(width=0, height=0)
        children: list[ft.Control] = [ft.Container(height=16)]
        if synopsis:
            children.append(
                ft.Text(
                    synopsis,
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=4,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        if ids:
            children.append(ft.Container(height=6))
            children.append(
                ft.Text(
                    " • ".join(ids),
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE_VARIANT),
                )
            )
        return ft.Column(children, tight=True, spacing=0)

    return ft.Stack(
        [
            backdrop,
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                poster_box,
                                ft.Container(width=24),
                                ft.Column(
                                    [
                                        ft.Text(
                                            title,
                                            size=28,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.ON_SURFACE,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Container(height=8),
                                        _metadata_row(anime),
                                        ft.Container(height=12),
                                        _genre_chips(anime),
                                        ft.Container(height=12),
                                        follow_button,
                                    ],
                                    expand=True,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Container(height=16),
                        _synopsis_block(anime),
                        ft.Container(height=24),
                        ft.Row(
                            [
                                ft.Text(
                                    "Episodes",
                                    size=20,
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE,
                                ),
                                ft.Container(expand=True),
                                # Whole-series download (Netflix's "Download
                                # Season"): a range + a quality preset, then
                                # N independent queued jobs.
                                ft.TextButton(
                                    content="Download the series",
                                    icon=ft.Icons.DOWNLOAD_FOR_OFFLINE_ROUNDED,
                                    on_click=lambda e: _open_series_download(),
                                ),
                                # Which provider served these episodes, and
                                # one-tap failover when this source misses.
                                ft.Text(
                                    f"Source: {state.current_source_name.capitalize()}"
                                    if state.current_source_name
                                    else "",
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.TextButton(
                                    content="Try another source",
                                    on_click=lambda e: controller.try_another_source(
                                        anime_session
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=8),
                        grid,
                        build_banner_ad(page, inline=True),
                        pager,
                        ft.Container(height=32),
                    ],
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                padding=ft.Padding.all(24),
                expand=True,
            ),
        ],
        expand=True,
    )


def _fmt_air_date(ts: int) -> str:
    """A unix air time as the card's short date (local). 0/absent never
    reaches here."""
    import datetime as _dt

    return _dt.datetime.fromtimestamp(int(ts)).strftime("%b %d %Y")


_REPORT_ISSUES = ()


def _report_issues() -> tuple[tuple[str, str], ...]:
    """The serving provider's own issue vocabulary (anikato's form is the
    one that works anonymously). Discovered, not hardcoded."""
    global _REPORT_ISSUES
    if not _REPORT_ISSUES:
        from services.providers.anikato import REPORT_ISSUES

        _REPORT_ISSUES = REPORT_ISSUES
    return _REPORT_ISSUES


def _build_series_download_dialog(episodes, controller, anime_session, downloads, ui=None):
    """Range + quality preset for a whole-series download.

    The range defaults to everything not already downloaded; the user
    narrows it, picks a quality, and the batch queues as N independent
    jobs. No hooks here — this is built inside an event handler, so the
    UI state is a plain cell and a preset tap re-opens the sheet."""
    from core.tasks import spawn

    ui = ui if ui is not None else {"preset": "highest"}
    episodes = list(episodes or [])
    nums = [e.episode for e in episodes]
    lo, hi = (min(nums), max(nums)) if nums else (1, 1)
    # Already-complete episodes are excluded from the default range.
    done = {s for s, r in (downloads or {}).items() if r.get("state") == "complete"}

    from_ctl = ft.TextField(value=str(lo), width=70, keyboard_type=ft.KeyboardType.NUMBER)
    to_ctl = ft.TextField(value=str(hi), width=70, keyboard_type=ft.KeyboardType.NUMBER)

    def _range():
        def _num(field, fallback):
            try:
                return int(float(field.value or fallback))
            except (TypeError, ValueError):
                return fallback

        return _num(from_ctl, lo), _num(to_ctl, hi)

    def _send():
        start, end = _range()
        chosen = [
            e.session
            for e in episodes
            if start <= e.episode <= end and e.session not in done
        ]
        controller.close_dialog()
        spawn(
            controller.download_series(anime_session, chosen, ui["preset"]),
            name="download-series",
        )

    def _preset(value):
        ui["preset"] = value
        # The ui cell must ride as the ui= kwarg — it used to land in the
        # `downloads` slot (the preset never stuck, and the range math
        # called .get() on the string). `downloads` is this builder's own
        # argument, so the re-open keeps the same completed-exclusion set.
        controller.open_sheet(
            _build_series_download_dialog(
                episodes, controller, anime_session, downloads, ui
            )
        )

    count = len([e for e in episodes if lo <= e.episode <= hi and e.session not in done])
    sizes = [float(getattr(e, "size", "") or 0) for e in episodes if getattr(e, "size", "")]
    summary = f"{count} episodes"
    if sizes:
        summary += f" · ~{sum(sizes) / 1024:.0f}MB"

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Download the series", weight=ft.FontWeight.W_700),
        content=ft.Column(
            [
                ft.Text(summary, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row([ft.Text("From"), from_ctl, ft.Text("to"), to_ctl], spacing=8),
                ft.Text("Quality", size=13, weight=ft.FontWeight.W_700),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            content=label,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.PRIMARY)
                                if ui["preset"] == value
                                else None
                            ),
                            on_click=lambda e, v=value: _preset(v),
                        )
                        for value, label in (
                            ("highest", "Highest"),
                            ("lowest", "Lowest"),
                            ("as-served", "As served"),
                        )
                    ],
                    spacing=6,
                ),
                ft.Text(
                    "Each episode is saved exactly as the provider serves it — "
                    "nothing is converted.",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=10,
        ),
        actions=[
            ft.TextButton(
                content="Cancel", on_click=lambda e: controller.close_dialog()
            ),
            ft.FilledButton(content="Download", on_click=lambda e: _send()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
