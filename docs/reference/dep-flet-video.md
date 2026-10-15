# dep-flet-video — flet-video 0.85.3 API reference (installed package)

> **Version note (2026-10-15):** compiled against 0.85.3; installed is **flet-video 1.0.4**.
> The API surface below was re-checked against 1.0.4 on 2026-10-13 (swarm audit §3: the
> `controls` dict form, `on_track_change`, `VideoSubtitleTrack.none()/auto()` are all present).
> Install source wins; full refresh in hybrid Phase 5.


> Source of truth: `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\.venv\Lib\site-packages\flet_video\`
> Three files only: `video.py` (393 lines), `types.py` (1034 lines), `__init__.py` (48 lines).
> Verified live via `uv run python` from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`:
> `importlib.metadata.version('flet-video') == '0.85.3'`, plus `inspect.signature(Video.__init__)`.
> Every claim below is traceable to a docstring/field/method in those files.
> Claims about what does **not** exist were verified by `grep -rn -i "balance|buffering|on_seek|on_loaded|quality|audio_track"` over the package (no hits except `filter_quality` texture docstring).

---

## 1. Version + backend per platform

- **Version:** `0.85.3` (`flet_video-0.85.3.dist-info`, confirmed via `importlib.metadata`).
- **Native backend is libmpv/mpv — there is no other playback engine in this package.** Evidence is `VideoConfiguration` in `types.py`:
  - `output_driver: Optional[str] = None` — docstring verbatim:
    > "Sets the [--vo](https://mpv.io/manual/stable/#options-vo) property on native backend. The default value is platform dependent: Windows, GNU/Linux, macOS & iOS : `"libmpv"`; Android: `"gpu"`."
  - `hardware_decoding_api: Optional[str] = None` — docstring verbatim:
    > "Sets the [--hwdec](https://mpv.io/manual/stable/#options-hwdec) property on native backend. The default value is platform dependent: Windows, GNU/Linux, macOS & iOS : `"auto"`; Android: `"auto-safe"`."
  - `enable_hardware_acceleration: bool = True` — docstring verbatim:
    > "Whether to enable hardware acceleration. When disabled, may cause battery drain, device heating, and high CPU usage."
  - `mpv_properties: Optional[dict[str, Union[str, int, float, bool]]] = None` — docstring says "Extra mpv/libmpv properties to set on native backends (Windows/macOS/Linux/iOS/Android)" (full text in §6).
- **Web backend exists** (referenced twice, no further detail in these 3 files):
  - `VideoSubtitleTrack.src`: "An absolute local file path (not supported on the web platform)".
  - `Video.take_screenshot(..., include_libass_subtitles ...)`: "ignored on the web backend".
- There is **no per-platform backend selection API** on `Video` itself — the only knobs are `VideoConfiguration.output_driver`, `.hardware_decoding_api`, `.enable_hardware_acceleration`, `.mpv_properties` (all inside `configuration`, not top-level `Video` params).

---

## 2. `Video` constructor — EVERY parameter (type / default / docstring)

Class: `@ft.control("Video") class Video(ft.LayoutControl)` in `video.py`. Docstring: "A control that displays a video from a playlist." Live signature confirmed via `inspect.signature(Video.__init__)` — order below matches source order, then inherited `LayoutControl`/`Control` params (`key, ref, expand, opacity, width/height/left/top/…`, all standard Flet, omitted for brevity).

