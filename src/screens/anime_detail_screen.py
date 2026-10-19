"""Anime detail — backdrop, poster, metadata, episode grid.

Craft carried from the original view: the blurred-poster backdrop (poster at
30% + surface wash), 200x300 poster with shadow, responsive title, bullet
metadata row, and episode cards in the detected grid shape with the
focus-ring border reserve.

Data comes from the controller (Phase 1). Phase 2 makes this screen fetch
its own anime by session — today it reads state.episodes like the old view.
"""

import contextlib

import flet as ft

from components.ad_breaks import grid_with_ads
from components.artwork_card import art_fallback, card_frame, card_media
from components.focus_styles import attach_focus_zoom
from components.offline_state import empty_or_offline
from components.pagination import pager as ft_pager
from core.artwork import PORTRAIT
from core.theme import AppColors
from hooks.use_grid_mode import grid_sources, use_grid_mode
from services.hls_proxy import image_url
from services.providers.base import owner_of
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _episode_card(
    ep,
    on_play,
    anime_session: str,
    now_playing: bool,
    state_glyph=None,
    menu_items=None,
    mode: str = PORTRAIT,
    fallback_src: str = "",
    provider: str = "",
) -> ft.Control:
    """One episode, rendered as the DISCOVER card (owner's order: the
    episode grid matches the Discover grid's size and anatomy on every
    source — same portrait poster, same centered play glyph, same
    bottom-left title block, same padding). Only the top-right overflow
    is an episode-specific addition, and it is a Stack SIBLING of the
    play button (an activatable control inside a Button's content
    swallows the tap AND is unreachable for D-pad focus)."""
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
    # The subtitle line carries what the source actually published —
    # duration, SUB/DUB, air date — joined, never invented.
    facts = " • ".join(
        [ep.duration or "24m"]
        + (["SUB"] if getattr(ep, "subs", False) else [])
        + (["DUB"] if getattr(ep, "dub", False) else [])
        + (
            [_fmt_air_date(getattr(ep, "aired_ts", 0))]
            if getattr(ep, "aired_ts", 0)
            else []
        )
    )
    overlay = [
        ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[
                    ft.Colors.TRANSPARENT,
                    ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
                ],
            ),
            expand=True,
        ),
        ft.Container(
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                [
                    state_glyph or ft.Container(width=0),
                    ft.Icon(
                        ft.Icons.EQUALIZER_ROUNDED
                        if now_playing
                        else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                        size=48,
                        color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
        ),
        ft.Container(
            alignment=ft.Alignment.BOTTOM_LEFT,
            padding=12,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                f"Episode {ep.episode}",
                                color=ft.Colors.WHITE,
                                weight=ft.FontWeight.BOLD,
                                size=14,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    "Filler",
                                    size=9,
                                    weight=ft.FontWeight.W_700,
                                    color=AppColors.WARNING,
                                ),
                                padding=ft.Padding.symmetric(horizontal=5, vertical=1),
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
                        facts,
                        size=12,
                        color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=4,
            ),
        ),
    ]
    # The shared frame is a flat FilledButton, so the D-pad can focus the
    # episode (Container cards are unreachable on TV in flet 1.0.4). Art
    # falls back to the series poster (the backend's own) when the episode
    # has none.
    return ft.Stack(
        [
            card_frame(
                mode=mode,
                media=card_media(
                    ep.snapshot or fallback_src,
                    mode,
                    title=f"Episode {ep.episode}",
                    provider=provider,
                ),
                overlay=overlay,
                on_click=lambda e: on_play(anime_session, ep.session),
            ),
            ft.Container(
                alignment=ft.Alignment.TOP_RIGHT,
                padding=ft.Padding.only(top=8, right=4),
                content=overflow,
            ),
        ],
        expand=True,
    )


# Above this, the description earns a "Read more" (about four lines at the
# detail screen's width); below it the full text shows as-is.
LONG_SYNOPSIS_CHARS = 220


