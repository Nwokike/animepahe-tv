"""animepahe-tv — entry point and application controller.

House architecture (KTV/Sherlock on flet 1.0.4): the controller owns the
services and exposes data actions; `AppShell` owns navigation state and
renders `@ft.component` screens through contexts. This module is the only
place services are constructed.
"""

import asyncio
import contextlib
import logging
import os

import flet as ft

from app_shell import AppShell
from core.constants import APP_NAME

# Logging first: the console + ring-buffer handlers attach at import time,
# so every service constructed below logs where it can be seen.
from core.logger_handler import in_memory_log_handler  # noqa: F401
from core.notify import show_snack
from core.storage import app_cache_dir
from core.tasks import session_alive, spawn, ui_set
from core.theme import AppColors, AppTheme, mode_for_token, token_for_mode
from services.animepahe import AnimePaheScraper
from services.cache import Cache
from services.kwik_resolver import KwikResolver
from services.update_service import UpdateService
from state.app_state import state
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

logger = logging.getLogger(__name__)

# UI updates per second for live download progress (segment callbacks fire
# far more often than a human can read).
_PROGRESS_FLUSH_SECONDS = 0.5


def _source_choices(sources) -> list[dict]:
    """Every site source as a choice dict, SUB (JPN) first then DUB (ENG),
    each best-first — the exact list the original build showed and the
    one both the play dialog and the download dialog render, so the two
    can never disagree about what a quality means."""
    ordered = sorted(
        sources,
        key=lambda s: (str(s.audio or "").lower().startswith("eng"), -s.resolution),
    )
    choices: list[dict] = []
    for src in ordered:
        audio_label = (
            "DUB (ENG)"
            if "eng" in (src.audio or "").lower()
            else f"SUB ({(src.audio or 'jpn').upper()})"
        )
        label = f"{src.resolution}p - {audio_label}"
        if src.fansub:
            label += f" ({src.fansub})"
        if getattr(src, "size", ""):
            label += f" [{src.size}]"
        choices.append(
            {
                "label": label,
                "kind": "source",
                "url": src.url,
                "headers": src.headers,
                "subtitles": src.subtitles,
                "skip": src.skip,
                "download_url": getattr(src, "download_url", "") or "",
                "direct": bool(getattr(src, "download_url", "")),
            }
        )
    return choices


def _preset_choice(choices: list[dict], preset: str) -> dict:
    """Which rendition a preset picks from an episode's choice list.

    The list is already best-first (SUB then DUB, resolution desc), so
    'highest' is its head and 'lowest' its tail. 'as-served' is the
    provider's own default — what sources[0] was before any preset."""
    if not choices:
        return {}
    if preset == "lowest":
        return choices[-1]
    return choices[0]


def _with_job_state(progress, episode_session: str, state: str) -> dict:
    """The manager's job state travels in the same dict the throttled
    flush already merges, so one flush carries state + bytes."""
    merged = dict(progress or {})
    row = dict(merged.get(episode_session) or {"done": 0, "total": 0, "bytes": 0})
    row["state"] = state
    merged[episode_session] = row
    return merged


def _anime_dict(anime) -> dict:
    """Anime dataclass -> the detail header's dict. Every field the
    providers fill is carried: dropping one here is what made synopsis,
    genres and the external ids invisible on the detail screen."""
    return {
        "title": anime.title,
        "poster": anime.poster,
        "episodes": anime.episodes,
        "year": anime.year,
        "type": anime.type,
        "status": anime.status,
        "score": anime.score,
        "season": anime.season,
        "synopsis": getattr(anime, "synopsis", "") or "",
        "genres": list(getattr(anime, "genres", None) or []),
        "mal_id": getattr(anime, "mal_id", 0) or 0,
        "anilist_id": getattr(anime, "anilist_id", 0) or 0,
        "studios": list(getattr(anime, "studios", None) or []),
        "aired": getattr(anime, "aired", "") or "",
        "backdrop": getattr(anime, "backdrop", "") or "",
    }