| # | Parameter | Type | Default | Docstring (verbatim / summarized) |
|---|-----------|------|---------|-----------------------------------|
| 1 | `playlist` | `list[VideoMedia]` | `field(default_factory=list)` (empty) | "A list of `VideoMedia`s representing the video files to be played." |
| 2 | `title` | `str` | `"flet-video"` | "Defines the name of the underlying window & process for native backend. This is visible inside the windows' volume mixer." |
| 3 | `fit` | `ft.BoxFit` | `ft.BoxFit.CONTAIN` | "The box fit to use for the video." |
| 4 | `fill_color` | `ft.ColorValue` | `ft.Colors.BLACK` | "Defines the color used to fill the video background." |
| 5 | `wakelock` | `bool` | `True` | "Whether to acquire wake lock while playing the video. When `True`, device's display will not go to standby/sleep while the video is playing." |
| 6 | `autoplay` | `bool` | `False` | "Whether the video should start playing automatically." |
| 7 | `show_controls` | `Annotated[Optional[bool], V.deprecated(...)]` | `None` | "Whether to show the video player controls." **Deprecated since 0.85.0, delete 0.88.0.** `reason="Use controls=None to hide controls."` During deprecation, `show_controls=False` hides controls even when `controls` is set (see `controls` docstring Note). |
| 8 | `controls` | `Optional[Union[VideoControls, ft.Control, dict[VideoControlsMode, Optional[Union[VideoControls, ft.Control]]]]]` | `field(default_factory=lambda: AdaptiveVideoControls())` | Built-in `VideoControls`, custom Flet `Control`, or `None` to hide. Dict form keys by `VideoControlsMode`: `DEFAULT` used when `NORMAL` missing; `FULLSCREEN` falls back to `NORMAL` then `DEFAULT`; a mode value of `None` hides controls for that mode only. |
| 9 | `fullscreen` | `bool` | `False` | "Whether the video player is presented in fullscreen mode. Set to `True` to enter fullscreen or `False` to exit fullscreen programmatically." |
| 10 | `muted` | `bool` | `False` | "Defines whether the video player should be started in muted state." |
| 11 | `playlist_mode` | `Optional[PlaylistMode]` | `None` | "Represents the mode of playback for the playlist." (`None` behaves as no-repeat; enum in §5.) |
| 12 | `shuffle_playlist` | `bool` | `False` | "Defines whether the playlist should be shuffled." |
| 13 | `volume` | `ft.Number` | `100.0` | Range `0.0–100.0` inclusive, `0.0` muted, `100.0` max. `before_update()` raises `ValueError("volume must be between 0 and 100 inclusive, got ...")` if out of range. |
| 14 | `playback_rate` | `ft.Number` | `1.0` | "Defines the playback rate of the video player." (No range validation in source.) This is the `rate` knob — it is called `playback_rate`, not `rate`. |
| 15 | `alignment` | `ft.Alignment` | `field(default_factory=lambda: ft.Alignment.CENTER)` | "Defines the Alignment of the viewport." |
| 16 | `filter_quality` | `ft.FilterQuality` | `ft.FilterQuality.LOW` | "Filter quality of the texture used to render the video output. Note: Android was reported to show blurry images when using `HIGH`. Prefer `MEDIUM` on this platform." This is a **texture-scaling** filter, not stream quality. |
| 17 | `pause_upon_entering_background_mode` | `bool` | `True` | "Whether to pause the video when application enters background mode." |
| 18 | `resume_upon_entering_foreground_mode` | `bool` | `False` | "Whether to resume the video when application enters foreground mode. Has effect only if `pause_upon_entering_background_mode` is also `True`." |
| 19 | `pitch` | `ft.Number` | `1.0` | "Defines the relative pitch of the video player." |
| 20 | `configuration` | `VideoConfiguration` | `field(default_factory=lambda: VideoConfiguration())` | "Additional configuration for the video player." (All mpv/hardware knobs live here — §5.) |
| 21 | `subtitle_configuration` | `VideoSubtitleConfiguration` | `field(default_factory=lambda: VideoSubtitleConfiguration())` | "Defines the subtitle configuration for the video player." (Styling/visibility — §5.) |
| 22 | `subtitle_track` | `Optional[VideoSubtitleTrack]` | `None` | "Defines the subtitle track for the video player." (`None` = default track handling; use `VideoSubtitleTrack.none()`/`auto()` or an explicit `src` — §5.) |
| 23–30 | `on_load`, `on_enter_fullscreen`, `on_exit_fullscreen`, `on_error`, `on_complete`, `on_track_change`, `on_position_change`, `on_duration_change` | `Optional[ft.ControlEventHandler["Video"]]` | `None` each | See §4 event table. |

**Parameters the task brief names that DO NOT EXIST on `Video` (verified by full-file read + grep):** `rate` (actual name is `playback_rate`), `balance` (no stereo-balance param anywhere), `mute` (actual name is `muted`, start-muted only — no live mute toggle method), `buffering` / buffer-size / cache-size (no such param; cache is only reachable indirectly via `configuration.mpv_properties`), `mpv_properties` as a top-level `Video` param (it lives one level down at `Video.configuration.mpv_properties`).

---

## 3. `VideoMedia` — the playlist item model

`@ft.value class VideoMedia` in `types.py`. Docstring: "Represents a media resource for video playback." Exactly 3 fields, no methods:

| Field | Type | Default | Docstring |
|-------|------|---------|-----------|
| `resource` | `str` (required) | — | "URI of the media resource." (Used for remote http(s)/HLS URLs and local paths. `playlist_add` raises `ValueError("media has no resource")` if falsy.) |
| `http_headers` | `Optional[dict[str, str]]` | `None` | "HTTP headers to be used for the media resource." — **one sentence, no elaboration.** |
| `extras` | `Optional[dict[str, str]]` | `None` | "Additional metadata for the media resource." (Opaque string map; no documented keys in these files.) |

