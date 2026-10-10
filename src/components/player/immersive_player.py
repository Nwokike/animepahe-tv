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
import logging
import re

import flet as ft
import flet_video as fv

from core.theme import AppColors

logger = logging.getLogger(__name__)

WATCHDOG_SECONDS = 20.0
DEFER_SEEK_POLL_SECONDS = 4.0
POSITION_CHECKPOINT_SECONDS = 10.0

KWIK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Playback speeds for the chip, index 2 is normal.
SPEEDS = (0.25, 0.5, 1.0, 1.25, 1.5, 2.0)


def _stream_variants(m3u8_text: str) -> list[dict]:
    """Parse an HLS master playlist into variants.

    Returns [] for a media playlist (single quality) or anything
    malformed — the caller then hides the quality chip entirely.
    """
    if not m3u8_text or "#EXT-X-STREAM-INF" not in m3u8_text:
        return []
    base = None
    lines = m3u8_text.splitlines()
    for line in lines:
        if line and not line.startswith("#"):
            base = line
            break
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
            uri = line if line.startswith("http") else base
            entry = dict(pending)
            entry["uri"] = uri
            label = f"{entry.get('height', 0)}p" if entry.get("height") else f"{entry.get('bandwidth', 0) // 1000}kbps"
            entry["label"] = label
            variants.append(entry)
            pending = {}
    return variants


