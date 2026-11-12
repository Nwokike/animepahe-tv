"""Control builders for ImmersivePlayer (KTV skeleton, white buttons)."""

import flet as ft
import flet_video as fv

from core.theme import AppColors


def build_player_controls(player_inst) -> fv.AdaptiveVideoControls:
    """Build adaptive player controls for touch and TV/Desktop modes.

    Every button is WHITE (the owner's call — the old ash-grey icons read
    as disabled). Shared chip instances ride BOTH control branches: only
    one branch renders per platform, so sharing is safe (KTV ships it).
    """
    speed_container = ft.Container(
        content=player_inst.speed_text,
        padding=ft.Padding(6, 3, 6, 3),
        border_radius=4,
        ink=True,
        on_click=lambda e: player_inst._run_async(player_inst._cycle_speed),
    )
    speed_container.tab_index = 0
    player_inst.speed_container = speed_container

    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
        icon_color=ft.Colors.WHITE,
        tooltip="Back",
        on_click=lambda e: player_inst._run_async(player_inst._on_back),
    )
    # Full title, no width machinery — the bar clips whatever doesn't fit.
    title_text = ft.Text(
        player_inst.title or "Now Playing",
        color=ft.Colors.WHITE,
        weight=ft.FontWeight.W_500,
    )

    # In-player toast chip. It lives INSIDE the video controls because the
    # fullscreen route (pushed by media_kit on the root navigator, above the
    # whole Flet page tree) re-renders these same controls — the only Flet
    # surface visible in fullscreen. Overlays placed next to the Video in a
    # Stack are covered in fullscreen; this chip is not.
    toast_text = ft.Text(
        "",
        color=ft.Colors.WHITE,
        size=13,
        weight=ft.FontWeight.W_500,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    toast_chip = ft.Container(
        content=toast_text,
        bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
        border_radius=8,
        padding=ft.Padding(12, 6, 12, 6),
        visible=False,
    )
    player_inst.toast_chip = toast_chip
    player_inst.toast_text = toast_text

    # Skip intro/outro chip: same slot as the toast (one shows at a time —
    # the toast replaces it visually and both hide themselves).
    skip_chip = ft.Container(
        content=ft.Text(
            "Skip Intro",
            size=13,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
        ),
        padding=ft.Padding(14, 8, 14, 8),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.75, ft.Colors.BLACK),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.4, ft.Colors.WHITE)),
        ink=True,
        visible=False,
        on_click=lambda e: player_inst._run_async(player_inst._on_skip_chip),
    )
    player_inst.skip_chip = skip_chip

    # Toast + skip overlay the title slot so they need no extra bar width.
    title_slot = ft.Stack(
        controls=[title_text, toast_chip, skip_chip],
        alignment=ft.Alignment.CENTER,
    )

    # Quality button (bottom controls): appears once stream options are
    # known (the resolution already fetched the master's variants, and the
    # probe refreshes/extends them). The row stays MOUNTED as the content
    # and the button is `visible=False` until then — a `content=None`
    # Container inside a flet_video control bar throws
    # "type 'Null' is not a subtype of type 'Control'" on the 1.1.0 line.
    quality_text = ft.Text(
        "—",
        size=11,
        color=ft.Colors.WHITE,
        weight=ft.FontWeight.W_600,
        no_wrap=True,
    )
    quality_row = ft.Row(
        controls=[
            ft.Icon(ft.Icons.HIGH_QUALITY, size=14, color=ft.Colors.WHITE),
            quality_text,
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    quality_btn = ft.Container(
        content=quality_row,
        visible=False,
        padding=0,
        border_radius=4,
        ink=True,
        tooltip="Quality",
        on_click=lambda e: player_inst._run_async(player_inst.open_player_settings),
    )
    player_inst.quality_btn = quality_btn
    player_inst.quality_row = quality_row
    player_inst.quality_text = quality_text

    # Audio track button: appears when the stream has multiple selectable
    # audio renditions.
    audio_text = ft.Text(
        "Audio",
        size=11,
        color=ft.Colors.WHITE,
        weight=ft.FontWeight.W_600,
        no_wrap=True,
    )
    audio_row = ft.Row(
        controls=[
            ft.Icon(ft.Icons.AUDIOTRACK_ROUNDED, size=14, color=ft.Colors.WHITE),
            audio_text,
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    audio_btn = ft.Container(
        content=audio_row,
        visible=False,
        padding=0,
        border_radius=4,
        ink=True,
        tooltip="Audio Track",
        on_click=lambda e: player_inst._run_async(player_inst.open_player_settings),
    )
    player_inst.audio_btn = audio_btn
    player_inst.audio_row = audio_row
    player_inst.audio_text = audio_text

    btn_style = ft.ButtonStyle(
        padding=ft.Padding(0, 0, 0, 0),
        visual_density=ft.VisualDensity.COMPACT,
    )

    def _icon_btn(icon, tooltip, on_click):
        return ft.IconButton(
            icon=icon,
            icon_color=ft.Colors.WHITE,
            icon_size=18,
            padding=0,
            visual_density=ft.VisualDensity.COMPACT,
            style=btn_style,
            tooltip=tooltip,
            on_click=on_click,
        )

    # Next / previous episode (shell-owned callbacks; hidden when the shell
    # did not provide them — a single-episode anime shows neither).
    prev_btn = (
        _icon_btn(
            ft.Icons.SKIP_PREVIOUS_ROUNDED,
            "Previous episode",
            lambda e: player_inst.on_previous(),
        )
        if player_inst.on_previous is not None
        else None
    )
    next_btn = (
        _icon_btn(
            ft.Icons.SKIP_NEXT_ROUNDED,
            "Next episode",
            lambda e: player_inst.on_next(),
        )
        if player_inst.on_next is not None
        else None
    )

    sub_btn = _icon_btn(
        ft.Icons.SUBTITLES_ROUNDED,
        "Subtitles",
        lambda e: player_inst._run_async(player_inst.open_subtitles),
    )

    camera_btn = _icon_btn(
        ft.Icons.CAMERA_ALT_ROUNDED,
        "Take Snapshot",
        lambda e: player_inst._run_async(player_inst._take_screenshot),
    )

    settings_btn = _icon_btn(
        ft.Icons.SETTINGS_ROUNDED,
        "Player Settings",
        lambda e: player_inst._run_async(player_inst.open_player_settings),
    )

    return fv.AdaptiveVideoControls(
        # --- Mobile (touch) ---
        material=fv.MaterialVideoControls(
            visible_on_mount=True,
            display_seek_bar=True,
            seek_on_double_tap=True,
            seek_gesture=True,
            volume_gesture=True,
            brightness_gesture=True,
            speed_up_on_long_press=True,
            speed_up_factor=2.0,
            controls_transition_duration=ft.Duration(milliseconds=300),
            seek_bar_position_color=AppColors.PRIMARY,
            button_bar_button_color=ft.Colors.WHITE,
            button_bar_button_size=18.0,
            primary_button_bar=[
                fv.VideoSpacer(flex=2),
                fv.VideoPlayOrPauseButton(icon_size=48.0),
                fv.VideoSpacer(flex=2),
            ],
            top_button_bar_margin=ft.Margin(16, 35, 16, 0),
            top_button_bar=[
                back_btn,
                title_slot,
            ],
            bottom_button_bar=[
                fv.VideoPositionIndicator(
                    text_style=ft.TextStyle(size=12, color=ft.Colors.WHITE),
                ),
                fv.VideoSpacer(),
                *([prev_btn] if prev_btn else []),
                *([next_btn] if next_btn else []),
                speed_container,
                quality_btn,
                audio_btn,
                camera_btn,
                sub_btn,
                settings_btn,
                fv.VideoFullscreenButton(icon_color=ft.Colors.WHITE, icon_size=18.0),
            ],
        ),
        # --- Desktop / TV (keyboard + D-pad) ---
        material_desktop=fv.MaterialDesktopVideoControls(
            visible_on_mount=True,
            display_seek_bar=True,
            modify_volume_on_scroll=True,
            toggle_fullscreen_on_double_press=False,
            play_and_pause_on_tap=False,
            hide_mouse_on_controls_removal=False,
            button_bar_button_size=18.0,
            primary_button_bar=[
                fv.VideoSpacer(flex=2),
                fv.VideoPlayOrPauseButton(icon_size=32.0),
                fv.VideoSpacer(flex=2),
            ],
            top_button_bar=[
                back_btn,
                title_slot,
            ],
            bottom_button_bar=[
                fv.VideoVolumeButton(slider_width=80, icon_color=ft.Colors.WHITE),
                fv.VideoSpacer(),
                fv.VideoPositionIndicator(
                    text_style=ft.TextStyle(size=12, color=ft.Colors.WHITE),
                ),
                fv.VideoSpacer(),
                *([prev_btn] if prev_btn else []),
                *([next_btn] if next_btn else []),
                speed_container,
                quality_btn,
                audio_btn,
                camera_btn,
                sub_btn,
                settings_btn,
                fv.VideoFullscreenButton(icon_color=ft.Colors.WHITE, icon_size=18.0),
            ],
            seek_bar_position_color=AppColors.PRIMARY,
            seek_bar_buffer_color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
            seek_bar_hover_height=8,
            volume_bar_active_color=AppColors.PRIMARY,
            controls_hover_duration=ft.Duration(seconds=4),
        ),
    )