**`http_headers` for HLS / per-segment question:** the source says only the single sentence above. There is **no documented guarantee** that headers are re-sent on every HLS segment/key/playlist sub-request, no per-segment hook, no separate segment-header field, and no web-vs-native forwarding note — that behavior lives in the (unread here) native/Dart backend, not in these 3 Python files. Practical consequence for the anime app: pass `Referer`/`User-Agent`/cookies via `http_headers` at the `VideoMedia` level and **verify at runtime** (e.g. `on_error` + proxy log) whether protected HLS segment requests carry them; if not, the fallback is `configuration.mpv_properties` (e.g. mpv `http-header-fields`, user-agent options — §6) which is applied at the mpv layer rather than the per-media layer.

**Anything else in the model:** nothing. No duration/title/artwork/track-list/quality-variant fields on `VideoMedia`. Per-episode titles, durations, thumbnails must be kept app-side.

---

## 4. Method / event surface (complete)

### 4a. Playback + playlist methods (`video.py`, all `async`, all via `self._invoke_method(...)` except validation)

| Method | Signature | Docstring / behavior | Notes for anime app |
|--------|-----------|----------------------|---------------------|
| `play` | `async def play(self)` | "Starts playing the video." → `_invoke_method("play")` | Pair with `autoplay=True` for auto-start. |
| `pause` | `async def pause(self)` | "Pauses the video player." | Honors `pause_upon_entering_background_mode` automatically. |
| `play_or_pause` | `async def play_or_pause(self)` | "Cycles between play and pause states … plays if paused and pauses if playing." | Ideal single play/pause button callback. |
| `stop` | `async def stop(self)` | "Stops the video player." | |
| `next` | `async def next(self)` | "Jumps to the next `VideoMedia` in the `playlist`." | Episode-next. Respects `playlist_mode`/`shuffle_playlist`. |
| `previous` | `async def previous(self)` | "Jumps to the previous `VideoMedia` in the `playlist`." | Episode-prev. |
| `seek` | `async def seek(self, position: ft.DurationValue)` | "Seeks the currently playing `VideoMedia` … at the specified `position`." → `_invoke_method("seek", {"position": position})` | `ft.DurationValue` = `ft.Duration` or int ms (live signature shows `Union[Duration, int]`). No `on_seek` event exists — observe via `on_position_change` after seeking. |
| `jump_to` | `async def jump_to(self, media_index: int)` | "Jumps to the `VideoMedia` at the specified `media_index`." Python-side `IndexError("media_index is out of range")` if `not (-len <= i < len)`; negative indexes normalized (`len + i`) because "dart doesn't support negative indexes". | Episode picker: `await video.jump_to(episode_index)`. |
| `playlist_add` | `async def playlist_add(self, media: VideoMedia)` | "Appends/Adds the provided `media` to the `playlist`." **Deprecated 0.85.0, delete 0.88.0** — `reason="Use playlist.append(media) instead."` Raises `ValueError("media has no resource")` if empty. Appends locally (`self.playlist.append(media)`), no backend round-trip in this file. | Use `video.playlist.append(...)` + `update()`. |
| `playlist_remove` | `async def playlist_remove(self, media_index: int)` | "Removes the provided `media` from the `playlist`." **Deprecated 0.85.0, delete 0.88.0** — use `playlist.pop(media_index)`. Same negative-index normalization + `IndexError`. Pops locally. | Use `video.playlist.pop(i)` + `update()`. |
| `is_playing` | `async def is_playing(self) -> bool` | "Returns `True` if the video player is currently playing, `False` otherwise." | Poll or cache from UI state; no `on_playing_change` event exists. |
| `is_completed` | `async def is_completed(self) -> bool` | "Returns `True` if video player has reached the end of the currently playing media, `False` otherwise." | Prefer `on_complete` event over polling. |
| `get_duration` | `async def get_duration(self) -> ft.Duration` | "Returns the duration of the currently playing media." | Pair with `on_duration_change` (event-driven) instead of polling. |
| `get_current_position` | `async def get_current_position(self) -> ft.Duration` | "Returns the current position of the currently playing media." | Pair with `on_position_change`; used for resume-position persistence. |
| `take_screenshot` | `async def take_screenshot(self, format: Optional[str] = "image/png", include_libass_subtitles: bool = False) -> Optional[bytes]` | "Captures a screenshot of the current video frame." `format`: `"image/png"`, `"image/jpeg"`, or `None` (raw BGRA on native); else `ValueError("format must be one of ...")`. `include_libass_subtitles`: native-only, "requires libass support …, ignored on the web backend". Returns `None` "if the current backend cannot capture a video frame". | Thumbnail/preview feature; not playback-critical. |