@ft.component
def AnimeDetailScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.episodes_version
    _ = state.busy_version  # download-start spinners, quality resolving
    # "About this release" expander (declared HERE: hooks are positional,
    # a use_state inside a nested builder would corrupt the mapping).
    about_open, set_about_open = ft.use_state(False)

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
    # The provider that owns this page — its referer rides the image route
    # when the platform wraps the artwork (web CORS / guarded hosts).
    provider = owner_of(state.current_anime_session or "")

    # The detected grid shape for the episode list (this backend's own art;
    # an episode with none falls back to the series poster below).
    episode_sources = grid_sources(episodes, lambda e: e.snapshot)
    grid_mode = use_grid_mode("episodes", episode_sources, state.current_source_name, state)

    from components.app_header import app_header

    def _titled(content: ft.Control) -> ft.Control:
        """Every branch of this screen keeps the shared header on top —
        the source pill/switcher must be visible even when the page has
        nothing else to show (owner's order: all screens, detail too).
        The Back control lives INSIDE that header (``on_back``): the owner
        rejected a second bar above it (2026-10-16)."""
        return ft.Column(
            [
                app_header(
                    state,
                    page,
                    controller,
                    subtitle="",
                    on_back=lambda: controller.back(),
                ),
                content,
            ],
            spacing=0,
            expand=True,
        )

    if not episodes and state.is_loading:
        return _titled(
            ft.Container(
                content=ft.ProgressRing(color=AppColors.PRIMARY),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        )

    # Whose anime is this? A Continue-Watching row (or a stale link) can
    # point at a session owned by a DIFFERENT backend than the active one.
    # Every chain here is OWNER-SCOPED, so the fetch still goes to the
    # session's own provider — and when that owner is AnimePahe its
    # Cloudflare flow must open for it (the owner's live run: tapping an
    # AnimePahe recent under another source showed "no episodes" and no
    # solver). The controller opens the gate for every user-driven load
    # (load_anime → load_episodes), so the window rides with the fetch.
    pinned = (state.current_source_name or "").strip()
    owner = owner_of(anime_session or "")
    owner_mismatch = bool(pinned and owner and owner != pinned)

    def _switch_to_owner(e=None):
        controller.set_backend_pin(owner or pinned)

    if not episodes:
        # The wall, not an empty catalogue: show the same SHIELD card Home
        # uses (Verify + Change source) instead of "No episodes found" —
        # the owner's report was exactly this dead end (2026-10-16).
        if getattr(state, "cf_blocked", False) and state.is_online:
            from components.offline_state import cf_gate_card

            return _titled(
                ft.Container(
                    content=ft.Column(
                        [
                            cf_gate_card(state, controller),
                            ft.Container(height=12),
                            ft.Text(
                                "The episode list loads again the moment the check passes.",
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                )
            )
        if owner_mismatch:
            return _titled(empty_or_offline(
                state,
                title=f"This anime belongs to {owner.capitalize()}",
                message=(
                    f"{pinned.capitalize()} is the current source, so its catalogue "
                    f"is what loads. Switch to {owner.capitalize()} to open this series."
                ),
                icon=ft.Icons.SWAP_HORIZ_ROUNDED,
                action_label=f"Switch to {owner.capitalize()}",
                on_retry=_switch_to_owner,
            ))
        return _titled(
            empty_or_offline(
                state,
                title="No episodes found",
                message="This series may have no releases yet — try again later.",
                icon=ft.Icons.MOVIE_FILTER_ROUNDED,
                on_retry=lambda e: controller.load_anime(state.current_anime_session),
                on_downloads=lambda e: controller.open_downloads(),
            )
        )

    # The page's own cover when the source serves one, else the blurred
    # poster (the shape this screen always had).
    backdrop_src = anime.get("backdrop") or poster
    backdrop = ft.Stack(
        [
            ft.Image(
                src=image_url(backdrop_src, provider),
                fit=ft.BoxFit.COVER,
                expand=True,
                opacity=0.3,
            )
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
        content=ft.Image(src=image_url(poster, provider), fit=ft.BoxFit.COVER, expand=True)
        if poster
        else art_fallback(
            title,
            mode=PORTRAIT,
            badge=anime.get("type", "TV"),
            show_title=True,
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
                on_click=lambda e, s=ep.session: controller.play_episode(anime_session, s),
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
                    on_click=lambda e, s=ep.session: controller.download_episode(anime_session, s),
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

        checked: set[str] = set()
        cell = {"note": ""}

        def _toggle_issue(value: str):
            if value in checked:
                checked.discard(value)
            else:
                checked.add(value)

        def _send():
            controller.close_dialog()
            # Already spawned by the controller bridge — a second spawn()
            # here would hand create_task a Task, not a coroutine.
            controller.report_broken_stream(
                anime_session, episode_session, sorted(checked), cell["note"]
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
                            on_change=lambda e: cell.__setitem__("note", e.control.value or ""),
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
                        mode=grid_mode,
                        fallback_src=poster or "",
                        provider=provider,
                    ),
                    # The DISCOVER spans, verbatim (owner's order: episodes
                    # match the Discover grid on every breakpoint — 2 up on
                    # a phone, denser on TV — instead of the old
                    # one-giant-card-per-row phone layout).
                    col={"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2},
                )
            )
        return cards

    grid = ft.Column(
        # A banner every 12 episodes, then one before the pager (the shared
        # grid rule — owner's order, 2026-10-16).
        controls=grid_with_ads(_render_ep_cards(), page, spacing=12, run_spacing=12),
        spacing=12,
    )

    pager = ft_pager(
        page=state.episodes_page,
        has_more=state.episodes_has_more,
        on_prev=lambda e: controller.load_episodes(anime_session, state.episodes_page - 1),
        on_next=lambda e: controller.load_episodes(anime_session, state.episodes_page + 1),
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
            icon=ft.Icons.FAVORITE_ROUNDED if following else ft.Icons.FAVORITE_BORDER_ROUNDED,
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
        studios = [str(s).strip() for s in (anime.get("studios") or []) if str(s).strip()]
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
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.ON_SURFACE)),
                )
                for g in genres[:8]
            ],
            spacing=6,
            wrap=True,
        )

    def _synopsis_block(anime: dict) -> ft.Control:
        """About this release: the description the serving backend
        publishes (anikato/animepahe's synopsis, the WP pair's post text),
        plus the external ids. Clamped to four lines with a "Read more"
        expander — the whole text is one tap away, and the episodes grid
        below stays the point of the screen. A source with neither text
        nor ids renders nothing at all."""
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
            long_text = len(synopsis) > LONG_SYNOPSIS_CHARS
            children.append(
                ft.Text(
                    synopsis,
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    max_lines=None if (about_open or not long_text) else 4,
                    overflow=ft.TextOverflow.CLIP if about_open else ft.TextOverflow.ELLIPSIS,
                )
            )
            if long_text:
                children.append(ft.Container(height=4))
                children.append(
                    ft.TextButton(
                        content="Show less" if about_open else "Read more",
                        on_click=lambda e: set_about_open(not about_open),
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

    # Phone (portrait width) gets the BANNER-FIRST hero the owner asked
    # for: the series' own cover across the top (16:9, with the poster
    # floating over its lower edge), then the title on its own line and
    # the facts wrapped beneath it. The old shape squeezed poster + title
    # + metadata + chips into one side-by-side row on a phone — cramped,
    # with dead space above and below the banner (owner's report,
    # 2026-10-16). TV / wide keeps the classic side-by-side hero.
    width = getattr(page, "width", None) or 0
    platform = getattr(page, "platform", None)
    is_tv = platform is not None and platform == ft.PagePlatform.ANDROID_TV
    compact = bool(page is not None and not is_tv and 0 < width < 720)

    hero_cover = ft.Container(
        aspect_ratio=16 / 7,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Stack(
            [
                ft.Image(
                    src=image_url(backdrop_src, provider),
                    fit=ft.BoxFit.COVER,
                    expand=True,
                )
                if backdrop_src
                else ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH),
                # Legibility scrim under the title block below.
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_CENTER,
                        end=ft.Alignment.BOTTOM_CENTER,
                        colors=[
                            ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
                            ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                        ],
                    ),
                ),
            ],
            expand=True,
        ),
    )
    # The poster hangs over the cover's lower edge WITHOUT a negative
    # offset (independent audit: R8 forbids negative-position hacks — they
    # clip across densities). The cover Stack is 20px TALLER than its art,
    # so the poster sits in the real bottom band, fully on-screen.
    compact_poster = ft.Container(
        width=96,
        height=140,
        right=8,
        border_radius=10,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border=ft.Border.all(2, ft.Colors.with_opacity(0.7, ft.Colors.BLACK)),
        shadow=ft.BoxShadow(
            blur_radius=14,
            color=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            offset=ft.Offset(0, 6),
        ),
        content=ft.Image(src=image_url(poster, provider), fit=ft.BoxFit.COVER, expand=True)
        if poster
        else art_fallback(
            title,
            mode=PORTRAIT,
            badge=anime.get("type", "TV"),
            show_title=False,
        ),
    )
    # The cover is the anchor Stack (absolute children position against
    # it). The poster sits in the real bottom band — the cover's aspect is
    # widened by 20px of honest Stack height, never a negative offset — so
    # it reads as floating over the art's lower edge on every density.
    compact_cover = ft.Container(
        content=ft.Stack(
            [
                ft.Column(
                    [
                        hero_cover,
                        # The poster's real band: 20px of empty Stack.
                        ft.Container(height=20),
                    ],
                    spacing=0,
                    tight=True,
                ),
                compact_poster,
            ],
            expand=True,
        ),
        expand=True,
    )
    compact_body = ft.Column(
        [
            # Space for the poster's band, then the title on its own line —
            # the owner's "banner first, text under it" shape. The synopsis
            # is NOT here: it renders once, after the hero, for both modes.
            ft.Container(height=16),
            ft.Text(
                title,
                size=22,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE,
                max_lines=3,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            ft.Container(height=6),
            _metadata_row(anime),
            ft.Container(height=10),
            _genre_chips(anime),
            ft.Container(height=12),
            follow_button,
        ],
        spacing=0,
        tight=True,
    )
    wide_hero = ft.Row(
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
    )
    hero: ft.Control = ft.Column(
        [compact_cover, compact_body] if compact else [wide_hero],
        spacing=0,
        tight=True,
    )

    return _titled(ft.Stack(
        [
            backdrop,
            ft.Container(
                content=ft.Column(
                    [
                        hero,
                        ft.Container(height=16),
                        _synopsis_block(anime),
                        ft.Container(height=16),
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
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=8),
                        grid,
                        ft.Container(height=8),
                        pager,
                        ft.Container(height=32),
                    ],
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12)
                if compact
                else ft.Padding.all(24),
                expand=True,
            ),
        ],
        expand=True,
    ))


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
        # REPORT_ISSUES is a CLASS attribute of the provider, not a module
        # constant — the old module-level import raised ImportError on the
        # first tap of the report menu (owner's log, 2026-10-16).
        from services.providers.anikato import AniKatoProvider

        _REPORT_ISSUES = tuple(AniKatoProvider.REPORT_ISSUES)
    return _REPORT_ISSUES


def _build_series_download_dialog(episodes, controller, anime_session, downloads, ui=None):
    """Range + quality preset for a whole-series download.

    The range defaults to everything not already downloaded; the user
    narrows it, picks a quality, and the batch queues as N independent
    jobs. No hooks here — this is built inside an event handler, so the
    UI state is a plain cell and a preset tap re-opens the sheet."""
    ui = ui if ui is not None else {"preset": "highest"}
    episodes = list(episodes or [])
    nums = [e.episode for e in episodes]
    lo, hi = (min(nums), max(nums)) if nums else (1, 1)
    # Already-complete episodes are excluded from the default range.
    done = {s for s, r in (downloads or {}).items() if r.get("state") == "complete"}

    # The range fields SWALLOW the first Escape (it ends the edit and
    # restores the value) instead of the dialog closing mid-keystroke —
    # the owner's report: typing "5" to replace "15" looked like the
    # modal simply vanishing.
    from core.focus_manager import FieldFocusTracker

    field_focus = FieldFocusTracker()

    from_ctl = ft.TextField(value=str(lo), width=70, keyboard_type=ft.KeyboardType.NUMBER)
    to_ctl = ft.TextField(value=str(hi), width=70, keyboard_type=ft.KeyboardType.NUMBER)

    def _restore_defaults():
        from_ctl.value = str(lo)
        to_ctl.value = str(hi)
        from_ctl.error = None
        to_ctl.error = None
        for ctl in (from_ctl, to_ctl):
            with contextlib.suppress(Exception):
                ctl.update()

    field_focus.attach(from_ctl, on_cancel=_restore_defaults)
    field_focus.attach(to_ctl, on_cancel=_restore_defaults)
    app_controller = getattr(controller, "_app_controller", None)
    if app_controller is not None:
        focus_manager = getattr(app_controller, "focus_manager", None)
        if focus_manager is not None:
            focus_manager.field_focus = field_focus

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
            e.session for e in episodes if start <= e.episode <= end and e.session not in done
        ]
        controller.close_dialog()
        controller.download_series(anime_session, chosen, ui["preset"])

    preset_buttons: dict[str, ft.OutlinedButton] = {}

    def _button_style(val: str) -> ft.ButtonStyle:
        is_active = ui["preset"] == val
        return ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.PRIMARY) if is_active else None,
            side=ft.BorderSide(1.5, AppColors.PRIMARY)
            if is_active
            else ft.BorderSide(1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)),
            color=AppColors.PRIMARY if is_active else ft.Colors.ON_SURFACE,
        )

    def _preset(value):
        ui["preset"] = value
        for val, btn in preset_buttons.items():
            btn.style = _button_style(val)
            with contextlib.suppress(Exception):
                btn.update()

    preset_row_controls = []
    for value, label in (
        ("highest", "Highest"),
        ("lowest", "Lowest"),
        ("as-served", "As served"),
    ):
        btn = ft.OutlinedButton(
            content=label,
            style=_button_style(value),
            on_click=lambda e, v=value: _preset(v),
        )
        preset_buttons[value] = btn
        preset_row_controls.append(btn)

    count = len([e for e in episodes if lo <= e.episode <= hi and e.session not in done])
    sizes = [float(getattr(e, "size", "") or 0) for e in episodes if getattr(e, "size", "")]
    # Never "0 episodes": an empty range (or an episode list that failed to
    # load) says so honestly instead of printing a zero.
    summary = f"{count} episodes" if count else "No episodes in this range"
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
                    preset_row_controls,
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
            ft.TextButton(content="Cancel", on_click=lambda e: controller.close_dialog()),
            ft.FilledButton(content="Download", on_click=lambda e: _send()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
