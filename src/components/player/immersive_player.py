"""ImmersivePlayer — the in-app episode player.

Ported from KTV's player, keeping the portable skeleton and dropping
everything KTV-specific (no HLS proxy, live channels, favorites, PiP,
snapshots, YouTube resolver). flet 1.0.4: opened by a branch on
``active_view`` rather than a ``/play`` view.

The design decisions that matter, all learned from KTV:
- ``network-timeout: 10`` in the mpv properties — the stock 60s default is
  what makes a dead host hang on the spinner for a minute.
- ``filter_quality=MEDIUM`` — HIGH blurs on Android.
- Adaptive controls with FRESH instances per branch: sharing one button
  instance across the touch and TV control trees double-mounts it.
- The toast chip lives INSIDE ``video.controls`` — media_kit pushes its
  fullscreen route above the whole Flet page, so anything placed next to
  the Video in a Stack is covered in fullscreen and that chip is not.
- Overlay hides on three independent signals (on_load, first positive
  duration tick, first positive position tick) plus a 20s watchdog;
  Go Back is reachable from the very first frame — the player is never a
  dead end.
- Resume seeks are deferred and polled: mpv discards seeks sent while the
  demuxer is still opening, which silently breaks naive resume.
"""

import asyncio
import contextlib
import logging
import os
import re
from typing import ClassVar

import flet as ft
import flet_video as fv

from components.guarded_controls import (
    GuardedContainer,
    GuardedIconButton,
    GuardedOutlinedButton,
    GuardedTextButton,
)
from core.snapshots import save_snapshot
from core.theme import AppColors

logger = logging.getLogger(__name__)

WATCHDOG_SECONDS = 20.0
DEFER_SEEK_POLL_SECONDS = 4.0
POSITION_CHECKPOINT_SECONDS = 10.0

# The browser identity the kwik family expects — ONE constant, shared
# with the kwik FILE resolver (core/constants.py): a Cloudflare
# clearance is bound to the user agent that earned it, so the two must
# never drift.
from core.constants import KWIK_USER_AGENT

__all__ = ["KWIK_USER_AGENT"]
# Playback speeds for the chip, index 2 is normal.
def _mpv_props(referer: str) -> dict:
    """mpv tuning for network media. The source's own referer rides
    http-header-fields so segment requests carry it even when a source
    is fetched directly (no proxy in the path)."""
    return {
        "http-header-fields": f"Referer: {referer}",
        "cache": "yes",
        "cache-secs": 5,
        "demuxer-max-bytes": "50M",
        "demuxer-max-back-bytes": "10M",
        "framedrop": "vo",
        "hr-seek-framedrop": "yes",
        # mpv's default 60s network timeout means a dead host spins this
        # spinner for a minute. 10s makes failure deterministic.
        "network-timeout": 10,
    }


SPEEDS = (0.25, 0.5, 1.0, 1.25, 1.5, 2.0)

# Aspect-fit choices (name, label) — persisted by name, so the map below
# is the only place a name meets a BoxFit.
FIT_OPTIONS = (("contain", "Contain"), ("cover", "Cover"), ("fill", "Fill"))

_BOX_FITS = {
    "contain": ft.BoxFit.CONTAIN,
    "cover": ft.BoxFit.COVER,
    "fill": ft.BoxFit.FILL,
}


def _stream_variants(m3u8_text: str, playlist_url: str | None = None) -> list[dict]:
    """Parse an HLS master playlist into variants.

    Returns [] for a media playlist (single quality) or anything
    malformed — the caller then hides the quality chip entirely.

    Relative variant URIs resolve against ``playlist_url`` (the master's
    own address). The old code used the FIRST media line as the base, so
    every relative variant collapsed onto one URI — pinning any quality
    replayed the same rendition.
    """
    if not m3u8_text or "#EXT-X-STREAM-INF" not in m3u8_text:
        return []
    lines = m3u8_text.splitlines()

    def _resolve(line: str) -> str:
        if line.startswith("http") or not playlist_url:
            return line
        base = playlist_url.rsplit("/", 1)[0]
        return f"{base}/{line}"

    variants = []
    pending: dict = {}
    for line in lines:
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            pending = {}
            res = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            if res:
                pending["width"] = int(res.group(1))
                pending["height"] = int(res.group(2))
            if bw:
                pending["bandwidth"] = int(bw.group(1))
        elif pending and line and not line.startswith("#"):
            uri = _resolve(line)
            entry = dict(pending)
            entry["uri"] = uri
            label = (
                f"{entry.get('height', 0)}p"
                if entry.get("height")
                else f"{entry.get('bandwidth', 0) // 1000}kbps"
            )
            entry["label"] = label
            variants.append(entry)
            pending = {}
    return variants