**Missing vs. the brief's expectations (verified absent):** no `get_current_position`-companion setter other than `seek`; no `playback_rate` setter method (rate is a **property** `video.playback_rate = x` + `update()`); no quality-switching / variant / rendition / audio-track / subtitle-track-switch **method** — track switching is done by reassigning the `subtitle_track` property (or rebuilding `playlist`), not by a dedicated call; no `duration`/`position` **properties** (only the async getters + change events).

### 4b. Events — every handler, signature, payload, when it fires

All typed `Optional[ft.ControlEventHandler["Video"]]` (`Callable[[], Any] | Callable[[Event[Video]], Any] | None`), default `None`. Handler receives a Flet `Event`; payload (if any) is in `event.data`.

| Handler | `event.data` | Fires when (per docstring) |
|---------|--------------|----------------------------|
| `on_load` | — (no documented payload) | "Fires when the video player is initialized and ready for playback." **Note:** named `on_load`, not `on_loaded` — the brief's `on_loaded` does not exist. |
| `on_enter_fullscreen` | — | "Fires when the video player enters fullscreen." |
| `on_exit_fullscreen` | — | "Fires when the video player exits fullscreen" |
| `on_error` | error info string/object ("contains information about the error") | "Fires when an error occurs." — the only error-reporting channel; log `event.data` for stream/debug diagnostics. |
| `on_complete` | — | "Fires when a video player completes." — episode-ended → autoplay-next hook point. |
| `on_track_change` | index of new track ("contains the index of the new track") | "Fires when a video track changes." — playlist advance (`next`/`previous`/`jump_to`/auto-advance). |
| `on_position_change` | current position as `flet.Duration` | "Fires when the current playback position changes." — progress bar + watch-history persistence. Fires continuously during playback. |
| `on_duration_change` | current duration as `flet.Duration` | "Fires when the current media duration changes." — fires once media metadata resolves; use to set slider max. |

**Events the brief names that DO NOT EXIST:** `on_loaded` (actual: `on_load`), `on_seek` (no seek-acknowledgement event — watch `on_position_change`), generic `on_event`/buffering-state events (none in this version).

---

## 5. Controls, subtitles, configuration

### 5a. `AdaptiveVideoControls` vs `MaterialVideoControls` vs `MaterialDesktopVideoControls`

Base: `@ft.value class VideoControls` with fixed `_type` discriminator per subclass. `Video.controls` defaults to `AdaptiveVideoControls()`.

- **`AdaptiveVideoControls`** (`_type="adaptive"`, fields `material: Optional[MaterialVideoControls] = None`, `material_desktop: Optional[MaterialDesktopVideoControls] = None`): "Platform-adaptive video controls. Adaptive controls select the controls implementation at runtime based on the current `Page.platform`: Android and iOS use Material controls; macOS, Windows, and Linux use Material desktop controls; **other platforms show no built-in controls**." Configure via `.material` / `.material_desktop` (omitted = defaults of that family).
- **`MaterialVideoControls`** (`_type="material"`): "Touch-oriented Material video controls." Key customizables:
  - **Behavior/gestures:** `display_seek_bar` (True), `automatically_imply_skip_next/previous_button` (True each — auto-added when playlist > 1), `volume_gesture` (False), `brightness_gesture` (False), `seek_gesture` (False), `gestures_enabled_while_controls_visible` (True), `seek_on_double_tap` (False) + `seek_on_double_tap_enabled_while_controls_visible` (True) + `seek_on_double_tap_layout_taps_ratios`/`_widget_ratios` (both `[1,1,1]`) + `seek_on_double_tap_backward/forward_duration` (both `10000` ms), `speed_up_on_long_press` (False) + `speed_up_factor` (2.0), `vertical_gesture_sensitivity` (100), `horizontal_gesture_sensitivity` (1000), `visible_on_mount` (False).
  - **Generic:** `padding` (None), `controls_hover_duration` (3000 ms), `controls_transition_duration` (300 ms), `initial_volume`/`initial_brightness` (0.5 each, 0.0–1.0, gesture-indicator seeds), `backdrop_color` (`#66000000`).
  - **Button bars** (`primary_button_bar` / `top_button_bar` / `bottom_button_bar`, each `Optional[list[Union[ft.Control, VideoBarItem]]]`; `None` = native default, `[]` = hide): material primary default = `[Spacer(2), SkipPrevious, Spacer, PlayOrPause(icon_size=48), Spacer, SkipNext, Spacer(2)]`; top default = empty; bottom default = `[PositionIndicator, Spacer, FullscreenButton]`. Margins/sizes/colors: `top_button_bar_margin` (sym h16), `bottom_button_bar_margin` (left16/right8), `button_bar_height` (56), `button_bar_button_size` (24), `button_bar_button_color` (`#FFFFFFFF`).
  - **Seek bar:** `seek_bar_margin` (0), `seek_bar_height` (2.4), `seek_bar_container_height` (36), `seek_bar_color`/`seek_bar_buffer_color` (`#3DFFFFFF`), `seek_bar_position_color`/`seek_bar_thumb_color` (`#FFFF0000`), `seek_bar_thumb_size` (12.8), `seek_bar_alignment` (BOTTOM_CENTER).
  - **Subtitles:** `shift_subtitles_on_controls_visibility_change` (False on touch).
