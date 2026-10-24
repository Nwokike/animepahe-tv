"""Bridge from screens to controller-owned actions.

House pattern (KTV/Sherlock): screens never touch services directly. They
call methods on this dataclass, which the AppShell fills in with closures
over the controller. Defaults are no-ops so a screen can render (and be
unit-tested) without a live controller.

Important: the AppShell MUTATES the same instance rather than replacing it —
copying breaks identity for screens that captured the context.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft


@dataclass
class ControllerMethods:
    # Navigation
    go_home: Callable[[], Any] = lambda: None
    open_search: Callable[[], Any] = lambda: None
    open_discover: Callable[[], Any] = lambda: None
    open_backend_picker: Callable[[], Any] = lambda: None
    pin_backend: Callable[[str], Any] = lambda name: None
    open_downloads: Callable[[], Any] = lambda: None
    open_settings: Callable[[], Any] = lambda: None
    open_anime: Callable[[str], Any] = lambda session: None
    open_schedule: Callable[[], Any] = lambda: None
    open_random: Callable[[], Any] = lambda: None
    back: Callable[[], Any] = lambda: None
    close_player: Callable[[], Any] = lambda: None
    play_adjacent: Callable[[int], Any] = lambda delta: None

    # Dialogs (the shell's single dialog portal)
    open_sheet: Callable[[Any], Any] = lambda dialog: None
    close_dialog: Callable[[], Any] = lambda: None

    # Data actions
    load_latest: Callable[..., Any] = lambda page_num=1: None
    load_episodes: Callable[..., Any] = lambda session, page_num=1: None
    load_anime: Callable[[str], Any] = lambda session: None
    load_discover_filters: Callable[[], Any] = lambda: None
    load_discover: Callable[..., Any] = lambda selections=None, page=1: None
    play_episode: Callable[[str, str], Any] = lambda anime_session, episode_session: None
    report_broken_stream: Callable[..., Any] = (
        lambda anime_session, episode_session, issues, note="": None
    )
    download_episode: Callable[[str, str], Any] = lambda anime_session, episode_session: None
    choose_download_quality: Callable[[int], Any] = lambda index: None
    download_series: Callable[..., Any] = lambda anime_session, episode_sessions, preset="highest": (
        None
    )
    pause_download: Callable[[str], Any] = lambda episode_session: None
    resume_download: Callable[[str], Any] = lambda episode_session: None
    retry_download: Callable[[str], Any] = lambda episode_session: None
    cancel_download: Callable[[str], Any] = lambda episode_session: None
    delete_download: Callable[[str], Any] = lambda episode_session: None
    play_downloaded: Callable[[str], Any] = lambda episode_session: None
    retry_cloudflare: Callable[[], Any] = lambda: None
    load_search: Callable[..., Any] = lambda query, page=1: None
    clear_search_history: Callable[[], Any] = lambda: None
    measure_cache: Callable[[], Any] = lambda: None
    clear_cache: Callable[[], Any] = lambda: None
    record_search_selection: Callable[[Any], Any] = lambda anime: None
    remove_search: Callable[..., Any] = lambda title, session="": None

    # Long-running actions
    choose_quality: Callable[[int], Any] = lambda index: None
    earn_kwik_qualities: Callable[[str, str], Any] = (
        lambda anime_session, episode_session: None
    )
    cancel_resolve: Callable[[], Any] = lambda: None

    # Favorites (whole anime)
    toggle_follow: Callable[[dict], Any] = lambda row: None

    # Backend management
    test_all_sources: Callable[[], Any] = lambda: None
    sources_status: Callable[[], dict] = dict
    set_backend_pin: Callable[[str], Any] = lambda name: None

    # AppController reference (attached by main.py)
    _app_controller: Any = None


ControllerMethodsCtx = ft.create_context(ControllerMethods())
