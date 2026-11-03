"""Event handlers for ImmersivePlayer (KTV skeleton, animepahe dialogs)."""

import contextlib
import logging
import re

import flet as ft
import flet_video as fv

# Module-level import (no cycle: immersive_player imports handlers lazily
# inside method bodies only).
from components.player.immersive_player import SPEEDS
from core.tasks import spawn
from core.theme import AppColors

logger = logging.getLogger(__name__)

STREAM_RECONNECT_MAX = 3


async def cycle_speed(player_inst):
    """Cycle playback speed through SPEEDS and persist the choice on the
    resume record (the next open continues at the same rate)."""
    player_inst._speed_idx = (player_inst._speed_idx + 1) % len(SPEEDS)
    rate = SPEEDS[player_inst._speed_idx]
    player_inst.video.playback_rate = rate
    if getattr(player_inst, "speed_text", None) is not None:
        player_inst.speed_text.value = f"{rate}x"
    try:
        player_inst.video.update()
        if hasattr(player_inst.speed_text, "update"):
            player_inst.speed_text.update()
    except Exception as ex:
        logger.warning("Failed to update speed UI: %s", ex)
    player_inst._toast_show(f"Speed {rate}x")
    if player_inst.store is not None and player_inst.resume_key:
        try:
            await player_inst.store.save_position(
                player_inst.resume_key,
                player_inst._last_position,
                player_inst._last_duration,
                rate=rate,
            )
        except Exception as ex:
            logger.debug("speed persist failed: %s", ex)