- **`MaterialDesktopVideoControls`** (`_type="materialDesktop"`): "Desktop-oriented Material video controls." Differences that matter:
  - Desktop behaviors instead of touch gestures: `modify_volume_on_scroll` (True), `toggle_fullscreen_on_double_press` (True), `hide_mouse_on_controls_removal` (False), `play_and_pause_on_tap` (False); `controls_transition_duration` 150 ms (vs 300).
  - Bottom-bar default **differs**: `[SkipPrevious, PlayOrPause, SkipNext, Spacer, PositionIndicator, FullscreenButton, VolumeButton]` (primary/top default to empty).
  - Extra seek-bar knobs: `seek_bar_transition_duration` (300), `seek_bar_thumb_transition_duration` (150), `seek_bar_margin` (sym h16, vs 0), `seek_bar_height` (3.2), `seek_bar_hover_height` (5.6), `seek_bar_hover_color` (`#3DFFFFFF`).
  - Extra **volume-bar** section: `volume_bar_color` (`#3DFFFFFF`), `volume_bar_active_color`/`volume_bar_thumb_color` (`#FFFFFFFF`), `volume_bar_thumb_size` (12.0), `volume_bar_transition_duration` (150).
  - `shift_subtitles_on_controls_visibility_change` defaults **True** (vs False).
- **Bar items** (`VideoBarItem` subclasses, composable into the three bars, freely mixed with arbitrary `ft.Control`): `VideoPlayOrPauseButton` (icon_size/icon_color), `VideoSkipNextButton`/`VideoSkipPreviousButton`/`VideoFullscreenButton` (icon/icon_size/icon_color), `VideoPositionIndicator` (text_style), `VideoSpacer` (`flex: int = 1`), `VideoVolumeButton` (icon_size/icon_color, volume_mute/low/high_icon, slider_width) — with the caveat docstring: "**This item is currently rendered only by `MaterialDesktopVideoControls`**."
- `VideoControlsMode` enum (`NORMAL="normal"`, `FULLSCREEN="fullscreen"`, `DEFAULT="default"`) drives the `Video.controls` dict form (§2 row 8).

### 5b. `VideoSubtitleConfiguration` / `VideoSubtitleTrack` — external subtitles

- **`VideoSubtitleConfiguration`** (`@ft.value`, styling only): `text_style: ft.TextStyle` (default height 1.4, size 32.0, letter/color WHITE, weight NORMAL, bgcolor BLACK_54), `text_scale_factor: ft.Number = 1.0`, `text_align: ft.TextAlign = CENTER`, `padding` (default left16/top0/right16/bottom24), `visible: bool = True`.
- **`VideoSubtitleTrack`** (`@ft.value`): required `src: str` + optional `title`/`language` + media-probe-ish optional fields (`channels_count, channels, sample_rate, fps, bitrate, rotate, par, audio_channels, album_art, codec, decoder` — all default `None`; despite living on the subtitle class they read as stream metadata echoes from the backend, not inputs you set).
  - `src` docstring verbatim — this is the external-subtitle answer:
    > "Supported values: A URL (e.g. "https://example.com/subs.srt" or "www.example.com/sub.vtt"); An absolute local file path (not supported on the web platform); A raw subtitle text string (e.g. the full contents of an SRT/VTT file)".
  - Classmethods: `VideoSubtitleTrack.none()` → `src="none"` ("No subtitle track. Disables subtitle output."); `VideoSubtitleTrack.auto()` → `src="auto"` ("Default subtitle track. Selects the first subtitle track.").
  - Wiring: assign to `Video.subtitle_track` (e.g. `video.subtitle_track = VideoSubtitleTrack(src="https://…/ep12-en.vtt", title="English", language="en")` then `await video.update_async()` / `video.update()`); visibility/style via `Video.subtitle_configuration`; shift-on-controls via the controls classes above.

### 5c. `VideoConfiguration` (all tunables, with defaults)

`@ft.value class VideoConfiguration`, docstring "Additional configuration for video playback.": `output_driver` (None → libmpv / gpu per platform), `hardware_decoding_api` (None → auto / auto-safe), `enable_hardware_acceleration` (True), `width: Optional[ft.Number]` (None, "fixed width for the video output"), `height: Optional[ft.Number]` (None), `scale: ft.Number = 1.0` ("Specifying this option will cause `width` & `height` to be ignored"), `mpv_properties` (None — §6).

