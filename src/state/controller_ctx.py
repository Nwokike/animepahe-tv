"""Bridge from screens to controller-owned actions.

House pattern (KTV/Sherlock): screens never touch services directly. They
call methods on this dataclass, which the AppShell fills in with closures
over the controller. Defaults are no-ops so a screen can render (and be
unit-tested) without a live controller.

Important: the AppShell MUTATES the same instance rather than replacing it —
copying breaks identity for screens that captured the context.
"""

from dataclasses import dataclass
from typing import Optional

import flet as ft


@dataclass
class ControllerMethods:
    # Navigation
    go_home: object = lambda: None
    open_search: object = lambda: None
    open_downloads: object = lambda: None
    open_settings: object = lambda: None
    open_anime: object = lambda session: None
    back: object = lambda: None

    # Data actions
    load_latest: object = lambda: None
    search: object = lambda query: None
    load_episodes: object = lambda session: None
    load_anime: object = lambda session: None
    play_episode: object = lambda anime_session, episode_session: None
    download_episode: object = lambda anime_session, episode_session: None
    retry_cloudflare: object = lambda: None
    check_updates: object = lambda: None
    load_search: object = lambda query, page=1: None
    clear_search_history: object = lambda: None

    # Long-running actions
    choose_quality: object = lambda index: None
    cancel_resolve: object = lambda: None

    # Favorites (whole anime)
    toggle_favorite: object = lambda row: None


ControllerMethodsCtx = ft.create_context(ControllerMethods())
