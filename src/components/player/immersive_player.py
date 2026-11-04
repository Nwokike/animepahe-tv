"""ImmersivePlayer — the in-app episode player (KTV skeleton).

Ported from ktv-player's player (immersive_player.py + controls.py +
handlers.py): the same lifecycle, the same single back funnel, the same
watchdog, the same quality/audio pinning through the HLS proxy. Everything
KTV-specific is stripped (YouTube resolver, PiP, favourites, the database
manager); everything animepahe-specific rides on top:

- the Yandex interstitial fires INSIDE start_playback, right before the
  playlist attaches (KTV's placement; owner-verified timing),
- resume reads/writes the app store (get_position/save_position) keyed by
  the episode session, with the saved playback rate restored,
- skip intro/outro chip driven by the source's skip windows,
- next/previous episode via shell-owned callbacks (auto-advance on a real
  completion),
- subtitles: the source's tracks (proxy-routed; fetched to raw text so the
  phone's mpv never fights the CDN), downloaded sidecar files (local
  paths), and a device file picker — the default track is applied AFTER
  the media attaches and re-applied after every quality/audio swap,
- downloaded files play directly (no proxy) when proxied=False.
"""

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable
from typing import Any, ClassVar

import flet as ft
import flet_video as fv

from core.theme import AppColors

logger = logging.getLogger(__name__)

# Absolute backstop: if no load/position/error event arrives within this
# window, the loading/reconnecting overlay is replaced by the retry/back UI.
# mpv's network-timeout (10s) usually errors out first with a real reason.
_WATCHDOG_SECONDS = 20.0

# Periodic VOD position checkpoint interval (see _maybe_save_position_periodically).
_POSITION_SAVE_INTERVAL = 10.0

# Position saves started from will_unmount (a sync hook) can outlive the
# page. They are tracked so shutdown can await them instead of leaving the
# write to a loop that is about to close.
_orphan_tasks: set = set()


def _keep(task: asyncio.Task) -> None:
    """Hold a strong reference to a fire-and-forget task.

    asyncio keeps only weak references to tasks, so a bare create_task can
    be collected before it finishes. Tracked here and dropped on completion,
    so nothing leaks.
    """
    _orphan_tasks.add(task)
    task.add_done_callback(_orphan_tasks.discard)


async def _await_result(awaitable) -> None:
    """Await an already-created coroutine for page.run_task.

    page.run_task takes a coroutine FUNCTION, not the coroutine object.
    """
    await awaitable


def _short_variant_label(variant: dict) -> str:
    """Compact chip label: '1280x720' -> '720p', else bandwidth."""
    resolution = variant.get("resolution") or ""
    if "x" in resolution:
        return f"{resolution.split('x')[-1]}p"
    bandwidth = variant.get("bandwidth", 0)
    if bandwidth >= 1_000_000:
        return f"{bandwidth / 1_000_000:.0f}M"
    return f"V{(variant.get('index') or 0) + 1}"


def _mpv_props(referer: str) -> dict:
    """mpv tuning for network media. The source's referer rides
    http-header-fields so segment requests carry it even when a source is
    fetched directly (no proxy in the path)."""
    return {
        "http-header-fields": f"Referer: {referer}",
        "cache": "yes",
        "cache-secs": 5,
        "demuxer-max-bytes": "50M",
        "demuxer-max-back-bytes": "10M",
        "framedrop": "vo",
        "hr-seek-framedrop": "yes",
        # mpv default is 60s — dead hosts would spin the loading overlay
        # for a minute with no error event. 10s makes failure deterministic.
        "network-timeout": 10,
    }


_BOX_FITS = {
    "contain": ft.BoxFit.CONTAIN,
    "cover": ft.BoxFit.COVER,
    "fill": ft.BoxFit.FILL,
}

SPEEDS = (0.25, 0.5, 1.0, 1.25, 1.5, 2.0)