class ImmersivePlayer(ft.Stack):
    """A Stack: black container, video, loading/error overlay.

    Ported from the house player (KTV) with its playback core: the resource
    is a LOOPBACK PROXY url (services/hls_proxy.py) that injects the
    UA + Referer the stream hosts require and rewrites the playlist, and
    ``source_url``/``source_referer``/``source_headers`` let the player
    rebuild that url when the viewer pins a quality variant or an audio
    rendition. flet-video gets ``http_headers`` too — the local socket
    doesn't care, but the direct-URL fallback path does.
    """

    def __init__(
        self,
        resource: str,
        title: str = "",
        http_headers: dict | None = None,
        resume_key: str | None = None,
        store=None,
        autoplay: bool = True,
        on_close=None,
        on_next=None,
        on_previous=None,
        variants: list[dict] | None = None,
        source_url: str | None = None,
        source_referer: str | None = None,
        source_headers: dict | None = None,
        proxied: bool = False,
        subtitles: list | None = None,
        skip: dict | None = None,
        variant_index: int | None = None,
    ):
        super().__init__(expand=True)
        self.resource = resource
        self.title = title
        self.http_headers = http_headers or {}
        self.resume_key = resume_key
        self.store = store
        self.variants = variants or []
        self.on_close = on_close
        self.on_next = on_next
        self.on_previous = on_previous
        # Source identity for quality/audio pinning (None for local files).
        self.source_url = source_url or resource
        self.source_referer = source_referer
        self.source_headers = source_headers or {}
        self.proxied = proxied
        # Subtitle tracks + skip windows exactly as the source served them
        # (anikato carries both; animepahe carries neither — hardsubs).
        self.subtitles = subtitles or []
        self.skip = skip or {}
        # A subtitle file the user loaded from the device ({name, text});
        # its raw text rides fv.VideoSubtitleTrack directly — no host, no
        # headers, every backend.
        self._local_subtitle: dict | None = None
        self._subtitle_applied = False
        # One Stream Settings sheet at a time (the chips re-spawn it).
        self._settings_open = False
        self.hls_proxy = None  # set by the shell mount; see _use_player_overlay
        # Pre-selected variant index (from quality picker)
        self._current_variant = variant_index

        # Skip-intro/outro chip and toast chip - created here so they exist
        # when _build_controls() is called (which happens during _build()).
        # They live INSIDE video.controls (in the top_button_bar Stack with
        # the title), like ktv-player, to avoid the "positioned absolutely
        # inside Stack only" error.
        self.skip_chip = GuardedContainer(
            content=ft.Text(
                "Skip Intro",
                size=13,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.WHITE,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.75, ft.Colors.BLACK),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, ft.Colors.WHITE)),
            visible=False,
            on_click=self._on_skip_chip,
        )
        # Fullscreen toast: native fullscreen swallows the snackbar, so
        # confirmations (resume/speed/skip) also land here and dispatch
        # through core.notify's registry.
        self.toast_chip = ft.Container(
            content=ft.Text("", size=13, weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.75, ft.Colors.BLACK),
            visible=False,
        )

        self._is_closing = False
        self._is_final_error = False
        self._overlay_hidden = False
        self._position_saved = False
        self._current_variant = None
        self._current_audio = None
        self._variants_cache: list[dict] | None = None
        self._audio_cache: list[dict] | None = None
        self._reconnect_count = 0

        self._initial_resume_position: float | None = None
        self._pending_seek: float | None = None
        self._last_position = 0.0
        self._last_duration = 0.0
        self._watchdog_task: asyncio.Task | None = None
        self._checkpoint_task: asyncio.Task | None = None
        self._speed_index = SPEEDS.index(1.0)
        self._speed_rate = 1.0

        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self):
        self.loading_ring = ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4)
        self.status_text = ft.Text("Loading stream...", size=14, color=ft.Colors.WHITE)
        # Guarded buttons (GuardedOutlinedButton): this error card is
        # mounted into page.overlay and REPLACED by key when the user
        # retries, so the very button being pressed is unmounted. A tap
        # that arrives after that was dispatched to a control whose
        # parent chain no longer reaches a Page, which flet reports as a
        # SESSION_CRASHED — the owner's live-APK crash. Cancelling the
        # event in before_event turns it into a harmless no-op.
        self.retry_btn = GuardedOutlinedButton(
            content="Retry",
            icon=ft.Icons.REFRESH_ROUNDED,
            visible=False,
            on_click=lambda e: self._manual_retry(),
        )
        self.back_error_btn = GuardedOutlinedButton(
            content="Go Back",
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: self._on_back(),
        )
        self.error_actions_row = ft.Row(
            [self.retry_btn, self.back_error_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
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

        self.video = fv.Video(
            autoplay=True,
            expand=True,
            wakelock=True,
            filter_quality=ft.FilterQuality.MEDIUM,
            pause_upon_entering_background_mode=True,
            resume_upon_entering_foreground_mode=False,
            playlist_mode=fv.PlaylistMode.NONE,
            fill_color=ft.Colors.BLACK,
            fit=self._box_fit(),
            title=self.title or "AnimePahe",
            controls=self._build_controls(),
            subtitle_configuration=fv.VideoSubtitleConfiguration(
                text_style=ft.TextStyle(
                    size=self._subtitle_size(),
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.W_600,
                    bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                ),
                text_align=ft.TextAlign.CENTER,
                visible=True,
            ),
            configuration=fv.VideoConfiguration(
                enable_hardware_acceleration=True,
                mpv_properties=_mpv_props(self.source_referer or "https://kwik.cx/"),
            ),
            on_load=self._on_first_ready,
            on_duration_change=self._on_duration_change,
            on_position_change=self._on_pos_change,
            on_error=self._on_error,
            on_complete=self._on_complete,
        )

        self.controls = [
            ft.Container(expand=True, bgcolor=ft.Colors.BLACK),
            self.video,
            self.overlay,
        ]

    def _build_controls(self) -> fv.AdaptiveVideoControls:
        """Fresh control instances per branch — sharing across the touch and
        desktop/TV trees double-mounts them."""
        from core.tasks import spawn

        # Chips render their label immediately; the stream probe refreshes
        # the text (and is the only thing that reveals them). Every list
        # accumulates across BOTH control branches (touch + desktop): _bar()
        # runs once per branch, and an assignment would let the second
        # branch clobber the first, leaving one platform's chips stale.
        self.quality_texts = []
        self.audio_texts = []
        self.quality_chips = []
        self.audio_chips = []
        self.speed_texts = []

        def _open_settings(e=None):
            spawn(self.open_stream_settings(), name="player-settings")

        def _bar(desktop: bool) -> list:
            items = [
                fv.VideoSpacer(),
                fv.VideoPositionIndicator(),
                fv.VideoSpacer(),
            ]
            # Quality chip: hidden until the probe proves the stream has
            # variants — an empty picker is worse than no chip.
            quality_text = ft.Text("Auto", size=12)
            self.quality_texts.append(quality_text)
            quality_chip = GuardedContainer(
                content=quality_text,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=6,
                ink=True,
                tooltip="Stream quality",
                on_click=_open_settings,
                visible=False,
            )
            self.quality_chips.append(quality_chip)
            items.append(quality_chip)

            audio_text = ft.Text("Audio", size=12)
            self.audio_texts.append(audio_text)
            audio_chip = GuardedContainer(
                content=audio_text,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=6,
                ink=True,
                tooltip="Audio track",
                on_click=_open_settings,
                visible=False,
            )
            self.audio_chips.append(audio_chip)
            items.append(audio_chip)

            speed_text = ft.Text("1.0x", size=12)
            self.speed_texts.append(speed_text)
            items.append(
                GuardedContainer(
                    content=speed_text,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=6,
                    ink=True,
                    tooltip="Playback speed",
                    on_click=self._cycle_speed,
                )
            )
            items.append(
                GuardedIconButton(
                    icon=ft.Icons.PHOTO_CAMERA_ROUNDED,
                    icon_size=16,
                    tooltip="Screenshot",
                    on_click=lambda e: spawn(self._take_snapshot(), name="snapshot"),
                )
            )
            # Subtitle file: this bar is the ONE always-reachable settings
            # surface (the quality/audio chips hide when a stream has no
            # options), so loading a local subtitle hangs here too.
            items.append(
                GuardedIconButton(
                    icon=ft.Icons.CLOSED_CAPTION_OUTLINED,
                    icon_size=16,
                    tooltip="Subtitle file",
                    on_click=lambda e: spawn(self._pick_subtitle_file(), name="pick-subtitle"),
                )
            )
            # VideoSkipNext/PreviousButton are value objects without event
            # handlers — real IconButtons are the supported way to add
            # custom skip behaviour inside the bar. Both are Guarded: the
            # shell replaces this whole player when the episode changes,
            # so a queued tap would reach a control with no page.
            if self.on_previous is not None:
                items.append(
                    GuardedIconButton(
                        icon=ft.Icons.SKIP_PREVIOUS_ROUNDED,
                        icon_size=24,
                        tooltip="Previous episode",
                        on_click=lambda e: self.on_previous(),
                    )
                )
            if self.on_next is not None:
                items.append(
                    GuardedIconButton(
                        icon=ft.Icons.SKIP_NEXT_ROUNDED,
                        icon_size=24,
                        tooltip="Next episode",
                        on_click=lambda e: self.on_next(),
                    )
                )
            items.append(fv.VideoFullscreenButton(icon_size=24))
            return items

        # Shared across both control branches, so it must be guarded ONCE:
        # a Back press unmounts the control that was pressed.
        # Include skip_chip and toast_chip in a Stack with the title (like ktv-player)
        # so they're in a proper Stack context for absolute positioning.
        title_text = ft.Text(self.title, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        title_slot = ft.Stack(
            controls=[title_text, self.skip_chip, self.toast_chip],
            alignment=ft.Alignment.CENTER,
        )
        top_bar = [
            GuardedIconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                on_click=lambda e: self._on_back(),
                tooltip="Back",
            ),
            title_slot,
        ]

        return fv.AdaptiveVideoControls(
            material=fv.MaterialVideoControls(
                visible_on_mount=True,
                display_seek_bar=True,
                seek_on_double_tap=True,
                seek_gesture=True,
                volume_gesture=True,
                brightness_gesture=True,
                speed_up_on_long_press=True,
                primary_button_bar=[
                    fv.VideoSpacer(flex=2),
                    fv.VideoPlayOrPauseButton(icon_size=48.0),
                    fv.VideoSpacer(flex=2),
                ],
                top_button_bar=top_bar,
                bottom_button_bar=_bar(desktop=False),
            ),
            material_desktop=fv.MaterialDesktopVideoControls(
                visible_on_mount=True,
                display_seek_bar=True,
                modify_volume_on_scroll=True,
                primary_button_bar=[
                    fv.VideoSpacer(flex=2),
                    fv.VideoPlayOrPauseButton(icon_size=32.0),
                    fv.VideoSpacer(flex=2),
                ],
                top_button_bar=top_bar,
                bottom_button_bar=_bar(desktop=True),
                controls_hover_duration=ft.Duration(seconds=4),
            ),
        )

    # ------------------------------------------------------------------
    # Lifecycle (Flet service hooks)
    # ------------------------------------------------------------------

    def init(self):
        pass

    def did_mount(self):
        from core.tasks import spawn

        # Mount, not first-ready: the registry must be live before any
        # confirmation can fire (speed cycles before the first frame is
        # not decoded), and unregistering at mount's mirror (will_unmount)
        # covers the overlay-removal race that never reaches handle_close.
        try:
            from core.notify import register_fullscreen_toast

            register_fullscreen_toast(self._toast_show)
        except Exception:
            pass
        self._read_resume_position()
        spawn(self._start_playback(), name="player-start")

    def _read_resume_position(self):
        if not self.store or not self.resume_key:
            return

        async def _read():
            entry = await self.store.get_position(self.resume_key)
            if entry:
                self._initial_resume_position = entry["position"]
                self._last_duration = entry.get("duration") or 0.0
                # The speed this episode was last watched at rides the
                # resume record (absent = 1.0).
                rate = entry.get("rate")
                if rate and rate != self._speed_rate:
                    self._speed_rate = float(rate)
                    for text in self.speed_texts:
                        text.value = f"{float(rate)}x"
                logger.info(
                    "resume available for %s at %.1fs",
                    self.resume_key,
                    entry["position"],
                )
                # The read can land AFTER the first ready/duration/position
                # signal, which would otherwise consume nothing and lose the
                # resume. Re-check now that we know the target.
                self._check_and_trigger_seek()

        from core.tasks import spawn

        spawn(_read(), name="resume-read")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    async def _start_playback(self):
        from core.tasks import spawn

        self._show_progress("Loading stream...")
        self._reconnect_count = 0
        try:
            self.video.playlist = [fv.VideoMedia(self.resource, http_headers=self.http_headers)]
            try:
                self.video.update()
            except RuntimeError:
                # Not mounted yet (slow first frame) — play() pushes the
                # playlist itself, so this is safe to skip.
                logger.debug("video.update() before mount; skipped")
            await self.video.play()
            self._start_watchdog()
            self._start_checkpoints()
            # Quality/audio options exist only once playback is running:
            # probe the master through the proxy, then reveal the pickers.
            spawn(self._probe_stream_options(), name="stream-probe")
        except Exception as ex:
            logger.exception("start_playback failed")
            self._show_final_error(f"Could not start playback: {ex}")

    def _manual_retry(self):
        if self._is_closing:
            return
        self._is_final_error = False
        self._reconnect_count = 0
        self._show_progress("Reconnecting stream...")
        from core.tasks import spawn

        async def _retry():
            try:
                self.video.playlist = [fv.VideoMedia(self.resource, http_headers=self.http_headers)]
                self.video.update()
                await self.video.play()
                self._start_watchdog()
            except Exception:
                self._show_final_error("Stream is not responding. Retry or go back.")

        spawn(_retry(), name="player-retry")

    # ------------------------------------------------------------------
    # Quality / audio pinning (through the proxy)
    # ------------------------------------------------------------------

    def _resource_url_for(self, variant: int | None, audio: str | None) -> str:
        """Rebuild the playback URL for a (variant, audio) pinning choice."""
        if self.hls_proxy is not None and self.source_url.startswith(("http://", "https://")):
            try:
                return self.hls_proxy.get_proxy_url(
                    self.source_url,
                    referer=self.source_referer,
                    headers=self.source_headers,
                    variant=variant,
                    audio=audio,
                )
            except Exception as ex:
                logger.warning("proxy rebuild failed, keeping current url: %s", ex)
        return self.resource

    @property
    def can_switch_quality(self) -> bool:
        return self.hls_proxy is not None and self.source_url.startswith(("http://", "https://"))

    async def list_variants(self) -> list[dict]:
        """HLS master variants (cached). Empty for media playlists."""
        if self._variants_cache is not None:
            return self._variants_cache
        if not self.can_switch_quality:
            return []
        try:
            variants = await asyncio.wait_for(
                self.hls_proxy.fetch_variants(self.source_url, headers=self.source_headers),
                timeout=8.0,
            )
        except Exception:
            variants = []
        self._variants_cache = variants or []
        return self._variants_cache

    async def list_audio_tracks(self) -> list[dict]:
        """External HLS audio renditions (cached)."""
        if self._audio_cache is not None:
            return self._audio_cache
        if not self.can_switch_quality:
            return []
        try:
            tracks = await asyncio.wait_for(
                self.hls_proxy.fetch_audio_tracks(self.source_url, headers=self.source_headers),
                timeout=8.0,
            )
        except Exception:
            tracks = []
        self._audio_cache = tracks or []
        return self._audio_cache

    async def _probe_stream_options(self) -> None:
        """Probe variants/audio once playing; reveal the quality chip when
        the stream actually has options to pick."""
        if not self.can_switch_quality or self._is_closing:
            return
        variants = await self.list_variants()
        # Unconditional: single-variant streams can still carry 2+ audio
        # renditions, so audio must be probed regardless.
        tracks = await self.list_audio_tracks()
        if self._is_closing:
            return
        if len(variants) > 1 or len(tracks) >= 2:
            self.variants = variants
            self.audio_tracks = tracks
            self._refresh_option_labels()
            with contextlib.suppress(Exception):
                self.video.update()

    async def apply_variant(self, index: int | None) -> None:
        """Pin a quality variant (None = Auto)."""
        self._current_variant = index
        await self._swap_media("Auto quality" if index is None else "Switching quality...")

    async def apply_audio(self, name: str | None) -> None:
        """Pin an audio rendition (None = manifest default)."""
        self._current_audio = name
        await self._swap_media("Default audio" if name is None else "Switching audio...")

    async def _swap_media(self, message: str):
        """Restart the playlist on the currently pinned resource, restoring
        position for seekable streams.

        Position/duration reads are bounded: a hung native bridge must not
        wedge the switcher. VOD restores; a live stream stays at the edge.
        """
        if self._is_closing or not self.video:
            return
        new_url = self._resource_url_for(self._current_variant, self._current_audio)
        position = None
        duration = None
        for getter in (self.video.get_current_position, self.video.get_duration):
            try:
                value = await asyncio.wait_for(asyncio.create_task(getter()), timeout=0.8)
                if getter is self.video.get_current_position:
                    position = value
                else:
                    duration = value
            except Exception:
                pass

        pos_sec = (
            position.in_seconds
            if position and getattr(position, "in_seconds", 0) > 0
            else self._last_position
        )
        dur_sec = (
            duration.in_seconds
            if duration and getattr(duration, "in_seconds", 0) > 0
            else self._last_duration
        )
        if dur_sec > 0:
            self._last_duration = dur_sec
        if dur_sec > 0 and pos_sec > 3:
            self._pending_seek = pos_sec

        self.resource = new_url
        self._show_progress(message)
        try:
            self.video.playlist = [fv.VideoMedia(new_url, http_headers=self.http_headers)]
            self.video.update()
            await self.video.play()
            self._start_watchdog()
            self._restore_speed_after_swap()
        except Exception as ex:
            logger.error("Stream switch failed: %s", ex)
            self._show_final_error("Switch failed. Retry or go back.")

    def _restore_speed_after_swap(self):
        """A playlist swap resets the playback rate to 1.0 — reapply the
        user's chosen speed (KTV parity)."""
        if self._speed_rate != 1.0:
            try:
                self.video.playback_rate = self._speed_rate
                self.video.update()
            except Exception:
                pass

    def _cycle_speed(self, e=None):
        """One tap per preset, wrapping. The confirmation rides the toast
        chip — the speed text only covers the branch whose chip was tapped
        (the control tree is built twice, touch + desktop/TV)."""
        self._speed_index = (self._speed_index + 1) % len(SPEEDS)
        rate = SPEEDS[self._speed_index]
        self._speed_rate = rate
        for text in self.speed_texts:
            text.value = f"{rate}x"
        try:
            self.video.playback_rate = rate
            self.video.update()
        except Exception:
            pass
        self._toast_show(f"Speed {rate}x")

    def _cycle_speed_reverse(self):
        """Cycle speed backwards (via '<' or ',' keyboard shortcut)."""
        self._speed_index = (self._speed_index - 1) % len(SPEEDS)
        rate = SPEEDS[self._speed_index]
        self._speed_rate = rate
        for text in self.speed_texts:
            text.value = f"{rate}x"
        try:
            self.video.playback_rate = rate
            self.video.update()
        except Exception:
            pass
        self._toast_show(f"Speed {rate}x")

    # ------------------------------------------------------------------
    # Keyboard & Direct Playback Controls (KTV Player parity)
    # ------------------------------------------------------------------

    async def toggle_play_pause(self):
        """Toggle play/pause with visual toast feedback."""
        try:
            await self.video.play_or_pause()
            is_playing = await self.video.is_playing()
            self._toast_show("Play" if is_playing else "Pause")
        except Exception as ex:
            logger.debug("toggle_play_pause failed: %s", ex)

    async def seek_relative(self, delta_seconds: float):
        """Seek forward (+) or backward (-) with toast feedback."""
        try:
            pos = max(0.0, self._last_position + delta_seconds)
            if self._last_duration > 0:
                pos = min(pos, self._last_duration)
            await self.video.seek(ft.Duration(seconds=pos))
            self._last_position = pos
            sign = "+" if delta_seconds > 0 else ""
            self._toast_show(f"{sign}{int(delta_seconds)}s ({_fmt(pos)})")
        except Exception as ex:
            logger.debug("seek_relative failed: %s", ex)

    def adjust_volume(self, delta: float):
        """Adjust volume by delta percentage (clamped 0..100)."""
        try:
            current_vol = getattr(self.video, "volume", 100.0) or 100.0
            new_vol = max(0.0, min(100.0, current_vol + delta))
            self.video.volume = new_vol
            self.video.update()
            self._toast_show(f"Volume {int(new_vol)}%")
        except Exception as ex:
            logger.debug("adjust_volume failed: %s", ex)

    def toggle_mute(self):
        """Toggle audio mute state."""
        try:
            new_muted = not getattr(self.video, "muted", False)
            self.video.muted = new_muted
            self.video.update()
            self._toast_show("Mute" if new_muted else "Unmute")
        except Exception as ex:
            logger.debug("toggle_mute failed: %s", ex)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        try:
            new_fs = not getattr(self.video, "fullscreen", False)
            self.video.fullscreen = new_fs
            self.video.update()
        except Exception as ex:
            logger.debug("toggle_fullscreen failed: %s", ex)

    async def jump_percentage(self, pct: float):
        """Jump to a specific percentage (0.0 .. 0.9) of the video."""
        try:
            if self._last_duration <= 0:
                return
            target = self._last_duration * pct
            await self.video.seek(ft.Duration(seconds=target))
            self._last_position = target
            self._toast_show(f"{int(pct * 100)}% ({_fmt(target)})")
        except Exception as ex:
            logger.debug("jump_percentage failed: %s", ex)

    # Flutter's keyLabel varies by platform ("Arrow Left" vs "ArrowLeft",
    # "Return" vs "Enter", "Esc" vs "Escape") — CollabShell normalizes by
    # lowercase + de-space + alias and so do we. The old exact-string
    # compares are why only Space ever matched.
    _KEY_ALIASES: ClassVar[dict] = {"return": "enter", "esc": "escape", "spacebar": "space"}
    _SEEK_BACK = ("arrowleft", "left", "j")
    _SEEK_FORWARD = ("arrowright", "right", "l")
    _VOLUME_UP = ("arrowup", "up")
    _VOLUME_DOWN = ("arrowdown", "down")
    _PLAY_PAUSE = ("space", "k", "mediaplaypause", "mediaplay", "mediapause")
    _PREV = ("[", "p", "mediatrackprevious")
    _NEXT = ("]", "n", "mediatracknext")

    @classmethod
    def _norm_key(cls, key: str) -> str:
        return cls._KEY_ALIASES.get(
            key.replace(" ", "").lower(), key.replace(" ", "").lower()
        )

    async def handle_key(self, e) -> bool:
        """Handle desktop and TV keyboard events. Full parity with the
        house player: play/pause, seek, volume, mute, fullscreen, episode
        skips, speed, percentage jumps and the skip-intro shortcut.

        Matching is NORMALIZED (space-less, lowercase, aliases) because
        Flutter's key label varies by platform — the exact-string compares
        this replaces only ever matched the space bar (owner: "you did
        pause with space bar but you did not do seek forward").
        """
        key = self._norm_key(getattr(e, "key", "") or "")

        if key in self._PLAY_PAUSE:
            await self.toggle_play_pause()
            return True
        if key in self._SEEK_BACK:
            await self.seek_relative(-10)
            return True
        if key in self._SEEK_FORWARD:
            await self.seek_relative(10)
            return True
        if key in self._VOLUME_UP:
            self.adjust_volume(10)
            return True
        if key in self._VOLUME_DOWN:
            self.adjust_volume(-10)
            return True
        if key == "m":
            self.toggle_mute()
            return True
        if key == "f":
            self.toggle_fullscreen()
            return True
        if key in self._NEXT and self.on_next is not None:
            self.on_next()
            return True
        if key in self._PREV and self.on_previous is not None:
            self.on_previous()
            return True
        if key in (">", "."):
            self._cycle_speed()
            return True
        if key in ("<", ","):
            self._cycle_speed_reverse()
            return True
        if key.isdigit():
            await self.jump_percentage(int(key) / 10.0)
            return True
        if key == "s" and getattr(self, "skip_chip", None) and self.skip_chip.visible:
            await self._on_skip_chip()
            return True
        return False

    def _refresh_option_labels(self) -> None:
        """Sync the quality/audio chip text with the current pins, and
        reveal the chips now that the probe proved there are options."""
        if not hasattr(self, "quality_texts"):
            return
        if self._current_variant is None:
            value = "Auto"
        else:
            current = next(
                (
                    v
                    for v in (self._variants_cache or [])
                    if v.get("index") == self._current_variant
                ),
                None,
            )
            value = current["label"] if current else f"V{self._current_variant + 1}"
        has_quality = len(self._variants_cache or []) > 1
        has_audio = len(self._audio_cache or []) >= 2
        for text in self.quality_texts:
            text.value = value if has_quality else "Auto"
        for chip in self.quality_chips:
            chip.visible = has_quality
        for text in self.audio_texts:
            text.value = self._current_audio or "Default"
        for chip in self.audio_chips:
            chip.visible = has_audio

    # ------------------------------------------------------------------
    # Overlay + watchdog
    # ------------------------------------------------------------------

    def _show_progress(self, message: str):
        self._is_final_error = False
        self.status_text.value = message
        self.loading_ring.visible = True
        self.retry_btn.visible = False
        self.back_error_btn.visible = True
        self._overlay_hidden = False
        self.overlay.visible = True
        self.update()

    def _show_final_error(self, message: str):
        self._cancel_watchdog()
        self._is_final_error = True
        self.status_text.value = message
        self.loading_ring.visible = False
        self.retry_btn.visible = True
        self.back_error_btn.visible = True
        self.overlay.visible = True
        self._overlay_hidden = False
        self._enable_tap_to_close()
        # The session was torn down while the stream was dying (hot
        # reload / app close): there is nothing left to update, and the
        # raise used to cascade through the caller's error path
        # (observed live: "Control must be added to the page first").
        with contextlib.suppress(RuntimeError):
            self.update()

    def _enable_tap_to_close(self):
        """A tap on the dead overlay goes Back — the error card is not a
        trap (KTV parity). Wired once; the handler stays for the life of
        the player."""
        if getattr(self, "_tap_to_close_wired", False):
            return
        self._tap_to_close_wired = True

        def _tap(_):
            if self._is_final_error:
                self._on_back()

        with contextlib.suppress(Exception):
            self.overlay.on_click = _tap

    def _hide_overlay(self):
        self._overlay_hidden = True
        self.overlay.visible = False
        self._cancel_watchdog()
        self.update()

    def _start_watchdog(self, timeout: float | None = None):
        self._cancel_watchdog()
        secs = timeout or WATCHDOG_SECONDS

        async def _watchdog():
            await asyncio.sleep(secs)
            if self._is_closing or self._is_final_error or self._overlay_hidden:
                return
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

    # ------------------------------------------------------------------
    # Position checkpoints + resume
    # ------------------------------------------------------------------

    def _start_checkpoints(self):
        async def _checkpoint_loop():
            while not self._is_closing:
                await asyncio.sleep(POSITION_CHECKPOINT_SECONDS)
                await self._save_current_position()

        try:
            loop = asyncio.get_running_loop()
            self._checkpoint_task = loop.create_task(_checkpoint_loop())
        except RuntimeError:
            pass

    def _check_and_trigger_seek(self):
        if self._pending_seek is not None:
            target = self._pending_seek
            self._pending_seek = None
            self._deferred_seek(target)
            return
        if self._initial_resume_position is not None:
            target = self._initial_resume_position
            self._initial_resume_position = None
            self._deferred_seek(target)

    def _deferred_seek(self, seconds: float):
        from core.tasks import spawn

        async def _seek():
            # mpv discards seeks sent while the demuxer is still opening;
            # poll for a real duration first, then seek.
            duration = None
            for _ in range(int(DEFER_SEEK_POLL_SECONDS * 5)):
                try:
                    duration = await asyncio.wait_for(
                        asyncio.create_task(self.video.get_duration()), timeout=0.5
                    )
                except Exception:
                    duration = None
                if duration and duration.in_seconds > 0:
                    break
                await asyncio.sleep(0.2)
            try:
                await self.video.seek(ft.Duration(seconds=seconds))
                self._last_position = seconds
                self.status_text.value = f"Resumed from {_fmt(seconds)}"
                self._toast_show(f"Resumed from {_fmt(seconds)}")
                self.update()
            except Exception as ex:
                logger.warning("deferred seek failed: %s", ex)

        spawn(_seek(), name="player-seek")

    def will_unmount(self):
        """Overlay-removal safety net: the shell can drop the player
        without handle_close (remount races) — the position save must
        not depend on the close path landing.

        SYNC on purpose: flet invokes ``will_unmount()`` without awaiting
        (messaging/session.py), so an async version produced a
        "coroutine was never awaited" warning and the save NEVER RAN.
        The async half rides spawn(); the toast unregister — staleness-
        guarded so a stale unmount cannot clear a newer player's chip —
        happens synchronously.
        """
        try:
            from core.notify import unregister_fullscreen_toast

            unregister_fullscreen_toast(self._toast_show)
        except Exception:
            pass
        if self._position_saved or self._is_closing:
            return

        async def _save():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._save_current_position(), timeout=2.0)
            self._position_saved = True

        from core.tasks import spawn

        spawn(_save(), name="player-unmount-save")

    async def _save_current_position(self):
        if self._position_saved or self._is_closing:
            return
        if not self.store or not self.resume_key:
            return
        position = None
        duration = None
        try:
            position = await asyncio.wait_for(
                asyncio.create_task(self.video.get_current_position()), timeout=0.8
            )
            duration = await asyncio.wait_for(
                asyncio.create_task(self.video.get_duration()), timeout=0.8
            )
        except Exception:
            return
        pos_sec = getattr(position, "in_seconds", 0) or 0
        dur_sec = getattr(duration, "in_seconds", 0) or 0
        if pos_sec <= 0:
            return
        self._last_position = pos_sec
        if dur_sec > 0:
            self._last_duration = dur_sec
        await self.store.save_position(self.resume_key, pos_sec, dur_sec or None, self._speed_rate)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def open_stream_settings(self) -> None:
        """In-player Stream Quality & Audio picker (KTV parity).

        Only opens when the stream actually has options: a dialog listing a
        single quality is noise. Both sections are built from the live
        master playlist through the proxy.

        Double-open guard: the chips re-spawn this on every tap, so a
        second tap while the sheet is up (or while its options are still
        being fetched) is a no-op — two stacked dialogs were reachable.
        """
        if self._settings_open:
            return
        self._settings_open = True
        from flet import context as flet_context

        variants = await self.list_variants()
        tracks = await self.list_audio_tracks()
        try:
            page = flet_context.page
        except Exception:
            page = None
        if page is None or self._is_closing:
            self._settings_open = False
            return
        if (
            len(variants) <= 1
            and len(tracks) < 2
            and not self.subtitles
            and not self._local_subtitle
        ):
            self._settings_open = False
            return

        from core.dialogs import show_app_dialog
        from core.tasks import spawn

        def _close():
            self._settings_open = False
            page._app_dialog = None
            with contextlib.suppress(Exception):
                page.pop_dialog()

        def _pick_variant(index):
            from core.tasks import spawn

            _close()
            spawn(self.apply_variant(index), name="apply-variant")

        def _pick_audio(name):
            from core.tasks import spawn

            _close()
            spawn(self.apply_audio(name), name="apply-audio")

        sections: list[ft.Control] = []
        if len(variants) > 1:
            rows = [
                GuardedOutlinedButton(
                    content=v["label"],
                    on_click=lambda e, i=v["index"]: _pick_variant(i),
                )
                for v in variants
            ]
            rows.insert(
                0,
                ft.FilledButton(
                    content="Auto (adaptive)",
                    on_click=lambda e: _pick_variant(None),
                ),
            )
            sections.append(ft.Text("Quality", size=13, weight=ft.FontWeight.W_700))
            sections.append(ft.Column(rows, tight=True, spacing=6))
        if len(tracks) >= 2:
            rows = [
                GuardedOutlinedButton(
                    content=t["name"] + (f" ({t['language']})" if t["language"] else ""),
                    on_click=lambda e, n=t["name"]: _pick_audio(n),
                )
                for t in tracks
            ]
            rows.insert(
                0,
                ft.FilledButton(
                    content="Default audio",
                    on_click=lambda e: _pick_audio(None),
                ),
            )
            sections.append(ft.Container(height=8))
            sections.append(ft.Text("Audio", size=13, weight=ft.FontWeight.W_700))
            sections.append(ft.Column(rows, tight=True, spacing=6))

        def _pick_subtitle(index):
            _close()
            self.apply_subtitle(index)

        sub_rows = [
            ft.FilledButton(
                content="Off",
                on_click=lambda e: _pick_subtitle(None),
            )
        ]
        for i, track in enumerate(self.subtitles):
            label = track.get("label") or f"Track {i + 1}"
            if track.get("default"):
                label += " (default)"
            sub_rows.append(
                GuardedOutlinedButton(
                    content=label,
                    on_click=lambda e, idx=i: _pick_subtitle(idx),
                )
            )
        if self._local_subtitle:
            sub_rows.append(
                GuardedOutlinedButton(
                    content=f"Local: {self._local_subtitle['name']}",
                    on_click=lambda e: (_close(), self.apply_local_subtitle()),
                )
            )
        sub_rows.append(
            GuardedTextButton(
                content="Load from file…",
                on_click=lambda e: (
                    _close(),
                    spawn(self._pick_subtitle_file(), name="pick-subtitle"),
                ),
            )
        )
        sections.append(ft.Container(height=8))
        sections.append(ft.Text("Subtitles", size=13, weight=ft.FontWeight.W_700))
        sections.append(ft.Column(sub_rows, tight=True, spacing=6))

        # Subtitle size + aspect fit — presentation controls that ride
        # every track (the source's own list stays untouched above).
        size_section: list[ft.Control] = []
        if self.subtitles or self._local_subtitle:
            size_section.append(ft.Text("Subtitle size", size=13, weight=ft.FontWeight.W_700))
            size_section.append(
                ft.Row(
                    [
                        GuardedOutlinedButton(
                            content=f"{s}",
                            on_click=lambda e, sz=s: self._set_subtitle_size(sz),
                        )
                        for s in self.SUBTITLE_SIZES
                    ],
                    spacing=6,
                )
            )
        size_section.append(ft.Text("Aspect fit", size=13, weight=ft.FontWeight.W_700))
        size_section.append(
            ft.Row(
                [
                    GuardedOutlinedButton(
                        content=label,
                        on_click=lambda e, n=name: self._set_fit(n),
                    )
                    for name, label in FIT_OPTIONS
                ],
                spacing=6,
            )
        )
        sections.extend(size_section)

        try:
            show_app_dialog(
                page,
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Stream Settings", weight=ft.FontWeight.BOLD),
                    content=ft.Column(sections, tight=True, spacing=8),
                    actions=[ft.TextButton(content="Close", on_click=lambda e: _close())],
                    actions_alignment=ft.MainAxisAlignment.END,
                ),
            )
        except Exception as ex:
            # A sheet that never showed must not lock the button forever.
            self._settings_open = False
            logger.warning("stream settings failed to open: %s", ex)

    def apply_subtitle(self, index: int | None) -> None:
        """Off (None) clears the track; an index applies that source
        track. The URLs in self.subtitles are already proxy-routed by the
        controller, so they carry the headers the subtitle host needs."""
        try:
            if index is None:
                self.video.subtitle_track = None
            else:
                track = self.subtitles[index]
                self.video.subtitle_track = fv.VideoSubtitleTrack(src=track["url"])
            self.video.update()
        except Exception as ex:
            logger.warning("subtitle switch failed: %s", ex)

    def apply_local_subtitle(self) -> None:
        """The loaded file's own text becomes the track. flet-video accepts
        raw SRT/VTT text as src — no host, no headers, works on web and
        native alike."""
        local = self._local_subtitle
        if not local:
            return
        try:
            self.video.subtitle_track = fv.VideoSubtitleTrack(
                src=local["text"], title=local["name"]
            )
            self.video.update()
        except Exception as ex:
            logger.warning("local subtitle failed: %s", ex)

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

    def _apply_default_subtitle(self) -> None:
        """The source's own default track (anikato marks English) applies
        automatically once, on first load."""
        if self._subtitle_applied or not self.subtitles:
            return
        self._subtitle_applied = True
        for i, track in enumerate(self.subtitles):
            if track.get("default"):
                self.apply_subtitle(i)
                return

    @staticmethod
    def _seconds(payload) -> float:
        value = getattr(payload, "in_seconds", None)
        if value is not None:
            return float(value)
        if isinstance(payload, bool):
            return 0.0
        try:
            return float(payload)
        except (TypeError, ValueError):
            return 0.0

    def _on_first_ready(self, e=None):
        logger.info("player ready")
        # A close or a final error can land between "loading" and this
        # signal — hiding the overlay then swallowed the error card the
        # user needed to see.
        if not self._is_closing and not self._is_final_error:
            self._hide_overlay()
            self._check_and_trigger_seek()
            self._apply_default_subtitle()
        # The speed read can land before or after this signal; either way
        # the saved rate must reach the video (it used to only ride the
        # chip text and be reapplied after a playlist swap).
        self._restore_speed_after_swap()

    def _on_duration_change(self, e):
        seconds = self._seconds(getattr(e, "data", None))
        if seconds > 0:
            self._last_duration = seconds
            if not self._overlay_hidden:
                self._hide_overlay()
                self._check_and_trigger_seek()

    def _on_pos_change(self, e):
        seconds = self._seconds(getattr(e, "data", None))
        if seconds > 0:
            self._last_position = seconds
            if not self._overlay_hidden:
                self._hide_overlay()
                self._check_and_trigger_seek()
            self._update_skip_chip(seconds)

    # ------------------------------------------------------------------
    # Snapshot: take_screenshot -> a real file. The device's Downloads dir
    # when the platform offers one (visible outside the app), else the
    # data tier; the toast carries the file's name, never a false claim.
    # ------------------------------------------------------------------

    async def _snapshot_directory(self) -> str | None:
        """The device Downloads directory on platforms that have it; None
        routes the save into the app's data tier. Web has no service."""
        page = self._page()
        if page is None or getattr(page, "web", False):
            return None
        try:
            paths = ft.StoragePaths()
            return await asyncio.wait_for(paths.get_downloads_directory(), timeout=5.0) or None
        except Exception:
            return None

    async def _take_snapshot(self, e=None):
        try:
            from core.notify import show_snack

            # The confirmation rides the RESULT — announcing before the
            # await claimed success the frame may never produce (and a
            # discarded failure left the user with a photo that isn't).
            shot = await asyncio.wait_for(self.video.take_screenshot(), timeout=5.0)
            if shot is None:
                show_snack(self._page(), "Screenshot unavailable", bgcolor=AppColors.PRIMARY)
                return
            directory = await self._snapshot_directory()
            path = await asyncio.to_thread(save_snapshot, shot, directory)
            logger.info("snapshot saved: %s", path)
            show_snack(
                self._page(),
                f"Saved {os.path.basename(path)}",
                bgcolor=AppColors.PRIMARY,
            )
        except Exception as ex:
            logger.info("snapshot failed: %s", ex)
            from core.notify import show_snack

            show_snack(self._page(), "Screenshot failed", bgcolor=AppColors.PRIMARY)

    def _page(self):
        from flet import context as flet_context

        try:
            return flet_context.page
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Subtitle presentation (size persisted; the source's tracks are
    # picked from the settings sheet)
    # ------------------------------------------------------------------

    SUBTITLE_SIZES: ClassVar[list[int]] = [12, 16, 22, 30]

    def _subtitle_size(self) -> int:
        if self.store is None:
            return 16
        try:
            size = int(self.store.get_setting("subtitle_size", 16))
        except Exception:
            size = 16
        return size if size in self.SUBTITLE_SIZES else 16

    def _set_subtitle_size(self, size: int) -> None:
        if self.store is None or size not in self.SUBTITLE_SIZES:
            return

        async def _save():
            await self.store.save_setting("subtitle_size", size)
            try:
                self.video.subtitle_configuration.text_style.size = size
                self.video.update()
            except Exception:
                pass

        from core.tasks import spawn

        spawn(_save(), name="save-subtitle-size")

    def _box_fit(self) -> ft.BoxFit:
        if self.store is None:
            return ft.BoxFit.CONTAIN
        try:
            name = str(self.store.get_setting("video_fit", "contain") or "contain")
        except Exception:
            name = "contain"
        return _BOX_FITS.get(name, ft.BoxFit.CONTAIN)

    def _set_fit(self, name: str) -> None:
        if self.store is None or name not in _BOX_FITS:
            return

        async def _save():
            await self.store.save_setting("video_fit", name)
            try:
                self.video.fit = _BOX_FITS[name]
                self.video.update()
            except Exception:
                pass

        from core.tasks import spawn

        spawn(_save(), name="save-video-fit")

    # ------------------------------------------------------------------
    # Fullscreen toast (the snackbar's fullscreen-visible twin)
    # ------------------------------------------------------------------

    def _toast_show(self, message: str) -> None:
        self.toast_chip.content.value = message
        self.toast_chip.visible = True
        with contextlib.suppress(Exception):
            self.toast_chip.update()
        # Generation counter: an older _hide task used to fire early and
        # hide a toast that had just been replaced.
        self._toast_gen = getattr(self, "_toast_gen", 0) + 1
        gen = self._toast_gen

        async def _hide():
            await asyncio.sleep(2.0)
            if self._is_closing or gen != self._toast_gen:
                return
            self.toast_chip.visible = False
            with contextlib.suppress(Exception):
                self.toast_chip.update()

        from core.tasks import spawn

        spawn(_hide(), name="player-toast-hide")

    # ------------------------------------------------------------------
    # Skip-intro / skip-outro (windows exactly as the source declared them)
    # ------------------------------------------------------------------

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
        """The window the position is inside, with its seek target."""
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
        window = self._active_window(seconds)
        is_intro = self._is_intro_window(window)
        visible = window is not None
        label = "Skip Intro" if is_intro else "Skip Outro"
        changed = visible != self.skip_chip.visible or (
            visible and self.skip_chip.content.value != label
        )
        if not changed:
            return
        self.skip_chip.visible = visible
        self.skip_chip.content.value = label
        with contextlib.suppress(Exception):
            self.skip_chip.update()

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

    def _on_error(self, e):
        err_msg = str(getattr(e, "data", None) or e)
        logger.warning("player error: %s", err_msg)
        if self._is_closing:
            return
        # "Cannot seek" fires at the live edge and after a VOD swap — it is
        # not a playback failure, and raising the error card over it would
        # interrupt a healthy stream (KTV swallows it the same way).
        if "Cannot seek" in err_msg or "force-seekable" in err_msg:
            logger.debug("swallowed seek error: %s", err_msg)
            return
        if self._is_final_error:
            return
        self._show_final_error("Unable to load stream. Check your connection or retry.")

    def _on_complete(self, e=None):
        """Auto-advance only at a real ending.

        Two guards, both from the house player: duration must be known (a
        stall-induced complete arrives before the first duration tick and
        would otherwise jump episodes and abandon position), and the
        position must be within 5s of the end.
        """
        if self._last_duration <= 0:
            logger.info("complete ignored: duration unknown")
            return
        if self._last_position < self._last_duration - 5:
            logger.info(
                "complete ignored: %.0fs of %.0fs",
                self._last_position,
                self._last_duration,
            )
            return
        if self.on_next is not None:
            self.on_next()

    async def _on_back(self, e=None):
        """Handle back button press - route through on_close callback.
        
        Matches ktv-player pattern: await on_close callback if it returns a coroutine.
        """
        if self.on_close:
            try:
                result = self.on_close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as ex:
                logger.error("Error executing on_close callback: %s", ex)

    async def handle_close(self):
        if self._is_closing:
            return
        self._is_closing = True
        try:
            from core.notify import unregister_fullscreen_toast

            unregister_fullscreen_toast()
        except Exception:
            pass
        self._is_final_error = True
        self._cancel_watchdog()
        if self._checkpoint_task and not self._checkpoint_task.done():
            self._checkpoint_task.cancel()
        # Bounded: a hung native bridge must not make Back dead.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._save_current_position(), timeout=3.0)
        self._position_saved = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.video.stop(), timeout=2.0)
        try:
            self.video.playlist = []
            self.video.update()
        except Exception:
            pass


def _fmt(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"