---

## 6. `mpv_properties` — quoted docstring + what can be tuned

Field: `mpv_properties: Optional[dict[str, Union[str, int, float, bool]]] = None` on `VideoConfiguration`. Full docstring, quoted verbatim:

> "Extra mpv/libmpv properties to set on native backends (Windows/macOS/Linux/iOS/Android). The keys are mpv option/property names without the leading `--`. Values can be `str`, `int`, `float` or `bool`. All values are converted to strings before being passed to mpv; boolean values are converted to `"yes"` / `"no"`. Full list of mpv options: https://mpv.io/manual/stable/#options. Example:
> ```python
> >>> VideoConfiguration(
>         mpv_properties={
>             "profile": "low-latency",   # --profile=low-latency
>             "untimed": True,            # --untimed
>             "volume": 80,               # --volume=80
>         }
>     )
> ```"

What this means for the brief's examples (`ytdl`, `cache`, `demuxing`, `user-agent`): the package **does not enumerate any specific mpv key** — no `ytdl`/`cache`/`demuxer`/`user-agent` string appears anywhere in the 3 files (grep-verified). **Any** mpv option from the linked manual can be passed by bare name (no `--` prefix), with `bool → "yes"/"no"` coercion. Concretely for an anime/HLS app this is the escape hatch for things with no first-class API: e.g. `{"http-header-fields": "Referer: https://…", "user-agent": "…", "cache": "yes", "demuxer-max-bytes": …, "ytdl": False/True, …}` — but key names, value formats, and platform support come from the **mpv manual**, not from this package, and must be validated at runtime via `on_error` (misspelled keys fail silently or error depending on the backend, and none of this applies to the web backend).

---

## 7. What we are NOT using that matters for an anime player

Facts about gaps/latent features, each tied to the source:

1. **External subtitle loading — available, likely unused.** `VideoSubtitleTrack(src=<url|abs path|raw SRT/VTT text>, title=, language=)` + `Video.subtitle_track` + `VideoSubtitleConfiguration` (style/visibility) + `none()`/`auto()` exist (§5b). If the app only plays raw streams today, enabling per-episode external subs is a property assignment, not a new dependency.
2. **Audio-track selection API — does not exist in this version.** No `audio_track` field, no `set_audio_track`/`get_audio_tracks` method, no `on_audio_change` event in either file. Multi-audio (JP/EN dub) anime sources can only be handled by rebuilding the playlist with a different stream or via raw `mpv_properties` (e.g. mpv `aid` selection), both unverified from these files alone.
3. **Buffering configuration — no first-class API.** No `buffering`, `buffer_size`, `cache_*`, `preload` param on `Video` or `VideoConfiguration` (grep-verified). Only indirectly tunable through `mpv_properties` keys from the mpv manual (native only), and the only buffering-adjacent UI is `seek_bar_buffer_color` (pure cosmetics in both Material families). Startup latency / rebuffering on slow HLS cannot be tuned from typed API.
4. **Wakelock — free, on by default.** `Video.wakelock: bool = True` ("device's display will not go to standby/sleep while the video is playing"). Keep default `True` for long episodes; only set `False` for preview/thumbnail players.
5. **Playback-rate persistence — property, not method; app must persist.** `playback_rate: ft.Number = 1.0` is a settable property (assign + `update()`), there is no `set_rate()` method and no built-in persistence — remember-per-anime speed (e.g. 1.25× for fillers) must be stored app-side and reapplied on `on_load`/`on_track_change`.
6. **Quality switching mechanics — no rendition API; rebuild-or-swap pattern.** No `quality`/`bitrate`/`variant`/`rendition` field or method on `Video`/`VideoMedia` (grep-verified). HLS multi-variant URLs therefore switch by either (a) rebuilding `video.playlist` around a new `VideoMedia(resource=<variant-or-master-url>)` and `jump_to`/`seek` back to the saved `get_current_position()`, or (b) pointing the single playlist entry at a different (master vs. pinned-variant) URL. `filter_quality` is **not** stream quality (it is texture-scaling: LOW default, MEDIUM advised on Android). `VideoConfiguration.scale/width/height` control output size, not bitrate.
7. **Adjacent unused-but-relevant knobs worth knowing:** `muted` (start-muted) + desktop `VideoVolumeButton`/scroll-volume (no live mute method — volume changes go through the `volume` 0–100 property); `pitch` (relative pitch, default 1.0); `pause_upon_entering_background_mode=True` / `resume_upon_entering_foreground_mode=False` (background behavior is already sensible for a phone player); `fullscreen` property + `on_enter/exit_fullscreen` (programmatic fullscreen); `title` (Windows volume-mixer label); `take_screenshot(format="image/png"|"image/jpeg"|None, include_libass_subtitles=False)` (episode thumbnails); deprecated `show_controls`/`playlist_add`/`playlist_remove` (avoid — use `controls=None` and direct `playlist.append/pop`, removal slated for 0.88.0).