class AppController:
    """Owns services + data actions. Navigation lives in AppShell."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.scraper: AnimePaheScraper | None = None
        self.kwik: KwikResolver | None = None
        self.cache: Cache | None = None
        self.update_service: UpdateService | None = None
        self._loading_locks: dict[str, asyncio.Lock] = {}
        # The shell-owned ControllerMethods (set in main()); the global Back
        # handler routes through its navigation closures.
        self.shell: ControllerMethods | None = None
        self._latest_gen = 0
        self._episodes_gen = 0
        self._play_lock = asyncio.Lock()
        self._play_gen = 0
        # Download progress throttle state (see _on_download_progress).
        self._pending_progress: dict = {}
        self._progress_flush_task = None

    async def init(self):
        self.page.title = APP_NAME

        # assets_dir is already src/assets, so font files are addressed
        # relative to it ("outfit.css", not "assets/outfit.css" — the
        # latter asked the server for /assets/outfit.css and 404'd).
        self.page.fonts = {"Outfit": "outfit.css"}
        self.page.theme = AppTheme.get_light_theme()
        self.page.dark_theme = AppTheme.get_dark_theme()
        self.page.theme.font_family = "Outfit"
        self.page.dark_theme.font_family = "Outfit"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        state.theme_mode = ft.ThemeMode.SYSTEM
        self.cache = Cache()
        # The process-wide singleton: the ddos solver and the player use
        # get_store(), and a second instance here would clobber their
        # sections on flush (each keeps its own dirty set).
        from services.store import get_store

        self.store = get_store()
        self.scraper = AnimePaheScraper()
        # The data layer: the ROUTER. Every provider is a complete app in
        # its own way; the auto order runs the OPEN sources first and
        # keeps AnimePahe (whose catalog is Cloudflare-walled) as the
        # safety net — its breaker trips on walled calls while its files
        # still get attempted. Per-request failover, never locked.
        from services.providers.base import DEFAULT_OWNER, owner_of
        from services.providers.anikato import AniKatoProvider
        from services.providers.animeout import AnimeOutProvider
        from services.animeout_solver import AnimeOutSolver
        from services.providers.animepahe_provider import AnimePaheProvider
        from services.providers.kayoanime import KayoanimeProvider
        from services.providers.kusonime import KusonimeProvider
        from services.router import ProviderRouter

        self.router = ProviderRouter(
            [
                AniKatoProvider(),
                AnimeOutProvider(
                    solver=AnimeOutSolver(store=self.store),
                ),
                KusonimeProvider(),
                KayoanimeProvider(),
                AnimePaheProvider(self.scraper),
            ]
        )
        self._owner_of = owner_of
        self._default_owner = DEFAULT_OWNER
        # Restore the user's content-source preference (auto or pinned).
        self.router.set_pin(await self.store.get_backend())
        self.kwik = KwikResolver(ddos_solver=self.scraper.ddos)
        self.update_service = UpdateService()
        self._search_gen = 0
        self._resolved_m3u8: str | None = None
        # Startup resolution is single-flight (boot + every manual switch).
        self._startup_lock = asyncio.Lock()
        # The shell publishes what Back should do (dialog open? which view?
        # is the player up?) on every render; _handle_global_back reads it.
        self.ui_state = {"dialog_open": False, "view": "tabs"}
        from core.focus_manager import FocusManager

        self.focus_manager = FocusManager(self.page)
        self.focus_manager.set_back_handler(self._handle_global_back)
        self._mount_connectivity()
        # One launcher + one clipboard for the whole app (call sites used to
        # construct their own per tap).
        from core.shared_services import mount_shared_services

        self.shared = mount_shared_services(self.page)
        # The loopback HLS proxy is what makes playback work: the stream
        # hosts fingerprint TLS and reject the video backends' client, so a
        # raw m3u8 fails to open. The proxy fetches with Chrome
        # impersonation + the right headers and rewrites the playlist, which
        # is also what makes quality/audio switching possible.
        from services.hls_proxy import HLSProxy

        self.hls_proxy = HLSProxy()
        try:
            await self.hls_proxy.start()
        except Exception as ex:
            logger.error("HLS proxy failed to start: %s — playing direct", ex)
            self.hls_proxy = None
        from services.downloads import DownloadManager

        self.downloads = DownloadManager(store=self.store)
        self.downloads.on_progress = self._on_download_progress
        self.downloads.on_finished = self._on_download_finished

        await self.cache.start_sweep(interval=300)

        state.scraper = self.scraper
        state.cache = self.cache
        state.page = self.page
        state.search_history = await self.store.get_search_history()
        state.continue_watching = await self.store.get_continue_watching()
        state.downloads = await self.store.get_downloads()
        state.follows = await self.store.get_follows()

        # Restore the theme choice before the first render so the shell
        # never flashes the wrong mode.
        await self._restore_theme_mode()

        # Follows -> new-episode alerts. The channel, the permission ask
        # and the tap deep-link all live behind the adapter (no-ops off
        # platform), so this is safe on desktop where the extension is
        # absent.
        await self._setup_notifications()

        # Resolve the session's backend ONCE, then the first home fetch —
        # all behind the shell's startup splash (Phase 2). Replaces the old
        # fire-and-forget health probe: probe_all still runs inside, and its
        # records still warm the health panel.
        spawn(self.resolve_startup(), name="startup-resolve")

        spawn(self._check_for_updates_bg(), name="update-check")
        await self.start_episode_checker()

    async def _setup_notifications(self) -> None:
        """Channel + permission + tap routing, once at startup — SPAWNED,
        never awaited: on a platform without the native listener (web) the
        package's invoke waits its full timeout before failing, and
        blocking startup on that would delay first paint by seconds."""
        from core import notifications
        from core.tasks import spawn

        def _on_tap(payload: str):
            session = notifications.handle_payload(payload)
            if session:
                logger.info("notification deep-link: %s", session)
                self._open_from_notification(session)

        async def _setup():
            notifications.on_tap(_on_tap)
            if not await notifications.request_permissions():
                logger.info("notifications unavailable on this platform")
                return
            await notifications.ensure_channel()

        spawn(_setup(), name="notification-setup")

    def _open_from_notification(self, anime_session: str) -> None:
        """A tapped new-episode alert opens that anime's detail."""
        from core.tasks import spawn

        spawn(self.load_anime(anime_session), name="notif-open-anime")

    async def _restore_theme_mode(self):
        try:
            saved = await self.store.get_theme_mode()
        except Exception as ex:
            logger.warning("theme restore failed: %s", ex)
            return
        if saved:
            mode = mode_for_token(saved)
            self.page.theme_mode = mode
            state.theme_mode = mode

    async def save_theme_mode(self, mode: ft.ThemeMode):
        state.theme_mode = mode
        try:
            await self.store.save_theme_mode(token_for_mode(mode))
        except Exception as ex:
            logger.warning("theme save failed: %s", ex)

    async def _check_for_updates_bg(self):
        await asyncio.sleep(2.0)
        update_data = await self.update_service.check_for_update()
        if update_data:
            state.update_available = True
            state.update_data = update_data

    # ------------------------------------------------------------------
    # Connectivity (native listener — no probe polling)
    # ------------------------------------------------------------------

    def _mount_connectivity(self):
        """Track online state so an offline user is told they're offline,
        not told to verify they're human (the old CF gate conflated the
        two: a dead network set cf_blocked)."""
        from flet import ConnectivityType

        connectivity = ft.Connectivity()
        connectivity.on_change = self._on_connectivity_change
        self.page.services.append(connectivity)

        async def _init():
            try:
                result = await connectivity.get_connectivity()
                state.is_online = ConnectivityType.NONE not in result
                logger.info("connectivity initial: online=%s", state.is_online)
            except Exception as ex:
                logger.debug("connectivity init failed: %s", ex)

        spawn(_init(), name="connectivity-init")

    def _on_connectivity_change(self, e):
        from flet import ConnectivityType

        was_online = state.is_online
        state.is_online = ConnectivityType.NONE not in e.connectivity
        if was_online and not state.is_online:
            logger.warning("Connectivity lost")
            state.connectivity_version += 1
            self._show_error_snackbar("You're offline. Check your connection.")
        elif not was_online and state.is_online:
            logger.info("Connectivity restored")
            state.connectivity_version += 1
            # The user needs the good news too — losing connectivity warns,
            # and regaining it silently leaves them guessing.
            show_snack(self.page, "Back online", bgcolor=AppColors.SUCCESS)
            # A network blip must not leave the CF gate latched on: probe
            # the feed again now that we're back.
            if state.cf_blocked:
                spawn(self.retry_cloudflare(), name="cf-retry-on-reconnect")

    def _show_error_snackbar(self, message: str = "Network error"):
        """Surface a failure to the user (guarded: never raises, never kills
        a real dialog). All failure paths funnel through here."""
        show_snack(self.page, message, bgcolor=AppColors.ERROR)

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._loading_locks:
            self._loading_locks[key] = asyncio.Lock()
        return self._loading_locks[key]

    def _handle_global_back(self):
        """Back/Escape precedence, translated from the original 1.0.9 app
        (which had `page.views` to pop): open dialog → player (the player's
        own FocusScope owns Back while it's open, so it can save the resume
        position first) → detail view → tabs root → let the OS background
        the app.
        """
        from core.dialogs import close_app_dialog

        # Ad-hoc dialogs (update prompt, KTV install prompt) first — the
        # original closed whatever dialog was open before navigating.
        if close_app_dialog(self.page):
            return
        ui = self.ui_state
        if ui.get("dialog_open"):
            self._shell_action("close_dialog")
            return
        if state.player_open:
            # The player's FocusScope handles Back and saves the position
            # before the shell tears the player down — do nothing here.
            return
        if ui.get("view") == "anime":
            self._shell_action("back")
            return
        # Root: the OS finishes/backgrounds the app, as on the original.

    def _shell_action(self, name: str, *args):
        """Call a navigation closure on the shell-owned methods instance.

        The shell fills these in on every render (and they're no-ops until
        its first render), so the controller never holds a stale closure.
        """
        action = getattr(self.shell, name, None)
        if action is not None:
            action(*args)

    # ------------------------------------------------------------------
    # Data actions — called by screens through ControllerMethods
    # ------------------------------------------------------------------

    async def load_latest(self, page_num: int = 1):
        lock = self._get_lock(f"latest_{page_num}")
        if lock.locked():
            return

        # Generation counter: a slow response for an older page must never
        # overwrite a newer one's results (load_search's pattern).
        self._latest_gen += 1
        gen = self._latest_gen

        async with lock:
            state.is_loading = True
            state.latest_page = page_num
            state.latest_version += 1

            try:
                results, has_more = await self.router.latest_releases(page_num)
                if gen != self._latest_gen:
                    logger.info("load_latest discarding stale page=%d", page_num)
                    return
                if not session_alive():
                    # Hot reload / app close tore the session down while this
                    # load ran; the writes below would crash inside
                    # Observable notify ("destroyed session", observed live).
                    logger.info("load_latest page=%d dropped (session gone)", page_num)
                    return
                logger.info(
                    "load_latest page=%d got %d items, has_more=%s",
                    page_num,
                    len(results),
                    has_more,
                )
                state.latest_releases = results
                state.latest_has_more = has_more
                state.latest_source = self.router.last_winner or ""
                if page_num == 1 and results:
                    state.cf_blocked = False
            except Exception as ex:
                if gen != self._latest_gen or not session_alive():
                    return
                logger.error("load_latest page=%d failed: %s", page_num, ex)
                state.latest_releases = []
                state.latest_has_more = False
                if page_num == 1:
                    self._show_error_snackbar("Couldn't load the latest releases.")
            finally:
                if gen == self._latest_gen:
                    ui_set(state, "is_loading", False)
                    if session_alive():
                        # Only a confirmed-online empty feed is a Cloudflare gate.
                        # An offline user used to get the SHIELD card here and told
                        # to verify they're human — a network blip is not a challenge.
                        if page_num == 1 and not state.latest_releases and state.is_online:
                            state.cf_blocked = True
                        state.latest_version += 1

    async def retry_cloudflare(self):
        """Clear the Cloudflare session + caches, then reload the home feed."""
        state.cf_blocked = False
        state.latest_version += 1
        # The Verify button spins for the whole re-challenge: it can take
        # several seconds on a cold WebView solve.
        state.cf_retrying = True
        state.busy_version += 1
        try:
            await self.scraper.ddos.reset()
            self.scraper.clear_cache()
            await self.cache.clear()
        except Exception as ex:
            logger.error("retry_cloudflare failed: %s", ex)
            self._show_error_snackbar("Couldn't refresh the session.")
        finally:
            state.cf_retrying = False
            state.busy_version += 1
        await self.load_latest(1)

    async def load_episodes(self, anime_session: str, page_num: int = 1):
        lock = self._get_lock(f"episodes_{anime_session}")
        if lock.locked():
            return

        # Generation counter per session: switching anime mid-flight must
        # not let the older detail screen's response land last.
        self._episodes_gen += 1
        gen = self._episodes_gen

        async with lock:
            if state.current_anime_session != anime_session:
                # Defense in depth for direct callers: a session switch
                # never leaves the previous anime's rows clickable under
                # the new session (see load_anime for the full story).
                state.episodes = []
                state.episodes_has_more = True
            state.is_loading = True
            state.current_anime_session = anime_session
            state.episodes_page = page_num
            state.episodes_version += 1

            try:
                episodes, has_more = await self.router.episodes(anime_session, page_num)
                state.current_source_name = self.router.last_winner or ""
                if gen != self._episodes_gen:
                    logger.info(
                        "load_episodes discarding stale page for %s", anime_session
                    )
                    return
                if not session_alive():
                    logger.info(
                        "load_episodes session=%s dropped (session gone)", anime_session
                    )
                    return
                logger.info(
                    "load_episodes session=%s page=%d got %d",
                    anime_session,
                    page_num,
                    len(episodes),
                )
                state.episodes = episodes
                state.episodes_has_more = has_more
                state.cf_blocked = False
            except Exception as ex:
                if gen != self._episodes_gen or not session_alive():
                    return
                logger.error("load_episodes session=%s failed: %s", anime_session, ex)
                state.episodes = []
                state.episodes_has_more = False
                self._show_error_snackbar("Couldn't load the episode list.")
            finally:
                if gen == self._episodes_gen:
                    ui_set(state, "is_loading", False)
                    if session_alive():
                        state.episodes_version += 1

        # The header poster from a latest-release card is an episode still
        # (/snapshots/). The original build self-healed it with a title
        # search; keep that so detail opened from Home doesn't sit on a still.
        if gen == self._episodes_gen:
            await self._heal_anime_poster(anime_session, gen)

    async def _heal_anime_poster(self, anime_session: str, gen: int):
        """Replace a /snapshots/ placeholder poster with the real poster."""
        anime = state.selected_anime or {}
        poster = anime.get("poster") or ""
        if "/snapshots/" not in poster:
            return
        try:
            # Owner-scoped: the heal is this backend's own errand, never a
            # reason to query another one.
            results, _ = await self.router.search(
                anime.get("title") or "", 1, owner=self._owner_of(anime_session)
            )
        except Exception as ex:
            logger.debug("poster heal search failed: %s", ex)
            return
        if gen != self._episodes_gen:
            return
        matched = next(
            (a for a in results if a.session == anime_session and a.poster), None
        )
        if matched is None or "/snapshots/" in (matched.poster or ""):
            return
        merged = dict(state.selected_anime or {})
        merged["poster"] = matched.poster
        state.selected_anime = merged
        state.episodes_version += 1
        logger.info("poster healed for %s", anime_session)

    def _ddos(self):
        """The Cloudflare solver, when this build has one."""
        return getattr(self.scraper, "ddos", None) if self.scraper else None

    def _may_solve(self, anime_session: str | None) -> bool:
        """A verification window opens only for a deliberate action on
        animepahe's own content — the provider is last precisely because
        its catalog is Cloudflare-walled. Background work (probes, the
        episode checker) must never trigger one."""
        solver = self._ddos()
        if solver is None:
            return False
        if anime_session and self._owner_of(anime_session) != self._default_owner:
            return False
        return True

    async def play_episode(self, anime_session: str, episode_session: str):
        # Resolve the stream, then open the in-app player. The ktv:// deep
        # link stays as the fallback for when resolution fails.
        # The lock dedupes a double-tap on the same episode (otherwise two
        # resolutions race and the second quality dialog wins).
        if self._play_lock.locked():
            logger.info("play_episode already resolving, ignoring tap")
            return
        async with self._play_lock:
            solver = self._ddos()
            if self._may_solve(anime_session) and solver is not None:
                solver.solve_allowed = True
            try:
                await self._play_episode(anime_session, episode_session)
            finally:
                if solver is not None:
                    solver.solve_allowed = False

    async def _play_episode(self, anime_session: str, episode_session: str):
        state.current_anime_session = anime_session
        state.current_episode_session = episode_session
        state.episodes_version += 1

        # Resolution takes seconds (play-page fetch + kwik unpack + the m3u8
        # variants). Show the "Resolving stream…" stage the whole way, and
        # honour a Cancel from the overlay via the play generation.
        gen = self._begin_resolve("Finding sources…")
        try:
            await self._play_episode_resolve(anime_session, episode_session, gen)
        finally:
            if gen == self._play_gen:
                self._end_resolve()

    def _begin_resolve(self, stage: str) -> int:
        self._play_gen += 1
        state.is_resolving = True
        state.resolve_stage = stage
        state.busy_version += 1
        return self._play_gen

    def _resolve_stage(self, gen: int, stage: str) -> None:
        if gen == self._play_gen:
            state.resolve_stage = stage
            state.busy_version += 1

    def _end_resolve(self) -> None:
        state.is_resolving = False
        state.resolve_stage = ""
        state.busy_version += 1

    def cancel_resolve(self) -> None:
        """Cancel from the resolving overlay: bump the generation so the
        in-flight resolution discards its result."""
        self._play_gen += 1
        self._end_resolve()

    async def _play_episode_resolve(
        self, anime_session: str, episode_session: str, gen: int
    ):
        anime = await self._resolve_anime(anime_session)
        if gen != self._play_gen:
            return
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        if anime and ep:
            record = {
                "anime_session": anime_session,
                "anime_id": ep.anime_id,
                "title": anime.get("title", ""),
                "poster": anime.get("poster", ""),
                "episode_num": ep.episode,
                "episode_session": episode_session,
                "total_episodes": anime.get("episodes", 0),
            }
            await self.store.record_watch(record)
            state.continue_watching = await self.store.get_continue_watching()
            state.continue_version += 1

        # Interstitial between episodes (the full-map cadence).
        try:
            from services.ads import show_interstitial

            await show_interstitial(self.page)
        except Exception as ex:
            logger.warning("interstitial skip: %s", ex)
        if gen != self._play_gen:
            return

        # External-player mode: the 1.0.9 flow, reproduced. The old app was
        # external-only — it resolved the chosen source and handed KTV the
        # m3u8 via ktv:// (with the install dialog on failure). The proxy is
        # irrelevant here, so nothing is built for it.
        if await self.store.get_external_player():
            if gen != self._play_gen:
                return
            await self._play_episode_external(anime_session, episode_session)
            return

        # 1. Stream sources — sorted best-first, as the original did.
        try:
            sources = await self.router.sources(anime_session, episode_session)
        except Exception as ex:
            logger.error(
                "sources(%s/%s) failed: %s", anime_session, episode_session, ex
            )
            self._show_error_snackbar("Couldn't load the stream sources.")
            sources = []
        if gen != self._play_gen:
            return
        serving_provider = None
        if not sources:
            # A backend with no stream for this episode is a RESULT, not a
            # handoff. The old automatic title-hop asked every other
            # backend right here — it produced the bogus ktv:// launch and
            # the CF-churn cascade (live log 2026-10-15). Cross-backend
            # play is the owner's explicit act now: the detail screen's
            # "Try another source" re-enters on that backend properly.
            logger.info(
                "no sources on %s for %s",
                self._owner_of(anime_session),
                episode_session,
            )
            self._show_error_snackbar(
                "This source has no playable stream for this episode."
            )
            return
        # SUB (JPN) group first, DUB (ENG) after — each best-first.
        # Dubs exist as separate renditions; today they render mixed.
        sources = sorted(
            sources,
            key=lambda s: (str(s.audio or "").lower().startswith("eng"), -s.resolution),
        )
        state.selected_source = sources[0]

        # 2. Resolve the best source -> m3u8 -> variants. Providers with
        # the kwik_resolve capability (AnimePahe) need the Kwik unpack;
        # every other provider's URLs are already playable.
        self._resolve_stage(gen, "Resolving stream…")
        m3u8 = await self._resolve_source(
            sources[0].url, anime_session, provider_name=serving_provider
        )
        if gen != self._play_gen:
            return
        if not m3u8:
            logger.warning("kwik resolve failed — external player fallback")
            await self._open_external_player(anime_session, episode_session)
            return
        self._resolved_m3u8 = m3u8
        self._resolve_stage(gen, "Loading qualities…")
        variants = await self._fetch_variants(m3u8, sources[0].headers)
        if gen != self._play_gen:
            return

        # 3. Quality choices: EVERY site source, best-first — exactly what
        #    the original listed ("1080p - SUB (JPN) (SubsProvide)"). The
        #    m3u8 variants of the chosen source are the in-player quality
        #    options instead (house-player parity), so they don't belong in
        #    this list.
        choices = _source_choices(sources)

        if len(choices) <= 1:
            await self._open_player(
                m3u8,
                variants,
                anime_session,
                episode_session,
                sources[0].headers,
                sources[0].subtitles,
                sources[0].skip,
            )
            return
        state.quality_choices = choices
        state.quality_dialog_open = True
        state.pending_playback = {
            "m3u8": m3u8,
            "variants": variants,
            "anime_session": anime_session,
            "episode_session": episode_session,
            "headers": sources[0].headers,
            "subtitles": sources[0].subtitles,
            "skip": sources[0].skip,
            # Which provider actually SERVED these sources — the re-resolve
            # in choose_quality must use the same capability gate (an
            # owner-derived one would unpack a direct m3u8 through kwik,
            # or hand the player a kwik page URL raw).
            "provider": serving_provider,
        }
        state.episodes_version += 1

    async def _resolve_source(
        self, url: str, anime_session: str, provider_name: str | None = None
    ) -> str | None:
        """Source URL -> playable URL, per the serving provider's
        capabilities. kwik_resolve providers (AnimePahe) unpack through
        Kwik; others are already playable (anikato m3u8s, kusonime
        files). None means resolution failed.

        `provider_name` overrides the owner-derived provider — the title
        failover serves sources from a DIFFERENT provider than the one
        the anime_session names, and the capability gate must follow the
        source, not the session."""
        name = provider_name or self._owner_of(anime_session)
        provider = self.router.get(name)
        if provider is not None and provider.capabilities.get("kwik_resolve"):
            try:
                return await self.kwik.resolve(url)
            except Exception as ex:
                logger.error("kwik resolve(%s) failed: %s", url, ex)
                return None
        return url or None

    async def _fetch_variants(
        self, m3u8: str, headers: dict | None = None
    ) -> list[dict]:
        """Master-playlist variants through the proxy (correct headers),
        falling back to a direct fetch when the proxy isn't running.

        Only HLS playlists are probed. A DIRECT file source (kayoanime's
        Drive MKV, a pixeldrain batch) has no variants, and fetching it
        here read the ENTIRE video body as text — the flet run log showed
        a play-episode task dying on primp.TimeoutError for a Drive file,
        with the player never opening.
        """
        if ".m3u8" not in (m3u8 or "").split("?")[0].lower():
            return []
        from components.player.immersive_player import KWIK_USER_AGENT

        headers = headers or {
            "User-Agent": KWIK_USER_AGENT,
            "Referer": "https://kwik.cx/",
        }
        if self.hls_proxy is not None:
            return await self.hls_proxy.fetch_variants(m3u8, headers=headers)
        from components.player.immersive_player import (
            KWIK_USER_AGENT,
            _stream_variants,
        )

        try:
            client = self.kwik._get_client()
            resp = await client.get(m3u8, headers=headers)
            if resp.status_code == 200 and resp.text:
                # The master's own URL resolves the relative variants.
                return _stream_variants(resp.text, m3u8)
        except Exception as ex:
            logger.warning("variant fetch failed: %s", ex)
        return []

    async def choose_quality(self, choice_index: int):
        """Open the pending playback with the chosen quality."""
        pending = state.pending_playback
        if not pending:
            return
        state.quality_dialog_open = False
        choices = state.quality_choices or []
        if choice_index < 0 or choice_index >= len(choices):
            await self._open_player(
                pending["m3u8"],
                pending.get("variants") or [],
                pending["anime_session"],
                pending["episode_session"],
                pending.get("headers"),
                pending.get("subtitles"),
                pending.get("skip"),
            )
            return
        pending_external = bool(pending.get("external"))
        choice = choices[choice_index]
        if pending_external:
            # The old-app path: resolve the chosen source and hand it to KTV.
            source = next(
                (
                    s
                    for s in getattr(self, "_external_sources", [])
                    if s.url == choice["url"]
                ),
                None,
            )
            if source is None:
                # Rebuild the Source from the choice (the list isn't kept).
                from core.state import Source

                source = Source(url=choice["url"], resolution=0, audio="jpn", fansub="")
            await self._resolve_and_launch_external(
                source, pending["anime_session"], pending["episode_session"]
            )
            return
        # Every entry is a site source (kwik url): re-resolve it, fetch its
        # own variants, and play. The dialog buttons spin while it happens
        # (see _build_quality_dialog).
        state.quality_resolving = True
        state.busy_version += 1
        from core.state import Source as _Source

        choice_source = _Source(
            url=choice["url"],
            resolution=0,
            audio="",
            fansub="",
            headers=choice.get("headers") or {},
        )
        try:
            m3u8 = await self._resolve_source(
                choice_source.url,
                pending["anime_session"],
                provider_name=pending.get("provider"),
            )
            variants = (
                await self._fetch_variants(m3u8, choice.get("headers")) if m3u8 else []
            )
        except Exception as ex:
            logger.error("quality choice resolve failed: %s", ex)
            self._show_error_snackbar("Couldn't switch to that quality.")
            m3u8 = None
            variants = []
        finally:
            state.quality_resolving = False
            state.busy_version += 1
        await self._open_player(
            m3u8 or pending["m3u8"],
            variants,
            pending["anime_session"],
            pending["episode_session"],
            choice.get("headers"),
            choice.get("subtitles"),
            choice.get("skip"),
        )

    async def _open_player(
        self,
        resource: str,
        variants: list[dict],
        anime_session: str,
        episode_session: str,
        source_headers: dict | None = None,
        subtitles: list | None = None,
        skip: dict | None = None,
    ):
        """Open the in-app player on a resolved stream.

        HLS resources route through the loopback proxy (the hosts
        fingerprint TLS and reject the video backends' client — a raw
        m3u8 fails with "Failed to open"); direct files (kusonime's
        .mkv) play as-is. ``source_*`` carries the CHOSEN SOURCE's own
        headers (anikato's m3u8s need Referer megaplay.buzz; animepahe's
        need the kwik pair) so the player and the proxy rebuilds send
        exactly what the CDN requires.
        """
        from components.player.immersive_player import KWIK_USER_AGENT

        anime = await self._resolve_anime(anime_session)
        # Clear any previous open-failure so it can't blink over the new one.
        state.player_error = None
        headers = (
            dict(source_headers)
            if source_headers
            else {
                "User-Agent": KWIK_USER_AGENT,
                "Referer": "https://kwik.cx/",
            }
        )
        referer = headers.get("Referer", "https://kwik.cx/")
        play_url = resource
        # Only HLS routes through the proxy; progressive files (a .mkv
        # from kusonime) play directly with their own headers.
        if self.hls_proxy is not None and ".m3u8" in resource:
            try:
                play_url = self.hls_proxy.get_proxy_url(
                    resource,
                    referer=referer,
                    headers=headers,
                )
            except Exception as ex:
                logger.warning("proxy url build failed; playing direct: %s", ex)
        # Subtitle URLs come from a host that requires the source's own
        # Referer — route them through the loopback proxy exactly like
        # segments (its passthrough serves the VTT bytes with the right
        # headers). Tracks travel exactly as the source served them.
        spec_subtitles = list(subtitles or [])
        if spec_subtitles and self.hls_proxy is not None:
            proxied_tracks = []
            for track in spec_subtitles:
                try:
                    proxied_tracks.append(
                        {
                            "label": track.get("label") or "",
                            "url": self.hls_proxy.get_proxy_url(
                                track["url"], referer=referer, headers=headers
                            ),
                            "default": bool(track.get("default")),
                        }
                    )
                except Exception as ex:
                    logger.warning("subtitle proxy build failed: %s", ex)
            if proxied_tracks:
                spec_subtitles = proxied_tracks
        state.player_spec = {
            "resource": play_url,
            "source_url": resource,
            "source_referer": referer,
            "source_headers": headers,
            "variants": variants,
            "subtitles": spec_subtitles,
            "skip": skip or {},
            "proxied": self.hls_proxy is not None,
            "title": (anime or {}).get("title") or "AnimePahe",
            "episode_session": episode_session,
            "anime_session": anime_session,
        }
        state.player_open = True
        state.episodes_version += 1
        logger.info(
            "player opening for %s/%s via %s",
            anime_session,
            episode_session,
            "proxy" if self.hls_proxy is not None else "direct",
        )

    async def test_all_sources(self):
        """Dev panel: probe every provider, then hit it with a real
        search. Nothing is faked — the rows are what each source
        actually answered, and nothing is filtered."""
        import time as _time

        rows: list[dict] = []
        for provider in self.router._providers:
            row = {
                "name": provider.name,
                "probe_ok": False,
                "probe_ms": None,
                "search_count": None,
                "search_ms": None,
                "error": "",
            }
            started = _time.monotonic()
            try:
                row["probe_ok"] = bool(await provider.probe())
                row["probe_ms"] = round((_time.monotonic() - started) * 1000)
            except Exception as ex:
                row["error"] = f"probe: {ex}"[:120]
            if row["probe_ok"]:
                started = _time.monotonic()
                try:
                    results, _ = await provider.search("one piece", 1)
                    row["search_count"] = len(results)
                    row["search_ms"] = round((_time.monotonic() - started) * 1000)
                except Exception as ex:
                    row["error"] = f"search: {ex}"[:120]
            rows.append(row)
        state.source_test_results = rows
        state.sources_test_version += 1
        logger.info(
            "source test: %s",
            [(r["name"], r["probe_ok"], r["search_count"]) for r in rows],
        )

    async def report_broken_stream(
        self, anime_session: str, episode_session: str, issues: list[str], note: str = ""
    ) -> tuple[bool, str]:
        """File one broken-stream report with the owning provider. Only
        providers that expose the site's own report form answer; every
        other one is a no-op with an honest message, never a crash."""
        provider = self.router.get(self._owner_of(anime_session or ""))
        if provider is None or not hasattr(provider, "report_broken"):
            return (False, "This source has no report form.")
        server = ""
        src = state.selected_source
        if src is not None and getattr(src, "fansub", ""):
            server = str(src.fansub)
        try:
            return await provider.report_broken(
                anime_session, episode_session, issues, note, server_name=server
            )
        except Exception as ex:
            logger.warning("report failed: %s", ex)
            return (False, "The report could not be sent.")

    # ------------------------------------------------------------------
    # Discover (provider-generated filters)
    # ------------------------------------------------------------------

    async def load_discover_filters(self):
        """Ask the serving provider for its own filter vocabulary. The
        list is generated from what the source offers — nothing about
        genres or categories is hardcoded in the UI."""
        name, spec = await self.router.discover_filters()
        state.discover_source = name
        state.discover_filters = spec
        state.discover_selections = {}
        state.discover_results = []
        state.discover_has_more = False
        state.discover_version += 1
        if not spec:
            logger.info("discover: no provider offers a browse surface")

    async def load_discover(self, selections: dict | None = None, page: int = 1):
        """Run the filtered browse. An empty result is a RESULT (nothing
        matched), not an error."""
        if selections is not None:
            state.discover_selections = dict(selections)
        state.discover_page = page
        name, items, has_more = await self.router.browse(
            state.discover_source or None,
            state.discover_selections,
            page,
        )
        state.discover_source = name or state.discover_source
        state.discover_results = items
        state.discover_has_more = has_more
        state.discover_version += 1

    async def load_schedule(self, time: str | None = None):
        """Airing schedule: 7 day tabs, then the selected day's entries.
        Only providers that expose a schedule answer (anikato); the router
        is not involved — this is a source-specific extra."""
        provider = self.router.get("anikato")
        if provider is None:
            self._show_error_snackbar("No source offers a schedule yet.")
            return
        try:
            tabs = await provider.schedule_tabs()
            state.schedule_tabs = tabs
            if time is None and tabs:
                time = tabs[0]["time"]
            state.schedule_time = time or ""
            state.schedule_entries = (
                await provider.schedule_entries(time) if time else []
            )
        except Exception as ex:
            logger.warning("schedule load failed: %s", ex)
            state.schedule_tabs = []
            state.schedule_entries = []
        state.schedule_version += 1

    async def open_schedule(self):
        """Home header: the airing-calendar dialog."""
        await self.load_schedule()
        from core.dialogs import show_app_dialog
        from core.theme import AppColors

        def _pick_day(e, t: str):
            from core.tasks import spawn

            spawn(self.load_schedule(t), name="load-schedule")

        def _open_entry(slug: str):
            from core.tasks import spawn

            _close_schedule()
            spawn(self.load_anime(f"anikato:{slug}"), name="open-schedule-anime")

        def _close_schedule():
            try:
                setattr(self.page, "_app_dialog", None)
                self.page.pop_dialog()
            except Exception:
                pass

        day_chips = ft.Row(
            [
                ft.OutlinedButton(
                    content=f"{t.get('weekday', '')} {t.get('date', '')}",
                    on_click=lambda e, t=t["time"]: _pick_day(e, t),
                    style=ft.ButtonStyle(
                        side={
                            ft.ControlState.DEFAULT: ft.BorderSide(
                                1.5,
                                AppColors.PRIMARY
                                if t["time"] == state.schedule_time
                                else ft.Colors.with_opacity(0.3, AppColors.PRIMARY),
                            )
                        }
                    ),
                )
                for t in state.schedule_tabs
            ],
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
            wrap=False,
        )
        entry_rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            entry.get("time", ""),
                            size=13,
                            weight=ft.FontWeight.W_700,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Container(width=10),
                        ft.Text(
                            entry.get("title", ""),
                            size=13,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"Ep {entry.get('episode', '')} · {entry.get('type', '')}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=8,
                ink=True,
                on_click=lambda e, s=entry.get("slug", ""): _open_entry(s),
            )
            for entry in state.schedule_entries
        ] or [
            ft.Text("No airings this day.", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        ]

        show_app_dialog(
            self.page,
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Airing Schedule", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    [
                        day_chips,
                        ft.Container(height=10),
                        ft.Column(
                            entry_rows,
                            tight=True,
                            spacing=2,
                            scroll=ft.ScrollMode.AUTO,
                            height=380,
                        ),
                    ],
                    tight=True,
                    spacing=8,
                ),
                actions=[
                    ft.TextButton(content="Close", on_click=lambda e: _close_schedule())
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            ),
        )

    async def open_random(self):
        """Home header: surprise-me — a random anime's detail page."""
        provider = self.router.get("anikato")
        if provider is None:
            self._show_error_snackbar("No source offers surprise-me yet.")
            return
        try:
            slug = await provider.random_slug()
        except Exception as ex:
            logger.warning("random failed: %s", ex)
            slug = None
        if slug:
            await self.load_anime(f"anikato:{slug}")

    def sources_status(self) -> dict:
        """Settings: per-provider live health as plain dicts."""
        return {
            name: {
                "state": rec.state,
                "latency_ms": rec.latency_ms,
                "last_error": rec.last_error,
                "checked_at": rec.checked_at,
            }
            for name, rec in self.router.health().items()
        }

    async def try_another_source(self, anime_session: str):
        """Detail: the owner missed — ask every OTHER provider BY TITLE
        (user-initiated), then RE-ENTER on the match's own session so the
        app truly becomes that backend's app: its episodes, its sources,
        its art. Never splices another backend's episodes under the old
        session — that pairing used to leak into playback and downloads."""
        anime = state.selected_anime or {}
        title = str(anime.get("title") or "").strip()
        if not title:
            self._show_error_snackbar("Nothing to look up — no title.")
            return
        state.is_loading = True
        state.episodes_version += 1
        try:
            episodes, _ = await self.router.episodes_for_title_any(
                title, skip=self._owner_of(anime_session)
            )
        except Exception as ex:
            logger.warning("try_another_source failed: %s", ex)
            episodes = []
        finally:
            state.is_loading = False
            state.episodes_version += 1
        if not episodes:
            self._show_error_snackbar("No other source has this title.")
            return
        # The host that answered; find its OWN anime session for the title
        # and open that — a real re-entry, not a splice.
        name = self.router.last_winner or ""
        provider = self.router.get(name) if name else None
        match = None
        if provider is not None:
            try:
                results, _ = await provider.search(title, 1)
            except Exception as ex:
                logger.warning("try_another_source search on %s failed: %s", name, ex)
                results = []
            match = next(
                (
                    a
                    for a in results
                    if a.session and a.title.lower() == title.lower()
                ),
                next((a for a in results if a.session), None),
            )
        if match is None:
            self._show_error_snackbar("No other source has this title.")
            return
        logger.info("try_another_source: re-entering on %s (%s)", name, match.session)
        self._shell_action("open_anime", match.session)

    async def check_new_episodes(self, *, force: bool = False) -> int:
        """Diff every follow's stored episode count against the router's
        current one and alert on new episodes. Returns the alerts fired.

        force=True re-checks even when a check ran recently (the user
        tapped Retry / the Sources panel)."""

        follows = await self.store.get_follows()
        if not follows:
            return 0
        from core import notifications

        fired = 0
        for anime_session, row in follows.items():
            if not anime_session:
                continue
            last_seen = await self.store.get_follow_progress(anime_session)
            try:
                episodes, _ = await self.router.episodes(anime_session, 1)
            except Exception as ex:
                logger.debug("new-episode check failed for %s: %s", anime_session, ex)
                continue
            if not episodes:
                continue
            newest = max((e.episode for e in episodes), default=0)
            if newest <= last_seen:
                continue
            title = str(row.get("title") or "Anime")
            poster = str(row.get("poster") or "")
            ok = await notifications.show_new_episode(
                anime_session=anime_session,
                title=title,
                episode=newest,
                poster_path=self._cache_poster_local(poster, anime_session),
            )
            if ok:
                fired += 1
            await self.store.set_follow_progress(anime_session, newest)
        return fired

    def _cache_poster_local(self, poster_url: str, anime_session: str) -> str | None:
        """BigPicture needs a LOCAL file — mirror the poster once into the
        CACHE tier. None when it can't be fetched (the notification then
        ships without the art).

        The cache tier, not data: a poster is regenerable (the next pass
        re-fetches it), and the OS may purge the cache dir under storage
        pressure — losing one costs one re-fetch. The path is absolute
        (the old relative one landed wherever the process cwd happened
        to be: under `flet run` that is storage/data, so the posters
        nested inside it, and on a device it was simply unpredictable).
        """
        if not poster_url or not poster_url.startswith("http"):
            return None
        from core import notifications
        from core.tasks import spawn

        cache_dir = app_cache_dir("posters")
        path = os.path.join(
            cache_dir, notifications.stable_filename(anime_session)
        )

        async def _fetch():
            try:
                client = self.kwik._get_client()
                resp = await client.get(poster_url, timeout=15)
                if resp.status_code == 200 and resp.content:
                    with open(path, "wb") as f:
                        f.write(resp.content)
                    self._trim_poster_cache()
            except Exception as ex:
                logger.debug("poster cache failed: %s", ex)

        spawn(_fetch(), name="cache-notify-poster")
        return path if os.path.exists(path) else None

    def _trim_poster_cache(self, keep: int = 50) -> None:
        """Bounded, oldest-first: the one directory the app grows without
        a cap. Fifty posters is a few MB and covers any realistic follow
        list; the rest re-fetch on their next notification."""
        try:
            root = app_cache_dir("posters")
            entries = sorted(
                (os.path.join(root, name) for name in os.listdir(root)),
                key=os.path.getmtime,
            )
            for stale in entries[:-keep] if len(entries) > keep else []:
                with contextlib.suppress(OSError):
                    os.unlink(stale)
        except OSError as ex:
            logger.debug("poster cache trim failed: %s", ex)

    async def start_episode_checker(self) -> None:
        """App start + every 6 hours: the new-episode pass for follows."""
        from core import notifications
        from core.tasks import spawn

        async def _loop():
            await asyncio.sleep(5.0)
            await notifications.ensure_channel()
            while True:
                try:
                    await self.check_new_episodes()
                except Exception as ex:
                    logger.warning("episode checker pass failed: %s", ex)
                await asyncio.sleep(6 * 3600)

        spawn(_loop(), name="episode-checker")

    async def resolve_startup(self):
        """Pick the session's backend once, then load the first home page.

        A stored preference pins directly; "auto" probes the four OPEN
        backends in editorial order and pins the winner IN MEMORY ONLY (the
        store keeps "auto", so the next launch resolves again). AnimePahe is
        never auto-chosen — selecting it is the owner's pin, and its
        Cloudflare flow appears exactly then. Single-flight via a lock; the
        splash stays up (startup_ready False) for the whole flow, in a
        finally so a failed fetch still lands on an honest home.
        """
        async with self._startup_lock:
            state.startup_ready = False
            state.startup_stage = "Finding a source…"
            preference = await self.store.get_backend()
            if preference and preference != "auto":
                self.router.set_pin(preference)
            else:
                self.router.set_pin(await self._auto_backend())
            state.startup_stage = "Loading releases…"
            try:
                await self.load_latest(1)
            finally:
                state.startup_stage = ""
                state.startup_ready = True

    async def _auto_backend(self) -> str | None:
        """First healthy OPEN backend in editorial order, or the first open
        backend when none answer (an honest failure beats no session)."""
        health = await self.router.probe_all()
        open_names = [
            name
            for name in self.router.provider_names
            if name != self._default_owner
        ]
        for name in open_names:
            if health.get(name):
                return name
        return open_names[0] if open_names else None

    async def set_backend_pin(self, name: str):
        """Settings: 'auto' or a provider name. Applies immediately and
        persists, then every switch — manual or a re-pick of Automatic —
        goes through the startup gate: splash → resolve → first fetch."""
        self.router.set_pin(name)
        await self.store.save_backend(name)
        logger.info("content source pinned to: %s", self.router.pin or "auto")
        spawn(self.resolve_startup(), name="backend-switch")

    async def open_backend_picker(self) -> None:
        """The header badge's dialog: every provider with its live health,
        one-tap pinning. Shell-owned (the portal), so the state flag the
        portal watches lives here."""
        state.backend_picker_open = True

    async def pin_backend(self, name: str) -> None:
        """One-tap pin from the picker; the picker closes and stays shut
        until the badge is tapped again."""
        await self.set_backend_pin(name)
        state.backend_picker_open = False

    async def close_player(self):
        state.player_open = False
        state.episodes_version += 1

    async def play_adjacent(self, delta: int):
        """Next/previous episode within the loaded page."""
        current = state.current_episode_session
        episodes = state.episodes or []
        if not episodes or not current:
            return
        index = next((i for i, e in enumerate(episodes) if e.session == current), None)
        if index is None:
            return
        target = index + delta
        if target < 0 or target >= len(episodes):
            return
        nxt = episodes[target]
        await self.close_player()
        await self.play_episode(state.current_anime_session, nxt.session)

    async def _play_episode_external(self, anime_session: str, episode_session: str):
        """The 1.0.9 external flow: quality dialog (all sources), resolve the
        chosen one, hand the m3u8 to KTV with a human title."""
        try:
            sources = await self.router.sources(anime_session, episode_session)
        except Exception as ex:
            logger.error("external: sources failed: %s", ex)
            self._show_error_snackbar("Couldn't load the stream sources.")
            return
        if not sources:
            self._show_error_snackbar("No stream found for this episode.")
            return
        sources = sorted(
            sources,
            key=lambda s: (str(s.audio or "").lower().startswith("eng"), -s.resolution),
        )

        choices: list[dict] = []
        for src in sources:
            audio_label = (
                "DUB (ENG)"
                if "eng" in (src.audio or "").lower()
                else f"SUB ({(src.audio or 'jpn').upper()})"
            )
            label = f"{src.resolution}p - {audio_label}"
            if src.fansub:
                label += f" ({src.fansub})"
            if getattr(src, "size", ""):
                label += f" [{src.size}]"
            if getattr(src, "bd", False):
                label += " [BD]"
            choices.append(
                {
                    "label": label,
                    "kind": "source",
                    "url": src.url,
                    "headers": src.headers,
                    "subtitles": src.subtitles,
                    "skip": src.skip,
                    # the site's own download route, when it serves one
                    "download_url": getattr(src, "download_url", "") or "",
                    # ...and that route needs NO unpacking: the provider
                    # authored it as a file, so resolving it through the
                    # owner's kwik path would fail and fall back to the
                    # stream URL — the site's own offering never used.
                    "direct": bool(getattr(src, "download_url", "")),
                }
            )

        state.selected_source = sources[0]
        if len(choices) <= 1:
            await self._resolve_and_launch_external(
                sources[0], anime_session, episode_session
            )
            return
        state.quality_choices = choices
        state.quality_dialog_open = True
        # Reuse the dialog portal; the choice handler routes by the current
        # external-player setting, so it lands back here.
        state.pending_playback = {
            "external": True,
            "anime_session": anime_session,
            "episode_session": episode_session,
            "m3u8": None,
            "variants": [],
        }
        state.episodes_version += 1

    async def _resolve_and_launch_external(
        self, source, anime_session: str, episode_session: str
    ):
        """Resolve one kwik source and hand the m3u8 to KTV, exactly as the
        old app did (TimeoutError counts as launch success)."""
        self._resolve_stage(self._play_gen, "Resolving stream…")
        m3u8 = await self._resolve_source(source.url, anime_session)
        if not m3u8:
            self._show_error_snackbar("Failed to resolve the stream.")
            return
        self._resolved_m3u8 = m3u8
        anime = await self._resolve_anime(anime_session)
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        from services.external_player import episode_title, launch_external

        await launch_external(
            self.page,
            m3u8,
            episode_title(
                (anime or {}).get("title", "Anime"),
                ep.episode if ep else None,
                source.resolution,
            ),
        )

    async def _open_external_player(self, anime_session: str, episode_session: str):
        """Fallback: hand the resolved stream to KTV Player.

        The deep link carries the m3u8 (base64) and a human title, exactly
        as the original build did; a failed launch offers the KTV install
        dialog instead of failing silently. If we never resolved a stream,
        the caller passes m3u8=None and we hand over the play-page URL.
        """
        anime = await self._resolve_anime(anime_session)
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        title = (anime or {}).get("title", "Anime")
        ep_num = ep.episode if ep else None

        from services.external_player import episode_title, launch_external

        if not self._resolved_m3u8:
            # Nothing resolved. The old path handed the site's play page to
            # KTV — but that URL embeds ANOTHER backend's session (a
            # kusonime one produced animepahe.com/play/kusonime:9538/…,
            # which can never resolve), and a launch with no stream at all
            # just raised the install dialog for nothing. Say what is true
            # instead; a backend with no stream is a result, not a handoff.
            logger.warning("external fallback with no resolved stream")
            self._show_error_snackbar("No playable stream for this episode.")
            return

        resolution = state.selected_source.resolution if state.selected_source else None
        await launch_external(
            self.page,
            self._resolved_m3u8,
            episode_title(title, ep_num, resolution),
        )

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    async def download_series(
        self, anime_session: str, episode_sessions: list[str], preset: str = "highest"
    ) -> int:
        """"Download the series": every episode in the range, queued.

        Each episode is its INDEPENDENT job — one failing (a walled link,
        a dead host) does not stop the rest, exactly Media3's per-request
        model. The queue's cap absorbs them, so a 170-episode series is a
        queue and not a burst. Returns how many were queued."""
        queued = 0
        for episode_session in episode_sessions:
            if episode_session in self.downloads.active_jobs:
                continue
            rows = await self.store.get_downloads()
            if (rows.get(episode_session) or {}).get("state") == "complete":
                continue
            # The whole episode is guarded: a dead host, a walled link or
            # an I/O failure must cost THIS episode only.
            state.starting_downloads.add(episode_session)
            state.busy_version += 1
            try:
                sources = await self.router.sources(anime_session, episode_session)
                if not sources:
                    continue
                choice = _preset_choice(_source_choices(sources), preset)
                if not choice:
                    continue
                await self._begin_download(
                    choice,
                    anime_session,
                    episode_session,
                    next(
                        (e for e in state.episodes if e.session == episode_session),
                        None,
                    ),
                    await self._resolve_anime(anime_session),
                )
                queued += 1
            except Exception as ex:
                logger.warning("series download skipped %s: %s", episode_session, ex)
            finally:
                self._finish_download_start(episode_session)
        state.downloads_version += 1
        logger.info(
            "series download: %d of %d queued (%s)",
            queued,
            len(episode_sessions),
            preset,
        )
        return queued

    async def download_episode(self, anime_session: str, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session)
        if row and row.get("state") == "complete":
            return
        if episode_session in self.downloads.active_jobs:
            return

        anime = await self._resolve_anime(anime_session)
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        # The button shows a spinner until the job actually starts — the
        # source + kwik resolve before it can take seconds.
        state.starting_downloads.add(episode_session)
        state.busy_version += 1
        try:
            sources = await self.router.sources(anime_session, episode_session)
        except Exception as ex:
            logger.error("download: sources failed: %s", ex)
            self._show_error_snackbar("Couldn't start the download.")
            self._finish_download_start(episode_session)
            return
        if not sources:
            self._show_error_snackbar("No stream found for this episode.")
            self._finish_download_start(episode_session)
            return

        # A silent sources[0] downloads whatever the provider listed first
        # — a 360p when a 1080p exists. The same list the play dialog
        # shows, so the user picks; a single rendition starts immediately.
        choices = _source_choices(sources)
        if len(choices) > 1:
            state.pending_download = {
                "anime_session": anime_session,
                "episode_session": episode_session,
                "title": (anime or {}).get("title", ""),
                "poster": (anime or {}).get("poster", ""),
                "episode_num": ep.episode if ep else 0,
                "anime_id": ep.anime_id if ep else 0,
            }
            state.download_choices = choices
            state.download_choice_open = True
            self._finish_download_start(episode_session)
            return
        # try/finally, not a trailing call: an I/O error inside _begin_download
        # (store, manifest, full disk) must not leave the row's spinner
        # spinning for the rest of the session.
        try:
            await self._begin_download(
                choices[0], anime_session, episode_session, ep, anime
            )
        finally:
            self._finish_download_start(episode_session)

    async def choose_download_quality(self, index: int):
        """The download dialog's pick — resolve and start that rendition."""
        pending = state.pending_download or {}
        choices = state.download_choices or []
        if not pending or index < 0 or index >= len(choices):
            return
        state.download_choice_open = False
        state.download_choices = None
        state.pending_download = None
        ep = next(
            (e for e in state.episodes if e.session == pending.get("episode_session")),
            None,
        )
        state.starting_downloads.add(pending.get("episode_session"))
        state.busy_version += 1
        try:
            await self._begin_download(
                choices[index],
                pending.get("anime_session"),
                pending.get("episode_session"),
                ep,
                pending,
            )
        finally:
            self._finish_download_start(pending.get("episode_session"))

    async def _begin_download(
        self,
        choice: dict,
        anime_session: str,
        episode_session: str,
        ep,
        anime: dict | None,
    ):
        """Resolve one chosen rendition and start the job."""
        source_headers = dict(choice.get("headers") or {})
        # The provider's own download route when the source serves one
        # (animepahe's pahe.win link) — the site authored it as a file, so
        # it is used as-is and the stream URL is only the fallback.
        download_url = choice.get("download_url") or choice["url"]
        if choice.get("direct"):
            resolved = download_url
        else:
            resolved = await self._resolve_source(download_url, anime_session)
            if not resolved and download_url != choice["url"]:
                resolved = await self._resolve_source(choice["url"], anime_session)
        if not resolved:
            self._show_error_snackbar("Couldn't resolve the stream for download.")
            return

        # The provider's own filename when it has one — the saved copy
        # keeps what the source called it (quality and fansub included).
        provider = self.router.get(self._owner_of(anime_session or ""))
        filename = None
        if provider is not None and hasattr(provider, "file_name"):
            try:
                filename = provider.file_name(anime_session, episode_session)
            except Exception as ex:
                logger.debug("provider filename lookup failed: %s", ex)

        metadata = {
            "anime_session": anime_session,
            "anime_id": (ep.anime_id if ep else 0) or (anime or {}).get("anime_id", 0),
            "title": (anime or {}).get("title", ""),
            "poster": (anime or {}).get("poster", ""),
            "episode_num": ep.episode if ep else 0,
            "filename": filename or "",
        }
        rows = await self.store.get_downloads()
        row = dict(metadata)
        row.update({"state": "partial"})
        await self.store.save_download(episode_session, row)
        state.downloads = rows | {episode_session: row}
        state.downloads_version += 1

        # One resolution, two shapes — decided by what the media IS, never
        # by which source it came from: a file is fetched directly, an
        # m3u8 by its segments, at whatever quality it serves. The same
        # peek carries the server's own filename, so the saved copy keeps
        # it when the provider didn't supply one.
        kind, server_name = await self.downloads.detect_kind(resolved, source_headers)
        if kind == "file" and server_name and not metadata["filename"]:
            metadata["filename"] = server_name
            row["filename"] = server_name
            await self.store.save_download(episode_session, row)
        if kind == "file":
            await self.downloads.start_direct(
                episode_session, resolved, source_headers, metadata
            )
        else:
            from components.player.immersive_player import KWIK_USER_AGENT

            if not source_headers:
                source_headers = {
                    "User-Agent": KWIK_USER_AGENT,
                    "Referer": "https://kwik.cx/",
                }
            await self.downloads.start(
                episode_session, resolved, source_headers, metadata
            )

    def _finish_download_start(self, episode_session: str) -> None:
        state.starting_downloads.discard(episode_session)
        state.busy_version += 1
        state.downloads_version += 1

    async def pause_download(self, episode_session: str):
        """Pause keeps the partials — a Range resume continues from them."""
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        self.downloads.pause(episode_session)
        state.download_progress = _with_job_state(
            state.download_progress, episode_session, "stopped"
        )
        row = {**row, "state": "partial"}
        await self.store.save_download(episode_session, row)
        state.downloads_version += 1

    async def resume_download(self, episode_session: str):
        """Resume (or retry) from the job's own manifest."""
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        job_dir = self.downloads._job_dir(
            row.get("anime_session", "unknown"), episode_session
        )
        manifest = self.downloads._read_manifest(
            os.path.join(job_dir, "manifest.json")
        )
        state.download_progress = _with_job_state(
            state.download_progress, episode_session, "downloading"
        )
        await self.downloads.resume(
            episode_session,
            manifest.get("url") or manifest.get("m3u8_url") or "",
            manifest.get("headers") or {},
            manifest.get("metadata") or row,
        )
        state.downloads_version += 1

    async def retry_download(self, episode_session: str):
        """A failed job re-queued from its own manifest."""
        await self.downloads.retry(episode_session)
        state.download_progress = _with_job_state(
            state.download_progress, episode_session, "queued"
        )
        state.downloads_version += 1

    async def cancel_download(self, episode_session: str):
        self.downloads.cancel(episode_session)

    async def delete_download(self, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        # The manager owns the layout (and its platform-safe name mapping);
        # computing the path here would drift from where the file lives.
        self.downloads.remove_job(row.get("anime_session", "unknown"), episode_session)
        await self.store.remove_download(episode_session)
        rows.pop(episode_session, None)
        state.downloads = rows
        state.downloads_version += 1

    async def play_downloaded(self, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        local = row.get("playlist") or row.get("file")
        if not local or not os.path.exists(local):
            # Open the player branch on the error card — staying on Downloads
            # with no feedback looks like the tap did nothing.
            state.player_error = "The downloaded file is missing."
            state.player_open = True
            state.episodes_version += 1
            return
        state.player_error = None
        # Local playback (an .m3u8 rewrite or a fetched file) needs no
        # request headers — the bytes are already on disk.
        state.player_spec = {
            "resource": local,
            "variants": [],
            "title": row.get("title", "AnimePahe"),
            "episode_session": episode_session,
            "anime_session": row.get("anime_session", ""),
            "headers": {},
        }
        state.player_open = True
        state.episodes_version += 1

    def _on_download_progress(self, episode_session: str, progress: dict):
        """Segment-level progress, throttled to ~2 UI updates/second.

        Each segment callback used to bump downloads_version, re-rendering
        the whole downloads tree per chunk. Now the latest value is cached
        and a single flusher runs while any job is active.
        """
        self._pending_progress[episode_session] = progress
        if self._progress_flush_task is None or self._progress_flush_task.done():
            self._progress_flush_task = spawn(
                self._flush_download_progress(), name="download-progress-flush"
            )

    async def _flush_download_progress(self):
        """One flush every ~0.5s while any job is active: the UI's rows
        AND the tray's progress notification (the package advances a row
        by re-showing its id). The UI polls; nothing re-renders per
        chunk."""
        while self._pending_progress:
            await asyncio.sleep(_PROGRESS_FLUSH_SECONDS)
            pending, self._pending_progress = self._pending_progress, {}
            if not pending:
                return
            merged = dict(state.download_progress or {})
            merged.update(pending)
            state.download_progress = merged
            state.downloads_version += 1
            await self._sync_download_notifications(merged)

    async def _sync_download_notifications(self, progress: dict) -> None:
        """One tray row per running download, advanced by re-showing its
        id. Off-platform (and off dev-mode) it is a no-op."""
        from core import notifications

        for session, row in progress.items():
            state_name = str(row.get("state") or "")
            if state_name not in ("downloading", "queued", "paused", "failed"):
                continue
            percent = row.get("percent")
            body = (
                f"{percent:.0f}%" if isinstance(percent, (int, float)) else "Downloading…"
            )
            if state_name == "paused":
                body = "Paused"
            elif state_name == "failed":
                body = "Download failed — tap to retry"
            await notifications.show_progress(
                notification_id=notifications.download_id(session),
                title=row.get("title") or "Downloading",
                body=body,
                payload=notifications.payload_for(row.get("anime_session") or ""),
                progress=int(percent or 0),
                max_progress=100,
                indeterminate=not isinstance(percent, (int, float)),
            )

    def _on_download_finished(self, episode_session: str, metadata: dict) -> None:
        """A finished download replaces its progress row with a
        completion one — same id, so the tray never holds two rows for
        one episode, and the tap deep-links to the anime."""
        from core import notifications
        from core.tasks import spawn

        async def _announce():
            await notifications.show_new_episode(
                anime_session=str(metadata.get("anime_session") or ""),
                title=str(metadata.get("title") or "Download"),
                episode=int(metadata.get("episode_num") or 0),
                poster_path=None,
                download_complete=True,
                episode_session=episode_session,
            )

        spawn(_announce(), name="download-done")

    async def _resolve_anime(self, anime_session: str) -> dict | None:
        """Title/poster/metadata for an anime, cheapest source first.

        Order: in-memory releases/search results → Continue Watching store →
        (only then, for cold links) a title search, which is how the original
        self-healed a snapshot poster. Episodes never need this — they load
        by session — but the detail screen's header does.
        """
        for release in state.latest_releases:
            if release.anime_session == anime_session:
                return {
                    "title": release.anime_title,
                    "poster": release.snapshot,
                    "episodes": 0,
                    "year": 0,
                    "type": "",
                    "status": "",
                    "score": 0.0,
                    "season": "",
                }
        for anime in state.search_results:
            if anime.session == anime_session:
                return _anime_dict(anime)
        entry = (await self.store.get_continue_watching()).get(anime_session)
        if entry:
            return {
                "title": entry.get("title", ""),
                "poster": entry.get("poster", ""),
                "episodes": entry.get("total_episodes", 0),
                "year": 0,
                "type": "",
                "status": "",
                "score": 0.0,
                "season": "",
            }
        # Cold link: the owning provider's details first (anikato serves
        # synopsis/type/status/score from the watch page), then the title
        # search self-heal as the last resort.
        provider = self.router.get(self._owner_of(anime_session))
        if provider is not None and hasattr(provider, "anime"):
            try:
                details = await provider.anime(anime_session)
            except Exception as ex:
                logger.warning("provider details failed for %s: %s", anime_session, ex)
                details = None
            if details is not None:
                return _anime_dict(details)
        return await self._resolve_anime_by_search(anime_session)

    async def _resolve_anime_by_search(self, anime_session: str) -> dict | None:
        """Self-heal a cold-opened anime: derive a title from the episodes we
        already have, search with it, and keep the match for this session."""
        title_guess = ""
        for release in state.latest_releases:
            if release.anime_session == anime_session:
                title_guess = release.anime_title
                break
        if not title_guess:
            return None
        try:
            # Owner-scoped: the cold-open self-heal belongs to this
            # session's own backend.
            results, _ = await self.router.search(
                title_guess, 1, owner=self._owner_of(anime_session)
            )
        except Exception as ex:
            logger.warning("anime self-heal search failed: %s", ex)
            return None
        matched = next((a for a in results if a.session == anime_session), None)
        if matched is None:
            return None
        # Cache it so the next open is free.
        state.search_results = [matched] + [
            a for a in state.search_results if a.session != anime_session
        ]
        return _anime_dict(matched)

    async def load_anime(self, anime_session: str):
        """Open the detail screen: resolve the header, then load episodes."""
        if state.current_anime_session != anime_session:
            # The new session must land with an EMPTY episode list in the
            # SAME render. The previous anime's rows used to stay clickable
            # while the new load ran (resolve + CF retries take seconds),
            # so a tap paired the NEW anime with the OLD anime's episode
            # session — "player opening for kusonime:48968 / 48025|1".
            state.episodes = []
            state.episodes_has_more = True
        state.current_anime_session = anime_session
        state.episodes_version += 1
        anime = await self._resolve_anime(anime_session)
        state.selected_anime = anime
        await self.load_episodes(anime_session, 1)

    async def load_search(self, query: str, page: int = 1):
        if not query:
            return
        lock = self._get_lock("search")
        async with lock:
            # Generation counter: a slow response for an older query must
            # never overwrite a newer one's results.
            self._search_gen += 1
            gen = self._search_gen

            state.is_loading = True
            state.search_query = query
            state.search_page = page
            state.search_error = None
            state.search_version += 1

            try:
                results, has_more = await self.router.search(query, page)
                if gen != self._search_gen:
                    logger.info("load_search discarding stale response for %r", query)
                    return
                if not session_alive():
                    logger.info("load_search q=%r dropped (session gone)", query)
                    return
                state.search_results = results
                state.search_has_more = has_more
                state.search_source = self.router.last_winner or ""
                if page == 1:
                    state.cf_blocked = False
                    await self.store.add_search(query)
                    state.search_history = await self.store.get_search_history()
            except Exception as ex:
                logger.error("load_search q=%r page=%d failed: %s", query, page, ex)
                if gen == self._search_gen and session_alive():
                    state.search_results = []
                    state.search_has_more = False
                    state.search_error = str(ex)
            finally:
                if gen == self._search_gen:
                    ui_set(state, "is_loading", False)
                    if session_alive():
                        state.search_version += 1

    async def toggle_follow(self, row: dict) -> bool:
        """Follow/unfollow a WHOLE anime; bumps the version so every
        shelf showing follows re-renders."""
        if not isinstance(row, dict):
            return False
        following = await self.store.toggle_follow(row)
        state.follows = await self.store.get_follows()
        state.follows_version += 1
        return following

    async def record_search_selection(self, anime) -> None:
        """A search result was opened: remember the ANIME (title + session),
        so recents show 'Black Clover Season 1' rather than the typed text."""
        if anime is None:
            return
        title = getattr(anime, "title", "") or ""
        session = getattr(anime, "session", "") or ""
        if not title:
            return
        await self.store.add_search_selection(title, session)
        state.search_history = await self.store.get_search_history()

    async def remove_search(self, title: str, session: str = "") -> None:
        await self.store.remove_search(title, session)
        state.search_history = await self.store.get_search_history()

    async def clear_search_history(self):
        """Clear with Undo (DDGS's shape): the snack action restores the
        exact rows — one-tap data loss was the old behavior."""
        rows = await self.store.clear_search_history()
        state.search_history = []
        state.search_version += 1
        if not rows:
            return

        def _undo():
            async def _restore():
                await self.store.restore_search_history(rows)
                state.search_history = await self.store.get_search_history()
                state.search_version += 1

            from core.tasks import spawn

            spawn(_restore(), name="undo-clear-history")

        from core.notify import show_snack

        show_snack(
            self.page, "Recent searches cleared", action_label="Undo", on_action=_undo
        )


async def main(page: ft.Page):
    controller = AppController(page)
    await controller.init()

    # Unhandled exceptions in event handlers land here — the only place a
    # crash is visible to the user at all. Console line (via logger) plus a
    # snack, so a broken tap never looks like a dead app.
    def _on_page_error(e):
        message = str(getattr(e, "data", None) or e)
        logger.error("unhandled page error: %s", message)
        show_snack(page, "Something went wrong.", bgcolor=AppColors.ERROR)

    page.on_error = _on_page_error

    methods = ControllerMethods()
    methods.load_latest = lambda page_num=1: spawn(
        controller.load_latest(page_num), name="load-latest"
    )
    methods.load_discover_filters = lambda: spawn(
        controller.load_discover_filters(), name="load-discover-filters"
    )
    methods.load_discover = lambda selections=None, page=1: spawn(
        controller.load_discover(selections, page), name="load-discover"
    )
    methods.retry_cloudflare = lambda: spawn(
        controller.retry_cloudflare(), name="retry-cf"
    )
    methods.load_episodes = lambda session, page_num=1: spawn(
        controller.load_episodes(session, page_num), name="load-episodes"
    )
    methods.open_schedule = lambda: spawn(
        controller.open_schedule(), name="open-schedule"
    )
    methods.open_random = lambda: spawn(controller.open_random(), name="open-random")
    methods.load_anime = lambda session: spawn(
        controller.load_anime(session), name="load-anime"
    )
    methods.play_episode = lambda anime_session, episode_session: spawn(
        controller.play_episode(anime_session, episode_session), name="play-episode"
    )
    methods.download_series = (
        lambda anime_session, episode_sessions, preset="highest": spawn(
            controller.download_series(anime_session, episode_sessions, preset),
            name="download-series",
        )
    )
    methods.report_broken_stream = (
        lambda anime_session, episode_session, issues, note="": spawn(
            controller.report_broken_stream(anime_session, episode_session, issues, note),
            name="report-broken",
        )
    )
    methods.load_search = lambda query, page=1: spawn(
        controller.load_search(query, page), name="load-search"
    )
    methods.clear_search_history = lambda: spawn(
        controller.clear_search_history(), name="clear-search-history"
    )
    methods.choose_quality = lambda index: spawn(
        controller.choose_quality(index), name="choose-quality"
    )
    methods.close_player = lambda: spawn(controller.close_player(), name="close-player")
    # Sync action: no spawn() — create_task(None) would raise.
    methods.cancel_resolve = lambda: controller.cancel_resolve()
    methods.toggle_follow = lambda row: spawn(
        controller.toggle_follow(row), name="toggle-follow"
    )
    methods.record_search_selection = lambda anime: spawn(
        controller.record_search_selection(anime), name="record-search-selection"
    )
    methods.remove_search = lambda title, session="": spawn(
        controller.remove_search(title, session), name="remove-search"
    )
    methods.play_adjacent = lambda delta: spawn(
        controller.play_adjacent(delta), name="play-adjacent"
    )
    methods.download_episode = lambda a, e: spawn(
        controller.download_episode(a, e), name="download-episode"
    )
    methods.choose_download_quality = lambda index: spawn(
        controller.choose_download_quality(index), name="choose-download-quality"
    )
    methods.cancel_download = lambda e: spawn(
        controller.cancel_download(e), name="cancel-download"
    )
    methods.pause_download = lambda e: spawn(
        controller.pause_download(e), name="pause-download"
    )
    methods.resume_download = lambda e: spawn(
        controller.resume_download(e), name="resume-download"
    )
    methods.retry_download = lambda e: spawn(
        controller.retry_download(e), name="retry-download"
    )
    methods.delete_download = lambda e: spawn(
        controller.delete_download(e), name="delete-download"
    )
    methods.play_downloaded = lambda e: spawn(
        controller.play_downloaded(e), name="play-downloaded"
    )

    # The shell's player branch reaches the controller through this handle
    # (its ControllerMethods copy is the shell-owned navigation half).
    methods.test_all_sources = lambda: spawn(
        controller.test_all_sources(), name="test-all-sources"
    )
    methods.try_another_source = lambda session: spawn(
        controller.try_another_source(session), name="try-another-source"
    )
    methods.sources_status = controller.sources_status
    methods.set_backend_pin = lambda name: spawn(
        controller.set_backend_pin(name), name="set-backend-pin"
    )
    methods.open_backend_picker = lambda: spawn(
        controller.open_backend_picker(), name="open-backend-picker"
    )
    methods.pin_backend = lambda name: spawn(
        controller.pin_backend(name), name="pin-backend"
    )
    methods._app_controller = controller
    controller.shell = methods

    # Ads: one SDK service on the page, guarded to the mobile family.
    try:
        from services.ads import build_ad_service, show_app_open

        ad_service = build_ad_service(
            page,
            on_initialized=lambda e: spawn(show_app_open(page), name="app-open"),
            on_init_failed=lambda e: logger.warning(
                "ad init failed: %s", getattr(e, "data", e)
            ),
        )
        if ad_service is not None and not isinstance(ad_service, ft.Container):
            page.services.append(ad_service)
    except Exception as ex:
        logger.warning("ad service setup skipped: %s", ex)

    page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