class ImmersivePlayer(ft.Stack):
    """A Stack: black container, video, loading/error overlay."""

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

        self._is_closing = False
        self._is_final_error = False
        self._overlay_hidden = False
        self._position_saved = False
        self._current_variant_index = 0

        self._initial_resume_position: float | None = None
        self._pending_seek: float | None = None
        self._last_position = 0.0
        self._last_duration = 0.0
        self._watchdog_task: asyncio.Task | None = None
        self._checkpoint_task: asyncio.Task | None = None
        self._speed_index = SPEEDS.index(1.0)

        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self):
        self.loading_ring = ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4)
        self.status_text = ft.Text(
            "Loading stream...", size=14, color=ft.Colors.WHITE
        )
        self.retry_btn = ft.OutlinedButton(
            content="Retry",
            icon=ft.Icons.REFRESH_ROUNDED,
            visible=False,
            on_click=lambda e: self._manual_retry(),
        )
        self.back_error_btn = ft.OutlinedButton(
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
            fit=ft.BoxFit.CONTAIN,
            title="AnimePahe",
            controls=self._build_controls(),
            configuration=fv.VideoConfiguration(
                enable_hardware_acceleration=True,
                mpv_properties={
                    "cache": "yes",
                    "cache-secs": 5,
                    "demuxer-max-bytes": "50M",
                    "demuxer-max-back-bytes": "10M",
                    "framedrop": "vo",
                    "hr-seek-framedrop": "yes",
                    # mpv's default 60s network timeout means a dead host
                    # spins this spinner for a minute. 10s makes failure
                    # deterministic.
                    "network-timeout": 10,
                },
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
        quality_state = {"text": "Auto"}
        speed_state = {"text": "1.0x"}

        def _quality_label() -> str:
            if not self.variants:
                return "Auto"
            if self._current_variant_index == 0:
                return "Auto"
            return self.variants[self._current_variant_index - 1]["label"]

        def _cycle_speed(e=None):
            self._speed_index = (self._speed_index + 1) % len(SPEEDS)
            rate = SPEEDS[self._speed_index]
            speed_state["text"] = f"{rate}x"
            self.video.playback_rate = rate
            self.video.update()

        def _cycle_quality(e=None):
            if not self.variants:
                return
            self._current_variant_index = (self._current_variant_index + 1) % (
                len(self.variants) + 1
            )
            index = self._current_variant_index
            if index == 0:
                self._swap_media(self.resource, "Auto quality")
            else:
                variant = self.variants[index - 1]
                self._swap_media(variant["uri"], f"Quality: {variant['label']}")

        def _bar(desktop: bool) -> list:
            items = [
                fv.VideoSpacer(),
                fv.VideoPositionIndicator(),
                fv.VideoSpacer(),
            ]
            if self.variants:
                items.append(
                    ft.Container(
                        content=ft.Text(quality_state["text"], size=12),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        border_radius=6,
                        ink=True,
                        tooltip="Quality",
                        on_click=_cycle_quality,
                    )
                )
            items.append(
                ft.Container(
                    content=ft.Text(speed_state["text"], size=12),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=6,
                    ink=True,
                    tooltip="Playback speed",
                    on_click=_cycle_speed,
                )
            )
            if self.on_previous is not None:
                items.append(
                    fv.VideoSkipPreviousButton(
                        icon_size=24.0,
                        on_click=lambda e: self.on_previous(),
                    )
                )
            if self.on_next is not None:
                items.append(
                    fv.VideoSkipNextButton(
                        icon_size=24.0,
                        on_click=lambda e: self.on_next(),
                    )
                )
            items.append(fv.VideoFullscreenButton(icon_size=24.0))
            return items

        top_bar = [
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                on_click=lambda e: self._on_back(),
                tooltip="Back",
            ),
            ft.Text(self.title, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
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
        self._read_resume_position()
        self._start_playback()

    def _read_resume_position(self):
        if not self.store or not self.resume_key:
            return

        async def _read():
            entry = await self.store.get_position(self.resume_key)
            if entry:
                self._initial_resume_position = entry["position"]
                self._last_duration = entry.get("duration") or 0.0
                logger.info(
                    "resume available for %s at %.1fs",
                    self.resume_key,
                    entry["position"],
                )

        from core.tasks import spawn

        spawn(_read(), name="resume-read")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    async def _start_playback(self):
        self._show_progress("Loading stream...")
        self.resource = self.resource
        try:
            self.video.playlist = [
                fv.VideoMedia(self.resource, http_headers=self.http_headers)
            ]
            self.video.update()
            await self.video.play()
            self._start_watchdog()
            self._start_checkpoints()
        except Exception as ex:
            logger.exception("start_playback failed")
            self._show_final_error(f"Could not start playback: {ex}")

    def _manual_retry(self):
        self._is_final_error = False
        self._show_progress("Reconnecting stream...")
        from core.tasks import spawn

        async def _retry():
            try:
                self.video.playlist = [
                    fv.VideoMedia(self.resource, http_headers=self.http_headers)
                ]
                self.video.update()
                await self.video.play()
                self._start_watchdog()
            except Exception:
                self._show_final_error("Stream is not responding. Retry or go back.")

        spawn(_retry(), name="player-retry")

    async def _swap_media(self, url: str, message: str):
        """Restart the single-item playlist, restoring position.

        Position/duration reads are bounded: a hung native bridge must not
        wedge the switcher. VOD restores; a live stream stays at the edge.
        """
        position = None
        duration = None
        for getter, attr in (
            (self.video.get_current_position, "position"),
            (self.video.get_duration, "duration"),
        ):
            try:
                value = await asyncio.wait_for(
                    asyncio.create_task(getter()), timeout=0.8
                )
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

        self.resource = url
        self._show_progress(message)
        try:
            self.video.playlist = [fv.VideoMedia(url, http_headers=self.http_headers)]
            self.video.update()
            await self.video.play()
            self._start_watchdog()
        except Exception:
            self._show_final_error("Quality switch failed. Retry or go back.")

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
        self.update()

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
                self.update()
            except Exception as ex:
                logger.warning("deferred seek failed: %s", ex)

        spawn(_seek(), name="player-seek")

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
        await self.store.save_position(self.resume_key, pos_sec, dur_sec or None)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

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
        self._hide_overlay()
        self._check_and_trigger_seek()

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

    def _on_error(self, e):
        logger.warning("player error: %s", getattr(e, "data", e))
        if not self._overlay_hidden:
            self._show_final_error("Playback error. Retry or go back.")

    def _on_complete(self, e=None):
        if self.on_next is not None:
            self.on_next()

    def _on_back(self, e=None):
        from core.tasks import spawn

        async def _close():
            await self.handle_close()
            if self.on_close:
                result = self.on_close()
                if asyncio.iscoroutine(result):
                    await result

        spawn(_close(), name="player-close")

    async def handle_close(self):
        if self._is_closing:
            return
        self._is_closing = True
        self._is_final_error = True
        self._cancel_watchdog()
        if self._checkpoint_task and not self._checkpoint_task.done():
            self._checkpoint_task.cancel()
        # Bounded: a hung native bridge must not make Back dead.
        try:
            await asyncio.wait_for(self._save_current_position(), timeout=3.0)
        except Exception:
            pass
        self._position_saved = True
        try:
            await asyncio.wait_for(self.video.stop(), timeout=2.0)
        except Exception:
            pass
        try:
            self.video.playlist = []
            self.video.update()
        except Exception:
            pass


def _fmt(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"