---

## 8. App improvement opportunities

Every item below cites a verified source (file + signature from §§1-7).
Items that could not be verified against the installed package are separated
at the end. Ordered by expected impact on the anime player.

1. **Load per-episode external subtitles via `VideoSubtitleTrack(src=...)`.**
   `VideoSubtitleTrack(src: str, title: Optional[str] = None, language: Optional[str] = None, ...)`
   (`types.py:910-994`) accepts a subtitle URL, an absolute local path
   (non-web), or raw SRT/VTT text (`src` docstring, §5b); assign to
   `Video.subtitle_track: Optional[VideoSubtitleTrack]` (`video.py:193-195`)
   and style with `Video.subtitle_configuration: VideoSubtitleConfiguration`
   (`video.py:185-190`; defaults: 32 px white-on-black54, centered, visible).
   `VideoSubtitleTrack.auto()` / `.none()` (`types.py:985-993`) give
   first-track vs. off for free. For sources that ship subtitle tracks
   alongside video URLs, this is the highest-impact gap to close: it turns
   "raw video only" episodes into fully-subtitled playback with one property
   assignment + `update()`, no new dependency. Improves the player surface
   (subtitle rendering, per-language selection via `title`/`language`).
2. **Implement quality switching as playlist rebuild around variant URLs.**
   No rendition/variant/bitrate field or method exists on `Video`/`VideoMedia`
   (grep-verified absent, §7.6) — so the supported mechanic is: save position
   via `async def get_current_position(self) -> ft.Duration`
   (`video.py:351-355`), replace `video.playlist` with
   `VideoMedia(resource=<other-variant-or-master-URL>, http_headers=...)`
   (`types.py:59-70`), `await video.jump_to(0)` (`video.py:285-298`), then
   `await video.seek(saved_position)` (`video.py:275-283`). `on_track_change`
   (`video.py:217-223`, new index in `e.data`) and `on_duration_change`
   (`video.py:233-239`) re-arm the progress UI after the swap. Improves the
   player surface (manual/auto quality selector for HLS masters that expose
   variant URLs).
3. **Tune CDN/HLS robustness through `configuration.mpv_properties`.**
   `VideoConfiguration.mpv_properties: Optional[dict[str, Union[str, int, float, bool]]]`
   (`types.py:119-140`): bare mpv option names, bool-to-`"yes"`/`"no"`, full list
   at the mpv manual. This is the only typed escape hatch for cache/demux
   (`cache`, `demuxer-*`), hardware decode (`hwdec`, `hwdec-codecs`), and
   request headers (`http-header-fields`, `user-agent`) on native backends —
   none of which have first-class params (grep-verified, §6). Concretely:
   pass the CDN's required `Referer`/`User-Agent` here when per-media
   `http_headers` proves insufficient for HLS segment sub-requests (§3), and
   raise demuxer/cache budgets for slow HLS. Improves stream-start success
   rate and rebuffering on protected/slow CDNs. Validate each key at runtime
   via `on_error` (`video.py:206-212`) — misspelled keys fail outside these
   files' visibility.
4. **Persist watch state with `on_position_change` + `get_current_position`.**
   `on_position_change: Optional[ft.ControlEventHandler["Video"]]`
   (`video.py:225-231`, current position as `flet.Duration` in `e.data`)
   fires continuously during playback; `get_current_position()` /
   `get_duration()` (`video.py:344-355`) give the same on demand, and
   `on_duration_change` (`video.py:233-239`) marks metadata readiness.
   Throttle-write position to watch history and resume each episode with
   `autoplay=True` (`video.py:59-61`) + `await video.seek(saved)` after
   `on_load` (`video.py:197-198`). `on_complete` (`video.py:215`) is the
   autoplay-next hook. Improves continue-watching, episode-advance, and
   progress-bar surfaces.
5. **Persist per-anime playback rate (property, not method).**
   `playback_rate: ft.Number = 1.0` (`video.py:140-143`) is a settable
   property — there is no `set_rate()` method (full 15-method enumeration,
   §4a). Store the user's speed app-side and reassign
   `video.playback_rate = saved` + `update()` on `on_load`/`on_track_change`.
   Related: `pitch: ft.Number = 1.0` (`video.py:173-176`) is available if
   speed changes need pitch compensation on dubbed episodes. Improves the
   player-preferences surface for negligible cost.