class ImmersivePlayer(ft.Stack):
    def __init__(
        self,
        resource: str,
        on_close: Callable | None = None,
        title: str = "",
        autoplay: bool = True,
        http_headers: dict | None = None,
        hls_proxy: Any | None = None,
        source_url: str = "",
        source_referer: str | None = None,
        source_headers: dict | None = None,
        source_proxied: bool = False,
        # animepahe-specific
        on_next: Callable | None = None,
        on_previous: Callable | None = None,
        resume_key: str | None = None,
        store=None,
        subtitles: list | None = None,
        skip: dict | None = None,
        variants: list | None = None,
        variant_index: int | None = None,
    ):
        super().__init__()
        self.resource = resource
        self._original_resource = resource
        self.on_close = on_close
        self.title = title
        self.http_headers = http_headers or {}
        self.expand = True

        # Quality / audio-track switching (HLS proxy manifest pinning)
        self.hls_proxy = hls_proxy
        self.source_url = source_url or resource
        self.source_referer = source_referer
        self.source_headers = source_headers
        self.source_proxied = source_proxied
        self._current_audio: str | None = None
        self._audio_tracks_cache: list[dict] | None = None

        # animepahe-specific wiring
        self.on_next = on_next
        self.on_previous = on_previous
        self.resume_key = resume_key
        self.store = store
        self.subtitles = subtitles or []
        self.skip = skip or {}
        self._local_subtitle: dict | None = None
        self._subtitle_applied = False
        self._subtitle_selection: str | int | None = "auto"
        self._media_attached = False
        # The quality the user picked in the dialog rides the spec: the
        # player STARTS pinned to it (no "Auto" — the owner's rule: the
        # label always names a concrete quality).
        self._current_variant = variant_index
        self._variants_cache = list(variants) if variants else None

        # Resume-from-last-position: one-shot seek consumed by the first
        # position-change tick after playback starts. _pending_seek is set
        # by _swap_media; _initial_resume_position comes from the store.
        self._pending_seek: float | None = None
        self._initial_resume_position: float | None = None
        self._last_position: float = 0.0
        self._last_duration: float = 0.0
        self._last_position_save: float = 0.0
        # Set after an awaited close-path save so a racing back-press
        # doesn't skip the position write — see the shell's close funnel.
        self._position_saved: bool = False

        self._retry_count = 0
        self._reconnect_count = 0
        # True only once the stream has actually produced playback. flet_video
        # notifies `complete` the moment a fresh playlist is attached and mpv
        # has nothing decoded yet; that notification is not an end-of-stream.
        self._playback_started = False
        self._is_final_error = False
        self._is_closing = False
        self._watchdog_task: asyncio.Task | None = None
        self._checkpoint_task: asyncio.Task | None = None

        # Overlay controls
        self.status_text = ft.Text(
            "Loading stream...",
            size=15,
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.W_500,
            text_align=ft.TextAlign.CENTER,
        )
        self.loading_ring = ft.ProgressRing(
            width=48,
            height=48,
            stroke_width=4,
            color=AppColors.PRIMARY,
        )

        # Error overlay action buttons
        self.retry_btn = ft.OutlinedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.REFRESH_ROUNDED, size=18),
                    ft.Text("Retry Stream", size=13),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=lambda e: self._run_async(self._manual_retry),
            visible=False,
        )
        self.back_error_btn = ft.FilledButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ARROW_BACK_ROUNDED, size=18),
                    ft.Text("Go Back", size=13),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=lambda e: self._run_async(self._on_back),
            visible=False,
        )
        self.error_actions_row = ft.Row(
            controls=[self.retry_btn, self.back_error_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
            visible=False,
        )

        self.overlay = ft.Container(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    self.loading_ring,
                    ft.Container(height=16),
                    self.status_text,
                    ft.Container(height=16),
                    self.error_actions_row,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )
        self._overlay_hidden = False

        # Speed control
        self._speed_idx = 2  # index of 1.0 in speeds list
        self.speed_text = ft.Text(
            "1.0x",
            size=11,
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.W_600,
        )

        self.video = fv.Video(
            autoplay=autoplay,
            expand=True,
            wakelock=True,
            filter_quality=ft.FilterQuality.LOW,
            pause_upon_entering_background_mode=True,
            resume_upon_entering_foreground_mode=False,
            playlist_mode=fv.PlaylistMode.NONE,
            fill_color=ft.Colors.BLACK,
            fit=self._box_fit(),
            alignment=ft.Alignment.CENTER,
            title=self.title or "AnimePahe TV",
            controls=self._build_controls(),
            subtitle_configuration=fv.VideoSubtitleConfiguration(
                text_style=ft.TextStyle(
                    size=float(self._subtitle_size()),
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.W_600,
                    bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                ),
                text_align=ft.TextAlign.CENTER,
                visible=True,
            ),
            configuration=fv.VideoConfiguration(
                enable_hardware_acceleration=True,
                # hwdec stays at the flet_video platform default (Android:
                # "auto-safe") — the old hard force of "mediacodec" made
                # phone MKVs fail with "Could not open codec"; auto-safe
                # still uses MediaCodec when supported but falls back to
                # software decoding instead of erroring out.
                mpv_properties=_mpv_props(self.source_referer or "https://kwik.cx/"),
            ),
            on_load=self._on_load,
            on_duration_change=self._on_duration_change,
            on_position_change=self._on_pos_change,
            on_error=self._on_error,
            on_complete=self._on_complete,
            on_enter_fullscreen=self._on_enter_fullscreen,
            on_exit_fullscreen=self._on_exit_fullscreen,
        )

        self.controls = [
            ft.Container(expand=True, bgcolor=ft.Colors.BLACK),
            self.video,
            self.overlay,
        ]

    # --- helpers -----------------------------------------------------

    @property
    def safe_page(self):
        try:
            return self.page
        except Exception:
            return None

    def _page(self):
        try:
            from flet import context as flet_context

            return flet_context.page
        except Exception:
            return None

    def _run_async(self, coro_fn, *args):
        """Run a coroutine method on the page loop from a sync callback."""
        page = self.safe_page or self._page()
        if page is not None:
            page.run_task(coro_fn, *args)
            return
        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(coro_fn(*args)))
        except RuntimeError:
            pass

    # --- lifecycle ----------------------------------------------------

    def did_mount(self):
        # The toast/skip chips were created by build_player_controls() in
        # __init__; the fullscreen toast registry must be live before any
        # confirmation can fire.
        try:
            from core.notify import register_fullscreen_toast

            register_fullscreen_toast(self._toast_show)
        except Exception:
            pass
        self._run_async(self.start_playback)

    def will_unmount(self):
        try:
            from core.notify import unregister_fullscreen_toast

            unregister_fullscreen_toast(self._toast_show)
        except Exception:
            pass
        self._cancel_watchdog()
        self._cancel_checkpoints()
        # Orphan position save: the view can be detached without the close
        # funnel ever running (remount races) — never lose the position.
        # save_position_now queries the live video, so this is correct even
        # when no position event ever landed.
        if not self._position_saved and self.resume_key:
            self._position_saved = True
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self.save_position_now())
                _keep(task)
            except RuntimeError:
                pass

    # --- playback -----------------------------------------------------

    async def start_playback(self):
        logger.info(
            "Initializing playback: title='%s', resource='%s'",
            self.title,
            self.resource,
        )
        self._reconnect_count = 0
        # Go Back is available from the very first moment — the player must
        # never be a dead end, not even during the pre-roll ad.
        self._show_progress("Loading stream...")
        await self._read_resume_position()

        # The interstitial fires here — when the video ACTUALLY starts
        # (KTV's placement: inside start_playback, never at episode or
        # quality selection). 20s cap, skip-on-error, never after close.
        if not self._is_closing:
            try:
                from services.ads import is_ads_supported, show_interstitial

                page = self._page()
                if page is not None and is_ads_supported(page):
                    await asyncio.wait_for(show_interstitial(page), timeout=20.0)
            except Exception as ex:
                logger.warning("Ad skipped due to error: %s", ex)

        if self._is_closing:
            logger.info("Playback cancelled — player closed during ad")
            return

        try:
            self.video.playlist = [
                fv.VideoMedia(self.resource, http_headers=self.http_headers),
            ]
            with contextlib.suppress(Exception):
                self.video.update()
            await self.video.play()
            self._start_watchdog()
            self._start_checkpoints()
        except Exception:
            logger.exception("start_playback error")
            self._show_final_error("Could not start playback.")

    async def _read_resume_position(self):
        """Restore the saved position + playback rate for this episode."""
        if not self.store or not self.resume_key:
            return
        try:
            entry = await self.store.get_position(self.resume_key)
        except Exception:
            entry = None
        if not entry:
            return
        try:
            self._initial_resume_position = float(entry["position"])
            self._last_duration = float(entry.get("duration") or 0.0)
        except (TypeError, ValueError, KeyError):
            return
        rate = entry.get("rate")
        if rate and float(rate) != SPEEDS[self._speed_idx]:
            try:
                self._speed_idx = SPEEDS.index(float(rate))
            except ValueError:
                self._speed_idx = 2
            self.video.playback_rate = float(rate)
            if getattr(self, "speed_text", None) is not None:
                self.speed_text.value = f"{float(rate)}x"
        logger.info(
            "resume available for %s at %.1fs",
            self.resume_key,
            self._initial_resume_position,
        )
        # The read can land AFTER the first ready/duration/position signal;
        # re-check so the target is not lost.
        self._check_and_trigger_seek()

    async def _cycle_speed(self):
        from components.player.handlers import cycle_speed

        await cycle_speed(self)

    def _manual_retry(self):
        if self._is_closing:
            return
        self._is_final_error = False
        self._reconnect_count = 0
        self._show_progress("Reconnecting stream...")

        async def _retry():
            try:
                self.video.playlist = [
                    fv.VideoMedia(self.resource, http_headers=self.http_headers),
                ]
                self.video.update()
                await self.video.play()
            except Exception:
                self._show_final_error("Stream is not responding. Retry or go back.")
                return
            self._start_watchdog()

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_retry()))
        except RuntimeError:
            pass

    # --- events ---------------------------------------------------------

    @staticmethod
    def _event_seconds(value) -> float | None:
        """Seconds from an on_position/on_duration event payload.

        flet-video delivers a `flet.Duration` which has no __float__ —
        coercing one with float() raised TypeError, which the old bare
        `except` swallowed; position/duration then stayed at 0.0 and
        resume never had a value to save.
        """
        if isinstance(value, ft.Duration):
            return float(value.in_seconds)
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            # Older event shapes sent milliseconds or microseconds.
            val = float(value)
            if val > 1_000_000:
                return val / 1_000_000.0
            if val > 1_000:
                return val / 1_000.0
            return val
        return None

    def _on_load(self, e=None):
        logger.info("player ready")
        if not self._is_closing and not self._is_final_error:
            self._hide_overlay()

    def _on_duration_change(self, e=None):
        self._maybe_media_attached()
        if not self._overlay_hidden:
            self._hide_overlay()
        if e and getattr(e, "data", None) is not None:
            seconds = self._event_seconds(e.data)
            if seconds is not None:
                self._last_duration = seconds
                if seconds > 0:
                    self._playback_started = True
        self._check_and_trigger_seek()

    def _on_pos_change(self, e=None):
        if not self._overlay_hidden:
            self._hide_overlay()
        if e and getattr(e, "data", None) is not None:
            seconds = self._event_seconds(e.data)
            if seconds is not None:
                self._last_position = seconds
                if seconds > 0:
                    self._playback_started = True
                    # The first positive tick is the proof the media
                    # attached — external subtitle tracks set before this
                    # were silently dropped by mpv (the phone never showed
                    # subtitles; the desktop did, by timing luck).
                    self._maybe_media_attached()
                    self._update_skip_chip(seconds)
        self._check_and_trigger_seek()
        self._maybe_save_position_periodically()

    def _maybe_media_attached(self):
        """One-shot, per attached media: apply the default subtitle track.

        External tracks set before the media attaches are dropped when mpv
        loads the media — and on Android mpv ALSO drops one added while the
        demuxer is still opening (the phone showed subtitles only after a
        manual reselect). So this schedules the apply with retries: 0s, 3s
        and 8s after the first tick, stopping early once the user picks a
        track themselves.
        """
        if self._media_attached or self._is_closing:
            return
        self._media_attached = True

        async def _with_retries():
            for delay in (0.0, 3.0, 8.0):
                if self._is_closing:
                    return
                if delay:
                    await asyncio.sleep(delay)
                    if self._is_closing:
                        return
                # The user picked something themselves — stop overriding.
                if self._subtitle_selection != "auto":
                    return
                await self._apply_default_subtitle(force=True)

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_with_retries()))
        except RuntimeError:
            pass

    def _maybe_save_position_periodically(self):
        """Throttled VOD-only checkpoint save (~every 10s). Android can kill
        the app mid-play — none of the close paths run then, so without
        periodic checkpoints the resume position is lost."""
        now = time.monotonic()
        if now - self._last_position_save < _POSITION_SAVE_INTERVAL:
            return
        self._last_position_save = now
        if (
            self._is_closing
            or not self.resume_key
            or self._last_duration <= 0
            or self._last_position <= 3
        ):
            return
        pos_sec = self._last_position
        if pos_sec >= (self._last_duration - 5):
            pos_sec = 0.0
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._persist_position(pos_sec, self._last_duration)
            )
            _keep(task)
        except RuntimeError:
            pass

    def _check_and_trigger_seek(self):
        # After media is ready / first tick, consume any pending one-shot
        # seek target — either the initial resume position or a position
        # captured before a quality/audio swap.
        target = getattr(self, "_pending_seek", None)
        if target is None:
            target = getattr(self, "_initial_resume_position", None)
        if target and target > 3:
            self._pending_seek = None
            self._initial_resume_position = None
            self._run_async(self._deferred_seek, target)

    async def _deferred_seek(self, seconds: float) -> None:
        try:
            # Poll readiness: mpv discards seek commands sent while the
            # demuxer is still opening network playlists / media tracks.
            for _ in range(40):  # up to 4.0s wait
                if self._is_closing or not self.video:
                    return
                try:
                    dur = await self.video.get_duration()
                    if dur and dur.in_seconds > 0:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)

            if self._is_closing or not self.video:
                return

            await asyncio.sleep(0.05)
            await self.video.seek(ft.Duration(seconds=int(seconds)))
            self._last_position = seconds
            logger.info("Deferred seek succeeded to %s seconds", seconds)
            self._toast_show(f"Resumed from {int(seconds) // 60}:{int(seconds) % 60:02d}")
        except Exception as ex:
            logger.debug("Deferred seek failed: %s", ex)

    def _hide_overlay(self):
        if not self._overlay_hidden:
            self._overlay_hidden = True
            self._cancel_watchdog()
            self.overlay.visible = False
            try:
                self.update()
            except Exception as ex:
                logger.debug(
                    "Failed to hide overlay (component might be unmounted): %s", ex
                )
            # First successful playback: probe the stream once for quality /
            # audio options so the buttons can appear.
            if not getattr(self, "_options_probed", False):
                self._options_probed = True
                try:
                    loop = asyncio.get_running_loop()
                    _keep(loop.create_task(self._probe_stream_options()))
                except RuntimeError:
                    pass

    def _enable_tap_to_close(self):
        # Same rule as _on_back: the outer close owns save + teardown + pop.
        def _tap(_):
            if self.on_close is None:
                return
            try:
                result = self.on_close()
                if hasattr(result, "__await__"):
                    page = self.safe_page or self._page()
                    if page is not None:
                        page.run_task(_await_result, result)
                    else:
                        _keep(asyncio.ensure_future(result))
            except Exception:
                logger.debug("Tap-to-close scheduling failed", exc_info=True)

        self.overlay.on_click = _tap

    def _safe_update(self):
        with contextlib.suppress(Exception):
            self.update()

    def _show_progress(self, message: str, show_back: bool = True):
        """Overlay state for loading/reconnecting: spinner + status, with Go
        Back always available (visible button + tap-to-close) so a stalling
        stream is never a dead end."""
        self._overlay_hidden = False
        self.status_text.value = message
        self.loading_ring.visible = True
        self.error_actions_row.visible = True
        self.retry_btn.visible = False
        self.back_error_btn.visible = show_back
        self.overlay.visible = True
        self._enable_tap_to_close()
        self._safe_update()

    # --- quality / audio switching (HLS via proxy) ----------------------

    def _resource_url_for(self, variant: int | None, audio: str | None) -> str:
        """Rebuild the playback URL for a (variant, audio) pinning choice."""
        if (
            self.hls_proxy
            and self.source_url
            and (variant is not None or audio is not None or self.source_proxied)
        ):
            try:
                return self.hls_proxy.get_proxy_url(
                    self.source_url,
                    referer=self.source_referer,
                    headers=self.source_headers,
                    variant=variant,
                    audio=audio,
                )
            except Exception:
                pass
        return self._original_resource

    @property
    def can_switch_quality(self) -> bool:
        return bool(self.hls_proxy) and self.source_url.startswith(
            ("http://", "https://")
        )

    async def list_variants(self) -> list[dict]:
        """HLS master variants (cached, but only SUCCESS is cached — an
        empty result used to be cached forever, which kept the quality chip
        hidden on phones where the first probe raced the proxy). Empty for
        media playlists/non-HLS."""
        if self._variants_cache is not None:
            return self._variants_cache
        if not self.can_switch_quality:
            return []
        try:
            variants = await asyncio.wait_for(
                self.hls_proxy.fetch_variants(
                    self.source_url,
                    headers=self.source_headers,
                    referer=self.source_referer,
                ),
                timeout=8.0,
            )
        except Exception:
            variants = []
        if variants:
            self._variants_cache = variants
        return variants

    async def list_audio_tracks(self) -> list[dict]:
        """External HLS audio renditions (cached on success only). Muxed
        audio is not switchable via manifest rewriting."""
        if self._audio_tracks_cache is not None:
            return self._audio_tracks_cache
        if not self.can_switch_quality:
            return []
        try:
            tracks = await asyncio.wait_for(
                self.hls_proxy.fetch_audio_tracks(
                    self.source_url,
                    headers=self.source_headers,
                    referer=self.source_referer,
                ),
                timeout=8.0,
            )
        except Exception:
            tracks = []
        if tracks:
            self._audio_tracks_cache = tracks
        return tracks

    async def _swap_media(self, message: str) -> None:
        """Restart playback on the currently pinned resource, restoring the
        position for seekable streams."""
        if self._is_closing or not self.video:
            return
        new_url = self._resource_url_for(self._current_variant, self._current_audio)
        position = None
        duration = None
        try:
            pos_task = asyncio.create_task(self.video.get_current_position())
            position = await asyncio.wait_for(pos_task, timeout=0.8)
        except Exception:
            pass
        try:
            dur_task = asyncio.create_task(self.video.get_duration())
            duration = await asyncio.wait_for(dur_task, timeout=0.8)
        except Exception:
            pass

        pos_sec = (
            position.in_seconds
            if (position and position.in_seconds > 0)
            else self._last_position
        )
        dur_sec = (
            duration.in_seconds
            if (duration and duration.in_seconds > 0)
            else self._last_duration
        )
        if dur_sec > 0:
            self._last_duration = dur_sec

        self.resource = new_url
        self._show_progress(message)
        # Restore position for finite streams (VOD duration > 0)
        if dur_sec > 0 and pos_sec > 3:
            self._pending_seek = pos_sec
        # The new media needs its subtitle track applied again.
        self._media_attached = False
        self._subtitle_applied = False

        try:
            self.video.playlist = [
                fv.VideoMedia(new_url, http_headers=self.http_headers),
            ]
            self.video.update()
            await self.video.play()
            self._start_watchdog()
        except Exception as ex:
            logger.error("Stream switch failed: %s", ex)
            self._show_final_error("Switch failed. Stream may be offline.")

    async def apply_variant(self, index: int | None) -> None:
        """Pin a quality variant (None = Auto)."""
        self._current_variant = index
        self._refresh_quality_label()
        await self._swap_media(
            "Auto quality" if index is None else "Switching quality..."
        )

    async def apply_audio(self, name: str | None) -> None:
        """Pin an audio rendition (None = manifest default)."""
        self._current_audio = name
        self._refresh_audio_label()
        await self._swap_media(
            "Default audio" if name is None else "Switching audio..."
        )

    def _refresh_quality_label(self) -> None:
        """Sync the quality button with the current pinning. There is NO
        "Auto": when nothing is pinned the stream's TOP rendition names the
        label (the owner's rule — the chip always names a concrete quality)."""
        text = getattr(self, "quality_text", None)
        btn = getattr(self, "quality_btn", None)
        if not text or not btn:
            return
        if self._current_variant is None:
            top = max(
                (self._variants_cache or []),
                key=lambda v: v.get("bandwidth") or 0,
                default=None,
            )
            text.value = _short_variant_label(top) if top else "—"
        else:
            current = next(
                (
                    v
                    for v in (self._variants_cache or [])
                    if v.get("index") == self._current_variant
                ),
                None,
            )
            text.value = (
                _short_variant_label(current)
                if current
                else f"V{self._current_variant + 1}"
            )
        with contextlib.suppress(Exception):
            btn.update()

    def _refresh_audio_label(self) -> None:
        text = getattr(self, "audio_text", None)
        btn = getattr(self, "audio_btn", None)
        if not text or not btn:
            return
        if self._current_audio is None:
            text.value = "Default"
        else:
            text.value = self._current_audio
        with contextlib.suppress(Exception):
            btn.update()

    async def _probe_stream_options(self) -> None:
        """Fetch variants/audio once playback is running; reveal the quality
        and audio buttons. The quality button reveals for ANY master (the
        chip always names a concrete quality — no "Auto"); audio needs two
        selectable renditions.

        Retried: on the phone the first probe raced the proxy (it was busy
        feeding mpv) and an empty result used to be cached forever — the
        chip then never appeared without opening Settings."""
        if not self.can_switch_quality or self._is_closing:
            return
        variants: list[dict] = []
        tracks: list[dict] = []
        for _ in range(3):
            variants = await self.list_variants()
            if variants or self._is_closing:
                break
            await asyncio.sleep(4.0)
        if self._is_closing:
            return
        if variants:
            tracks = await self.list_audio_tracks()

        q_btn = getattr(self, "quality_btn", None)
        q_row = getattr(self, "quality_row", None)
        if q_btn is not None and q_row is not None and len(variants) >= 1:
            q_btn.content = q_row
            q_btn.padding = ft.Padding(6, 3, 6, 3)
            self._refresh_quality_label()
            with contextlib.suppress(Exception):
                q_btn.update()

        a_btn = getattr(self, "audio_btn", None)
        a_row = getattr(self, "audio_row", None)
        if a_btn is not None and a_row is not None and len(tracks) >= 2:
            a_btn.content = a_row
            a_btn.padding = ft.Padding(6, 3, 6, 3)
            self._refresh_audio_label()
            with contextlib.suppress(Exception):
                a_btn.update()

    async def open_player_settings(self) -> None:
        from components.player.handlers import open_player_settings

        await open_player_settings(self)

    async def open_subtitles(self) -> None:
        from components.player.handlers import pick_subtitles

        await pick_subtitles(self)

    # --- watchdog -------------------------------------------------------

    def _start_watchdog(self, timeout: float | None = None):
        """Guarantee every loading/reconnecting state resolves: if no load,
        position or error event arrives within `timeout`, swap the spinner
        for the retry/back UI instead of spinning forever."""
        self._cancel_watchdog()
        secs = _WATCHDOG_SECONDS if timeout is None else timeout

        async def _watchdog():
            await asyncio.sleep(secs)
            if self._is_closing or self._is_final_error or self._overlay_hidden:
                return
            logger.warning(
                "Playback watchdog fired after %.1fs — no load/position/error",
                secs,
            )
            self._show_final_error("Stream is not responding. Retry or go back.")

        try:
            loop = asyncio.get_running_loop()
            self._watchdog_task = loop.create_task(_watchdog())
        except RuntimeError:
            pass

    def _cancel_watchdog(self):
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self._watchdog_task = None

    def _start_checkpoints(self):
        if self._checkpoint_task is not None:
            return

        async def _checkpoint_loop():
            while not self._is_closing:
                await asyncio.sleep(_POSITION_SAVE_INTERVAL)
                self._maybe_save_position_periodically()

        try:
            loop = asyncio.get_running_loop()
            self._checkpoint_task = loop.create_task(_checkpoint_loop())
        except RuntimeError:
            pass

    def _cancel_checkpoints(self):
        if self._checkpoint_task and not self._checkpoint_task.done():
            self._checkpoint_task.cancel()
        self._checkpoint_task = None

    # --- error handling & retry ------------------------------------------

    def _on_error(self, e: ft.ControlEvent):
        err_msg = str(e.data) if hasattr(e, "data") and e.data else str(e)
        logger.debug("on_error: %s", err_msg)
        if self._is_closing:
            return
        if "Cannot seek" in err_msg or "force-seekable" in err_msg:
            return
        if self._is_final_error:
            return

        self._show_final_error(
            "Unable to load stream. Please check connection or retry."
        )

    def _show_final_error(self, message: str = "Playback failed."):
        self._cancel_watchdog()
        self._is_final_error = True
        self._overlay_hidden = False
        self.status_text.value = message
        self.loading_ring.visible = False
        self.error_actions_row.visible = True
        self.retry_btn.visible = True
        self.back_error_btn.visible = True
        self.overlay.visible = True
        self._enable_tap_to_close()
        self._safe_update()

    # --- position persistence ---------------------------------------------

    async def _persist_position(self, pos_sec: float, dur_sec: float) -> None:
        """VOD-only position save through the store."""
        if not self.store or not self.resume_key:
            return
        if dur_sec > 0 and pos_sec > 3:
            if pos_sec >= (dur_sec - 5):
                pos_sec = 0.0
            try:
                await self.store.save_position(
                    self.resume_key,
                    pos_sec,
                    dur_sec,
                    rate=SPEEDS[self._speed_idx],
                )
                self._position_saved = True
                logger.info(
                    "position saved (%.1fs of %.1fs)", pos_sec, dur_sec
                )
            except Exception as ex:
                logger.debug("Saving playback position failed: %s", ex)

    async def save_position_now(self) -> None:
        """Capture and save the playback position on player close (awaited
        by the shell's close funnel before teardown)."""
        try:
            if not self.video or not self.resume_key:
                return
            pos = None
            dur = None
            try:
                pos = await asyncio.wait_for(
                    asyncio.create_task(self.video.get_current_position()),
                    timeout=0.8,
                )
            except Exception:
                pos = None
            try:
                dur = await asyncio.wait_for(
                    asyncio.create_task(self.video.get_duration()), timeout=0.8
                )
            except Exception:
                dur = None

            pos_sec = pos.in_seconds if pos else self._last_position
            dur_sec = dur.in_seconds if dur else self._last_duration
            await self._persist_position(pos_sec, dur_sec)
        except Exception as ex:
            logger.debug("Saving playback position failed: %s", ex)

    def teardown(self):
        """Sync final cleanup — safe to call from the close funnel after the
        awaited save. Exits native fullscreen FIRST (a popped view under an
        open fullscreen route corrupts the engine's view stack —
        'FlutterEngineRemoveView kInvalidArguments' then a Dart RangeError
        on the next rebuild), then clears the playlist so native playback
        halts immediately."""
        self._cancel_watchdog()
        self._cancel_checkpoints()
        if self.video:
            self._is_closing = True
            try:
                if self.video.fullscreen:
                    self.video.fullscreen = False
            except Exception:
                logger.debug("suppressed")
            try:
                self.video.playlist = []
                self.video.update()
            except Exception:
                pass

    def _on_complete(self, e: ft.ControlEvent | None = None):
        # flet_video notifies `complete` the moment a fresh playlist is
        # attached and mpv has nothing decoded yet. A real completion always
        # follows real playback.
        if not self._playback_started:
            logger.debug("Ignoring complete notification before playback started")
            return
        # Auto-advance at a real ending (owner's rule: duration must be known
        # and the position within 5s of the end).
        if self._last_duration > 0 and self._last_position >= self._last_duration - 5:
            if self.on_next is not None:
                self.on_next()
            return
        from components.player.handlers import handle_stream_complete

        handle_stream_complete(self, e)

    # --- close ------------------------------------------------------------

    async def handle_close(self, e: ft.ControlEvent | None = None):
        if self._is_closing:
            return
        self._is_closing = True
        self._is_final_error = True
        self._cancel_watchdog()
        await self.save_position_now()
        try:
            if self.video:
                with contextlib.suppress(Exception):
                    await self.video.stop()
                self.video.playlist = []
                self.video.update()
        except Exception as ex:
            logger.debug("Ignored error while stopping video on close: %s", ex)

    async def _on_back(self, e: ft.ControlEvent | None = None):
        # Route through on_close ONLY. The outer close funnel owns the save,
        # teardown and pop in one pass — calling handle_close() here first
        # latches _is_closing and strands the user on a dead player.
        if self.on_close:
            try:
                result = self.on_close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as ex:
                logger.error("Error executing on_close callback: %s", ex)

    def _build_controls(self) -> fv.AdaptiveVideoControls:
        from components.player.controls import build_player_controls

        return build_player_controls(self)

    # --- snapshot -----------------------------------------------------------

    async def _take_screenshot(self):
        try:
            from core.notify import show_snack

            page = self._page()
            # The confirmation rides the RESULT — announcing before the
            # await claimed success the frame may never produce.
            shot = await asyncio.wait_for(self.video.take_screenshot(), timeout=5.0)
            if shot is None:
                if page is not None:
                    show_snack(page, "Screenshot unavailable", bgcolor=AppColors.PRIMARY)
                self._toast_show("Screenshot unavailable")
                return
            directory = None
            try:
                directory = await self._snapshot_directory()
            except Exception:
                directory = None
            from core.snapshots import save_snapshot

            path = await asyncio.to_thread(save_snapshot, shot, directory)
            logger.info("snapshot saved: %s", path)
            if page is not None:
                show_snack(
                    page,
                    f"Saved {os.path.basename(path)}",
                    bgcolor=AppColors.PRIMARY,
                )
            self._toast_show(f"Saved {os.path.basename(path)}")
        except Exception as ex:
            logger.info("snapshot failed: %s", ex)
            self._toast_show("Screenshot failed")

    async def _snapshot_directory(self) -> str | None:
        """Where snapshots land. None routes the save into the app's data
        tier (core.snapshots decides); tests override this."""
        return None

    # --- presentation settings (persisted) ---------------------------------

    SUBTITLE_SIZES: ClassVar[list[int]] = [12, 16, 22, 30]

    def _subtitle_size(self) -> int:
        if self.store is None:
            return 16
        try:
            size = int(self.store.get_setting("subtitle_size", 16))
        except Exception:
            size = 16
        return size if size in self.SUBTITLE_SIZES else 16

    def set_subtitle_size(self, size: int) -> None:
        if self.store is None or size not in self.SUBTITLE_SIZES:
            return

        async def _save():
            await self.store.save_setting("subtitle_size", size)
            try:
                self.video.subtitle_configuration.text_style.size = float(size)
                self.video.update()
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_save()))
        except RuntimeError:
            pass

    def _box_fit(self) -> ft.BoxFit:
        if self.store is None:
            return ft.BoxFit.CONTAIN
        try:
            name = str(self.store.get_setting("video_fit", "contain") or "contain")
        except Exception:
            name = "contain"
        return _BOX_FITS.get(name, ft.BoxFit.CONTAIN)

    def set_fit(self, name: str) -> None:
        if self.store is None or name not in _BOX_FITS:
            return
        self.video.fit = _BOX_FITS[name]

        async def _save():
            await self.store.save_setting("video_fit", name)
            with contextlib.suppress(Exception):
                self.video.update()

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_save()))
        except RuntimeError:
            pass

    # --- fullscreen toast -----------------------------------------------------

    def _toast_show(self, message: str) -> None:
        chip = getattr(self, "toast_chip", None)
        text = getattr(self, "toast_text", None)
        if chip is None or text is None:
            return
        text.value = message
        chip.visible = True
        try:
            chip.update()
        except Exception:
            logger.debug("suppressed")
        # Generation counter: an older _hide task used to fire early and
        # hide a toast that had just been replaced.
        self._toast_gen = getattr(self, "_toast_gen", 0) + 1
        gen = self._toast_gen

        async def _hide():
            await asyncio.sleep(2.0)
            if self._is_closing or gen != self._toast_gen:
                return
            chip.visible = False
            try:
                chip.update()
            except Exception:
                logger.debug("suppressed")

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_hide()))
        except RuntimeError:
            pass

    def _on_enter_fullscreen(self, e=None):
        try:
            from core.notify import set_fullscreen_toast_active

            set_fullscreen_toast_active(True)
        except Exception:
            pass

    def _on_exit_fullscreen(self, e=None):
        try:
            from core.notify import set_fullscreen_toast_active

            set_fullscreen_toast_active(False)
        except Exception:
            pass

    # --- skip intro / skip outro ------------------------------------------------

    @staticmethod
    def _window(pair) -> tuple[float, float] | None:
        """Accepts {'start','end'} objects or [start, end] arrays — the
        two shapes sources serve. Returns (start, end) or None."""
        if isinstance(pair, dict):
            try:
                return (float(pair["start"]), float(pair["end"]))
            except (KeyError, TypeError, ValueError):
                return None
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            try:
                return (float(pair[0]), float(pair[1]))
            except (TypeError, ValueError):
                return None
        return None

    def _active_window(self, seconds: float):
        """The skip window the position is inside, or None."""
        intro = self._window(self.skip.get("intro"))
        if intro and intro[0] < seconds < intro[1] - 1:
            return intro
        outro = self._window(self.skip.get("outro"))
        if outro and outro[0] < seconds < outro[1] - 1:
            return outro
        # Per-episode arrays are the fallback shape (anikato's
        # ajax/server skip_data) when getSources served nothing.
        ep_intro = self._window(self.skip.get("episode_intro"))
        if ep_intro and ep_intro[0] < seconds < ep_intro[1] - 1:
            return ep_intro
        ep_outro = self._window(self.skip.get("episode_outro"))
        if ep_outro and ep_outro[0] < seconds < ep_outro[1] - 1:
            return ep_outro
        return None

    def _is_intro_window(self, window) -> bool:
        """Intro vs outro for a window — shared by the chip label and the
        skip confirmation so the two can never disagree."""
        if not window:
            return False
        return window == self._window(self.skip.get("intro")) or window == self._window(
            self.skip.get("episode_intro")
        )

    def _update_skip_chip(self, seconds: float) -> None:
        chip = getattr(self, "skip_chip", None)
        if chip is None:
            return
        window = self._active_window(seconds)
        is_intro = self._is_intro_window(window)
        visible = window is not None
        label = "Skip Intro" if is_intro else "Skip Outro"
        changed = visible != chip.visible or (
            visible and chip.content.value != label
        )
        if not changed:
            return
        chip.visible = visible
        chip.content.value = label
        try:
            chip.update()
        except Exception:
            logger.debug("suppressed")

    async def _on_skip_chip(self, e=None):
        window = self._active_window(self._last_position)
        if not window:
            return
        _start, end = window
        # Land 1s past the window so the chip does not re-flash.
        # ft.DurationValue: a bare int is MILLISECONDS in flet-video, so
        # the raw-seconds seek jumped to ~1ms instead of ~1s.
        try:
            await self.video.seek(ft.Duration(seconds=end + 1))
        except Exception as ex:
            logger.warning("skip seek failed: %s", ex)
            return
        what = "intro" if self._is_intro_window(window) else "outro"
        self._toast_show(f"Skipped {what}")

    # --- subtitles -----------------------------------------------------------

    async def _subtitle_src(self, entry: dict) -> str:
        """The best `VideoSubtitleTrack.src` for a subtitle entry.

        - A local sidecar path (downloads) is used as-is: mpv reads local
          files, no network, no headers.
        - A remote URL is fetched to RAW TEXT through the proxy when one is
          wired — raw text is a documented `src` form and removes mpv's own
          fetcher (and its missing CDN headers) from the equation entirely;
          on the phone that fetch was failing silently. Falls back to the
          URL itself.
        """
        url = entry.get("url") or ""
        if not url.startswith(("http://", "https://")):
            return url  # local sidecar path
        if self.hls_proxy is not None:
            try:
                _ct, text = await asyncio.wait_for(
                    self.hls_proxy.fetch_master(
                        url,
                        headers=self.source_headers or None,
                        referer=self.source_referer,
                    ),
                    timeout=8.0,
                )
                if text and text.strip():
                    return text
            except Exception as ex:
                logger.debug("subtitle fetch fell back to URL: %s", ex)
        return url

    def _apply_track(self, src: str, title: str | None = None) -> None:
        try:
            self.video.subtitle_track = fv.VideoSubtitleTrack(src=src, title=title)
            self.video.update()
        except Exception as ex:
            logger.warning("subtitle switch failed: %s", ex)

    async def _apply_default_subtitle(self, force: bool = False) -> None:
        """The source's own default track (anikato marks English) applies
        automatically once the media is attached. `force=True` lets the
        retry schedule re-run it (a fresh fetch through a then-idle proxy)
        without counting as a user selection."""
        if not force and self._subtitle_applied:
            return
        if not self.subtitles or self._is_closing:
            return
        if self._subtitle_selection not in ("auto", None):
            return
        self._subtitle_applied = True
        for track in self.subtitles:
            if track.get("default"):
                src = await self._subtitle_src(track)
                if self._is_closing:
                    return
                self._apply_track(src, track.get("label"))
                return

    def apply_subtitle(self, index: int | None) -> None:
        """Off (None) clears the track; an index applies that source track."""
        self._subtitle_selection = index
        if index is None:
            self._apply_track("none")
            return

        async def _apply():
            if index < 0 or index >= len(self.subtitles):
                return
            track = self.subtitles[index]
            src = await self._subtitle_src(track)
            self._apply_track(src, track.get("label"))

        try:
            loop = asyncio.get_running_loop()
            _keep(loop.create_task(_apply()))
        except RuntimeError:
            pass

    def apply_local_subtitle(self) -> None:
        """The loaded file's own text becomes the track. flet-video accepts
        raw SRT/VTT text as src — no host, no headers, works everywhere."""
        local = self._local_subtitle
        if not local:
            return
        self._subtitle_selection = "local"
        self._apply_track(local["text"], local["name"])

    async def _pick_subtitle_file(self, e=None) -> None:
        """Pick an .srt/.vtt from the device and apply it. Every failure
        mode is an honest snack, never a crash: no picker service (dev/web
        quirks), cancel, unreadable bytes."""
        from core.notify import show_snack

        page = self._page()
        if page is None:
            return
        try:
            from core.shared_services import get_shared_services

            picker = get_shared_services(page).file_picker
            files = await picker.pick_files(
                dialog_title="Choose a subtitle file",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["srt", "vtt"],
                with_data=True,
            )
        except Exception as ex:
            logger.info("subtitle picker unavailable: %s", ex)
            show_snack(page, "File picker unavailable", bgcolor=AppColors.PRIMARY)
            return
        if not files:
            return  # the user cancelled
        picked = files[0]
        raw = getattr(picked, "bytes", None)
        text = raw.decode("utf-8", errors="replace") if raw else ""
        if not text.strip():
            show_snack(page, "Could not read that file", bgcolor=AppColors.PRIMARY)
            return
        self._local_subtitle = {
            "name": getattr(picked, "name", "") or "Local subtitle",
            "text": text,
        }
        self.apply_local_subtitle()
        show_snack(
            page,
            f"Subtitles: {self._local_subtitle['name']}",
            bgcolor=AppColors.PRIMARY,
        )
        self._toast_show(f"Subtitles: {self._local_subtitle['name']}")

    def handle_key(self, e) -> bool:
        """Window-level key handling (registered by the shell for the life
        of the player view). Returns True when the key was consumed."""
        key = getattr(e, "key", None) or ""
        if key == "s" and getattr(self, "skip_chip", None) and self.skip_chip.visible:
            self._run_async(self._on_skip_chip)
            return True
        if key in ("]", "n") and self.on_next is not None:
            self.on_next()
            return True
        if key in ("[", "p") and self.on_previous is not None:
            self.on_previous()
            return True
        return False