async def pick_subtitles(player_inst):
    """Subtitle selection: Auto / Off / the source's own tracks / a local
    .srt/.vtt file from the device."""

    active_sub = getattr(player_inst, "_subtitle_selection", "auto")

    def _check_icon(is_active: bool):
        return (
            ft.Icon(ft.Icons.CHECK_ROUNDED, color=AppColors.PRIMARY)
            if is_active
            else None
        )

    def _close_dialog(e=None):
        try:
            dialog.open = False
            page = player_inst.safe_page or player_inst._page()
            if page is not None:
                page.update()
        except Exception:
            pass

    async def _select_auto(e=None):
        player_inst._subtitle_selection = "auto"
        player_inst._subtitle_applied = False
        _close_dialog()
        # Re-run the default pick (post-attach semantics).
        player_inst._media_attached = bool(player_inst._playback_started)
        player_inst._run_async(player_inst._apply_default_subtitle)

    async def _select_off(e=None):
        player_inst._subtitle_selection = None
        try:
            player_inst.video.subtitle_track = fv.VideoSubtitleTrack.none()
            player_inst.video.update()
        except Exception as ex:
            logger.warning("Disable subtitles failed: %s", ex)
        _close_dialog()

    async def _select_source(index: int, e=None):
        player_inst._subtitle_selection = index
        _close_dialog()
        player_inst.apply_subtitle(index)

    async def _pick_local(e=None):
        _close_dialog()
        # The player owns the pick (boot-singleton picker + honest snacks);
        # the dialog just hands the tap over.
        await player_inst._pick_subtitle_file()

    rows: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.SUBTITLES_ROUNDED, size=20),
            title=ft.Text("Auto", size=14, weight=ft.FontWeight.W_500),
            subtitle=ft.Text("The source's default track", size=11),
            trailing=_check_icon(active_sub == "auto"),
            # flet on_click handlers are SYNC — an async def here produced
            # "coroutine was never awaited" and the tap did nothing.
            on_click=lambda e: player_inst._run_async(_select_auto),
        ),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.SUBTITLES_OFF_ROUNDED, size=20),
            title=ft.Text("Off", size=14, weight=ft.FontWeight.W_500),
            subtitle=ft.Text("Disabled", size=11),
            trailing=_check_icon(active_sub is None),
            on_click=lambda e: player_inst._run_async(_select_off),
        ),
    ]
    for i, track in enumerate(player_inst.subtitles):
        rows.append(
            ft.ListTile(
                dense=True,
                leading=ft.Icon(ft.Icons.LANGUAGE_ROUNDED, size=18),
                title=ft.Text(track.get("label") or f"Track {i + 1}", size=14),
                trailing=_check_icon(active_sub == i),
                on_click=lambda e, idx=i: player_inst._run_async(_select_source, idx),
            )
        )
    rows.append(
        ft.ListTile(
            leading=ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=20),
            title=ft.Text("Load Local File…", size=14, weight=ft.FontWeight.W_500),
            subtitle=ft.Text("Select .srt or .vtt", size=11),
            trailing=_check_icon(active_sub == "local"),
            on_click=lambda e: player_inst._run_async(_pick_local),
        )
    )

    dialog = ft.AlertDialog(
        title=ft.Text("Subtitles", size=15, weight=ft.FontWeight.W_700),
        content_padding=ft.Padding(0, 8, 0, 0),
        inset_padding=ft.Padding(20, 24, 20, 16),
        content=ft.Column(
            controls=rows,
            tight=True,
            spacing=2,
            scroll=ft.ScrollMode.AUTO,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=_close_dialog),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    try:
        page = player_inst.safe_page or player_inst._page()
        if page is not None:
            page.show_dialog(dialog)
    except Exception as ex:
        logger.warning("Failed to show subtitle options dialog: %s", ex)


async def open_player_settings(player_inst):
    """Player settings: Stream (quality/audio) + Video Fit + Subtitle size.

    Populated from the already-probed variant/track caches so the dialog
    opens instantly, refreshed in the background.
    """
    if not hasattr(player_inst, "_current_variant"):
        player_inst._current_variant = None
    if not hasattr(player_inst, "_current_audio"):
        player_inst._current_audio = None

    has_variants = (
        getattr(player_inst, "_variants_cache", None) is not None
        and len(player_inst._variants_cache) > 1
    )
    has_audio = (
        getattr(player_inst, "_audio_tracks_cache", None) is not None
        and len(player_inst._audio_tracks_cache) >= 2
    )

    stream_header = ft.Text(
        "Stream (Quality & Audio)",
        size=13,
        weight=ft.FontWeight.W_600,
        color=AppColors.PRIMARY,
        visible=has_variants or has_audio,
    )
    stream_divider = ft.Divider(visible=has_variants or has_audio)

    quality_dd = ft.Dropdown(
        label="Quality",
        value=(
            "auto"
            if player_inst._current_variant is None
            else str(player_inst._current_variant)
        ),
        options=(
            [ft.dropdown.Option("auto", "Auto (Adaptive)")]
            + [
                ft.dropdown.Option(str(v["index"]), v["label"])
                for v in (getattr(player_inst, "_variants_cache", []) or [])
            ]
            if has_variants
            else [ft.dropdown.Option("auto", "Auto (Adaptive)")]
        ),
        width=240,
        visible=has_variants,
        on_select=lambda e: player_inst._run_async(
            player_inst.apply_variant,
            None if e.control.value == "auto" else int(e.control.value),
        ),
    )
    audio_dd = ft.Dropdown(
        label="Audio Track",
        value=(
            "default"
            if player_inst._current_audio is None
            else player_inst._current_audio
        ),
        options=(
            [ft.dropdown.Option("default", "Default")]
            + [
                ft.dropdown.Option(
                    t["name"],
                    t["name"] + (f" ({t['language']})" if t["language"] else ""),
                )
                for t in (getattr(player_inst, "_audio_tracks_cache", []) or [])
            ]
            if has_audio
            else [ft.dropdown.Option("default", "Default")]
        ),
        width=240,
        visible=has_audio,
        on_select=lambda e: player_inst._run_async(
            player_inst.apply_audio,
            None if e.control.value == "default" else e.control.value,
        ),
    )

    async def _refresh_stream_options():
        try:
            variants = await player_inst.list_variants() or []
            tracks = await player_inst.list_audio_tracks() or [] if variants else []
        except Exception:
            return
        has_q = len(variants) > 1
        has_a = len(tracks) >= 2
        quality_dd.visible = has_q
        if has_q:
            quality_dd.options = [ft.dropdown.Option("auto", "Auto (Adaptive)")] + [
                ft.dropdown.Option(str(v["index"]), v["label"]) for v in variants
            ]
            quality_dd.value = (
                "auto"
                if player_inst._current_variant is None
                else str(player_inst._current_variant)
            )
        audio_dd.visible = has_a
        if has_a:
            audio_dd.options = [ft.dropdown.Option("default", "Default")] + [
                ft.dropdown.Option(
                    t["name"],
                    t["name"] + (f" ({t['language']})" if t["language"] else ""),
                )
                for t in tracks
            ]
            audio_dd.value = (
                "default"
                if player_inst._current_audio is None
                else player_inst._current_audio
            )
        stream_header.visible = has_q or has_a
        stream_divider.visible = has_q or has_a
        try:
            stream_header.update()
            quality_dd.update()
            audio_dd.update()
            stream_divider.update()
        except Exception:
            pass

    def _change_fit(e):
        player_inst.set_fit(str(e.control.value).lower())

    def _change_subtitle_size(e):
        with contextlib.suppress(TypeError, ValueError):
            player_inst.set_subtitle_size(int(e.control.value))

    def _close_dialog(e=None):
        try:
            dialog.open = False
            page = player_inst.safe_page or player_inst._page()
            if page is not None:
                page.update()
        except Exception:
            pass

    dialog = ft.AlertDialog(
        title=ft.Text(
            "Player Settings",
            size=16,
            weight=ft.FontWeight.BOLD,
        ),
        content=ft.Column(
            controls=[
                stream_header,
                quality_dd,
                audio_dd,
                stream_divider,
                ft.Text(
                    "Screen Aspect Ratio",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                ),
                ft.Dropdown(
                    label="Video Fit",
                    value=getattr(player_inst.video.fit, "name", "CONTAIN").lower(),
                    options=[
                        ft.dropdown.Option("contain", "Fit to Screen (Contain)"),
                        ft.dropdown.Option("cover", "Crop to Fill (Cover)"),
                        ft.dropdown.Option("fill", "Stretch to Fill (Fill)"),
                    ],
                    on_select=_change_fit,
                    width=240,
                ),
                ft.Divider(),
                ft.Text(
                    "Subtitles",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.PRIMARY,
                ),
                ft.Dropdown(
                    label="Subtitle Size",
                    value=str(player_inst._subtitle_size()),
                    options=[
                        ft.dropdown.Option(str(s), f"{s}px")
                        for s in player_inst.SUBTITLE_SIZES
                    ],
                    on_select=_change_subtitle_size,
                    width=240,
                ),
                ft.ListTile(
                    dense=True,
                    leading=ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=18),
                    title=ft.Text("Load from file…", size=13),
                    subtitle=ft.Text("Use an .srt/.vtt from the device", size=11),
                    on_click=lambda e: (
                        _close_dialog(),
                        spawn(player_inst._pick_subtitle_file(), name="pick-subtitle"),
                    ),
                ),
            ],
            tight=True,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
        actions=[
            ft.TextButton("Done", on_click=_close_dialog),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    try:
        page = player_inst.safe_page or player_inst._page()
        if page is not None:
            page.show_dialog(dialog)
            page.run_task(_refresh_stream_options)
    except Exception as ex:
        logger.warning("Failed to show player settings dialog: %s", ex)


def handle_stream_complete(player_inst, e: ft.ControlEvent):
    """Handle stream completion: auto-advance at a real ending (the shell's
    on_next), reconnect a mid-stream stall, else surface the error."""
    # Finite VOD streams that reach the end should not reconnect — the
    # shell's on_next picks the next episode.
    dur = getattr(player_inst, "_last_duration", 0.0)
    pos = getattr(player_inst, "_last_position", 0.0)
    if (
        isinstance(dur, (int, float))
        and isinstance(pos, (int, float))
        and dur > 0
        and pos >= max(0.0, dur - 5.0)
    ):
        if player_inst.on_next is not None:
            player_inst.on_next()
        return

    if re.match(r"https?://", player_inst.resource):
        if player_inst._reconnect_count < STREAM_RECONNECT_MAX:
            player_inst._reconnect_count += 1
            player_inst._show_progress(
                f"Reconnecting stream ({player_inst._reconnect_count}/{STREAM_RECONNECT_MAX})..."
            )
            try:
                page = player_inst.safe_page or player_inst._page()
                if page is not None:
                    page.run_task(reconnect_stream, player_inst)
            except Exception:
                pass
        else:
            player_inst._show_final_error("Stream ended unexpectedly. Retry or go back.")


async def reconnect_stream(player_inst):
    """Attempt live stream reconnection."""
    if player_inst._is_closing:
        return

    try:
        if player_inst.video:
            player_inst.video.playlist = [
                fv.VideoMedia(player_inst.resource, http_headers=player_inst.http_headers),
            ]
            player_inst.video.update()
            await player_inst.video.play()
            player_inst._start_watchdog()
    except Exception as ex:
        logger.debug("Failed to reconnect stream: %s", ex)
        player_inst._show_final_error()