6. **Keep `wakelock=True` (default) and set background behavior explicitly.**
   `wakelock: bool = True` (`video.py:52-57`) already prevents display sleep
   during playback — keep it for long episodes; only disable for
   preview/thumbnail players. Pair with
   `pause_upon_entering_background_mode: bool = True` (`video.py:161-164`)
   and `resume_upon_entering_foreground_mode: bool = False`
   (`video.py:166-171`) to define phone-background behavior (currently
   pause-on-background, no auto-resume). Improves the mobile-playback
   surface with zero code beyond constructor args.
7. **Use the `controls` dict form for fullscreen + custom anime chrome.**
   `controls: Optional[Union[VideoControls, ft.Control, dict[VideoControlsMode, ...]]]`
   (`video.py:77-103`) defaults to `AdaptiveVideoControls()` (Material on
   Android/iOS, MaterialDesktop on desktop, none elsewhere — `types.py:873-907`).
   The dict form (`VideoControlsMode.NORMAL/FULLSCREEN/DEFAULT`,
   `types.py:46-56`) allows a lean touch UI in normal mode and a richer
   desktop bar (`VideoVolumeButton` renders **only** in
   `MaterialDesktopVideoControls` — `types.py:287-293` note) in fullscreen,
   with per-mode `None` to hide. Custom `ft.Control` values and bar-item
   lists (`primary/top/bottom_button_bar`, native defaults quoted in §5a)
   give episode-title overlays and next-episode buttons without forking the
   player. Improves player-chrome and fullscreen surfaces.
8. **Diagnose stream failures with `on_error` + `take_screenshot` thumbnails.**
   `on_error` (`video.py:206-212`, info in `e.data`) is the only
   error-reporting channel — log it with the failing `VideoMedia.resource`
   to distinguish CDN 403s, expired HLS URLs, and codec failures.
   `async def take_screenshot(self, format: Optional[str] = "image/png", include_libass_subtitles: bool = False) -> Optional[bytes]`
   (`video.py:358-392`) captures PNG/JPEG (or raw BGRA with `None` on
   native; `ValueError` otherwise) for episode thumbnails/previews.
   Improves the diagnostics and browse/continue-watching artwork surfaces.

Unverified / explicitly absent — checked and NOT in installed 0.85.3, so no
improvement can be built on them without a different package or version:

- Audio-track (dub/sub-audio) selection API: no `audio_track` field, no
  `set_audio_track`/`get_audio_tracks` method, no `on_audio_change` event in
  `video.py` or `types.py` (full read + grep, §§4/7.2). Multi-audio anime
  sources require a playlist rebuild with a different stream or raw
  `mpv_properties` (e.g. mpv `aid`), both unverified from these files alone.
- Buffering/cache tuning as typed API: no `buffering`/`buffer_size`/`cache_*`
  param on `Video` or `VideoConfiguration` (grep-verified, §7.3). Only
  reachable — if at all — via unlisted `mpv_properties` keys from the mpv
  manual (native only); `seek_bar_buffer_color` is cosmetics, not buffering.
- Whether `VideoMedia.http_headers` are forwarded on every HLS segment/key
  sub-request: the one-sentence docstring (`types.py:66-67`) makes no such
  promise and no forwarding logic exists in these 3 Python files (backend
  behavior, §3). Requires a runtime proxy test per CDN.
- Specific `mpv_properties` key names/values for `ytdl`/`cache`/`demuxer`/
  `user-agent`: zero such strings in the package (grep-verified, §6). Key
  validity, value formats, and web-backend inapplicability come from the mpv
  manual and runtime `on_error` observation, not from this package.
- Stream-quality metadata (bitrate/resolution/rendition list): no such field
  on `VideoMedia` (3 fields only, §3) and no quality getter method (§4a).
  Quality choice depends on variant URLs the app itself extracts from master
  playlists.
- `balance` (stereo), `rate` (actual name `playback_rate`), `mute` (actual
  name `muted`, start-muted only, no live toggle method), `on_loaded`
  (actual name `on_load`), `on_seek` (no seek-ack event): all absent under
  the brief's names; the verified counterparts are in §§2/4.

What was checked and found **not** significant beyond §7: `title`
(volume-mixer label), `fit`/`fill_color`/`alignment` (presentation only),
`filter_quality` (texture scaling, not stream quality — LOW default, MEDIUM
advised on Android), `fullscreen` programmatic toggle (mechanics, not an
improvement), `playlist_mode`/`shuffle_playlist` (playlist looping, marginal
for episodic anime), deprecated `show_controls`/`playlist_add`/
`playlist_remove` (avoid — removal slated for 0.88.0).
