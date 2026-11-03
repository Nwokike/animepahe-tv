# dep-flet-video — flet-video 0.85.3 API reference (installed package)

> **Version note (2026-11-01):** compiled against 0.85.3; installed is **flet-video 0.85.3** (Python 3.14.9).
> The API surface below was re-verified against the live .venv site-packages on 2026-11-01.
> Source of truth: `/home/maikel/Desktop/kiri-apps/animepahe-tv/.venv/lib/python3.14/site-packages/flet_video/`
> Three files only: `video.py` (393 lines), `types.py` (1034 lines), `__init__.py` (48 lines).
> Verified live via `.venv/bin/python` from the repo root:
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

## 8. App usage vs flet-video 0.85.3 (verified 2026-11-01)

This section cross-references every `fv.*` / `Video` kwarg / `on_*` handler used in `src/components/player/immersive_player.py` against the verified 0.85.3 API.

### 8a. Imports & classes used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `import flet_video as fv` | 32 | ✅ Package exists |
| `fv.Video` | 295 | ✅ Exported, class present |
| `fv.PlaylistMode.NONE` | 302 | ✅ Enum exists (NONE, SINGLE, LOOP) |
| `fv.VideoSubtitleConfiguration` | 307 | ✅ Exported, class present |
| `fv.VideoConfiguration` | 317 | ✅ Exported, class present |
| `fv.AdaptiveVideoControls` | 334, 464 | ✅ Exported, class present |
| `fv.VideoSpacer` | 355, 357, 474, 476, 486, 488 | ✅ Exported, class present |
| `fv.VideoPositionIndicator` | 356 | ✅ Exported, class present |
| `fv.VideoFullscreenButton` | 443 | ✅ Exported, class present |
| `fv.MaterialVideoControls` | 465 | ✅ Exported, class present |
| `fv.VideoPlayOrPauseButton` | 475, 487 | ✅ Exported, class present |
| `fv.MaterialDesktopVideoControls` | 481 | ✅ Exported, class present |
| `fv.VideoMedia` | 559, 586, 720 | ✅ Exported, class present |
| `fv.VideoSubtitleTrack` | 1321, 1334 | ✅ Exported, class present (with `.none()`/`.auto()` classmethods) |

### 8b. `Video` constructor kwargs — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `autoplay=True` | 296 | ✅ Exists |
| `expand=True` | 297 | ✅ Inherited from LayoutControl |
| `wakelock=True` | 298 | ✅ Exists |
| `filter_quality=ft.FilterQuality.MEDIUM` | 299 | ✅ Exists |
| `pause_upon_entering_background_mode=True` | 300 | ✅ Exists |
| `resume_upon_entering_foreground_mode=False` | 301 | ✅ Exists |
| `playlist_mode=fv.PlaylistMode.NONE` | 302 | ✅ Exists |
| `fill_color=ft.Colors.BLACK` | 303 | ✅ Exists |
| `fit=self._box_fit()` | 304 | ✅ Exists |
| `title=self.title or "AnimePahe"` | 305 | ✅ Exists |
| `controls=self._build_controls()` | 306 | ✅ Exists (accepts AdaptiveVideoControls) |
| `subtitle_configuration=fv.VideoSubtitleConfiguration(...)` | 307-316 | ✅ Exists |
| `configuration=fv.VideoConfiguration(...)` | 317-320 | ✅ Exists |
| `on_load=self._on_first_ready` | 321 | ✅ Exists (**named `on_load`, not `on_loaded`**) |
| `on_duration_change=self._on_duration_change` | 322 | ✅ Exists |
| `on_position_change=self._on_pos_change` | 323 | ✅ Exists |
| `on_error=self._on_error` | 324 | ✅ Exists |
| `on_complete=self._on_complete` | 325 | ✅ Exists |

### 8c. `Video` properties & methods accessed — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `self.video.playlist = [...]` | 559, 586, 720, 1746 | ✅ Property (list[VideoMedia]) |
| `self.video.update()` | 561, 587, 666, 721, 735, 750, 764, 801, 811, 821, 1322, 1337, 1512, 1537, 1747 | ✅ Inherited method |
| `await self.video.play()` | 566, 588, 722 | ✅ Method |
| `await self.video.play_or_pause()` | 776 | ✅ Method |
| `await self.video.is_playing()` | 777 | ✅ Method |
| `await self.video.seek(ft.Duration(...))` | 788, 831, 1059, 1648 | ✅ Method (accepts `ft.Duration` or int ms) |
| `self.video.volume = new_vol` | 800 | ✅ Property (0-100, validated) |
| `self.video.muted = new_muted` | 810 | ✅ Property (bool) |
| `self.video.fullscreen = new_fs` | 820 | ✅ Property (bool) |
| `self.video.playback_rate = rate` | 734, 749, 763 | ✅ Property (NOT a method — assign + update()) |
| `self.video.subtitle_track = None` | 1318 | ✅ Property |
| `self.video.subtitle_track = fv.VideoSubtitleTrack(...)` | 1321, 1334 | ✅ Property |
| `self.video.subtitle_configuration.text_style.size = size` | 1511 | ✅ Nested property |
| `self.video.fit = _BOX_FITS[name]` | 1536 | ✅ Property |
| `await self.video.take_screenshot()` | 1462 | ✅ Method (returns Optional[bytes]) |
| `await self.video.stop()` | 1742 | ✅ Method |
| `await self.video.get_duration()` | 692, 1051, 1113 | ✅ Method (returns ft.Duration) |
| `await self.video.get_current_position()` | 692, 1110 | ✅ Method (returns ft.Duration) |

### 8d. Event handlers used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `on_load` | 321 | ✅ Exists (**NOT `on_loaded`**) |
| `on_duration_change` | 322 | ✅ Exists |
| `on_position_change` | 323 | ✅ Exists |
| `on_error` | 324 | ✅ Exists |
| `on_complete` | 325 | ✅ Exists |
| `on_enter_fullscreen` | — | ✅ Exists (not used by app) |
| `on_exit_fullscreen` | — | ✅ Exists (not used by app) |
| `on_track_change` | — | ✅ Exists (not used by app) |

### 8e. `VideoSubtitleConfiguration` fields used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `text_style` | 308-313 | ✅ Exists |
| `text_align` | 314 | ✅ Exists |
| `visible` | 315 | ✅ Exists |

### 8f. `VideoConfiguration` fields used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `enable_hardware_acceleration=True` | 318 | ✅ Exists |
| `mpv_properties={...}` | 319 | ✅ Exists |

### 8g. `MaterialVideoControls` fields used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `visible_on_mount=True` | 466 | ✅ Exists |
| `display_seek_bar=True` | 467 | ✅ Exists |
| `seek_on_double_tap=True` | 468 | ✅ Exists |
| `seek_gesture=True` | 469 | ✅ Exists |
| `volume_gesture=True` | 470 | ✅ Exists |
| `brightness_gesture=True` | 471 | ✅ Exists |
| `speed_up_on_long_press=True` | 472 | ✅ Exists |
| `primary_button_bar` | 473-477 | ✅ Exists |
| `top_button_bar` | 478 | ✅ Exists |
| `bottom_button_bar` | 479 | ✅ Exists |

### 8h. `MaterialDesktopVideoControls` fields used — ALL VERIFIED ✅

| App usage | Line(s) | 0.85.3 status |
|-----------|---------|---------------|
| `visible_on_mount=True` | 482 | ✅ Exists |
| `display_seek_bar=True` | 483 | ✅ Exists |
| `modify_volume_on_scroll=True` | 484 | ✅ Exists |
| `primary_button_bar` | 485-488 | ✅ Exists |
| `top_button_bar` | 490 | ✅ Exists |
| `bottom_button_bar` | 491 | ✅ Exists |
| `controls_hover_duration` | 492 | ✅ Exists |

### 8i. **App usages that do NOT exist in 0.85.3 (ERRORS)** — NONE FOUND ✅

All `fv.*` usages in `immersive_player.py` are verified present in the installed flet-video 0.85.3. No mismatches, no missing APIs, no signature errors.

### 8j. App usage notes & minor caveats

| Item | Finding |
|------|---------|
| `playback_rate` assignment | App correctly uses property assignment (`self.video.playback_rate = rate` + `update()`). No `set_rate()` method exists — this is correct usage. |
| `on_load` vs `on_loaded` | App uses `on_load` (correct). The old doc incorrectly mentioned `on_loaded`. |
| `muted` vs `mute` | App uses `muted` (correct). No `mute` property exists. |
| `VideoSubtitleTrack.none()` / `.auto()` | Exist in 0.85.3 (verified). App doesn't use them but could for "off"/"auto" subtitle modes. |
| `VideoMedia.http_headers` | App passes headers per-media. Verified the field exists. **Caveat:** no documented guarantee headers are re-sent on HLS segment sub-requests (§3). |
| `mpv_properties` keys | App uses `http-header-fields`, `cache`, `cache-secs`, `demuxer-max-bytes`, `demuxer-max-back-bytes`, `framedrop`, `hr-seek-framedrop`, `network-timeout` (line 57-72). These are mpv-level options, not validated by the Python package — validate at runtime via `on_error`. |
| `take_screenshot` format | App uses default `"image/png"` (line 1462). Valid. |
| `seek` position | App uses `ft.Duration(seconds=...)`. Verified `ft.DurationValue` accepts `ft.Duration` or int (ms). |
| Deprecated APIs | App does NOT use `show_controls`, `playlist_add`, `playlist_remove` — correct. |

---

## 9. Biggest doc corrections from previous version

| Old doc claim | Corrected fact (0.85.3 verified) |
|---------------|----------------------------------|
| "installed is **flet-video 1.0.4**" | Installed is **0.85.3** (matching pyproject.toml pin). |
| `on_loaded` event exists | **Does not exist** — actual event is `on_load`. |
| `rate` parameter on Video | **Does not exist** — actual parameter is `playback_rate`. |
| `mute` parameter on Video | **Does not exist** — actual parameter is `muted` (start-muted only, no live toggle). |
| `balance` parameter | **Does not exist** — no stereo balance control. |
| `buffering` / `buffer_size` params | **Do not exist** — only via `mpv_properties`. |
| `mpv_properties` as top-level Video param | **Does not exist** — lives at `Video.configuration.mpv_properties`. |
| `VideoSubtitleTrack.none()/auto()` missing | **Exist in 0.85.3** — verified present. |
| `on_seek` event | **Does not exist** — use `on_position_change`. |
| `on_playing_change` event | **Does not exist** — poll `is_playing()` or track via `on_load`/`on_pause` logic. |
| `VideoMedia` has quality/variant fields | **Does not** — only 3 fields: `resource`, `http_headers`, `extras`. |
| Audio track selection API | **Does not exist** — no `audio_track`, `set_audio_track`, `on_audio_change`. |

---

## 10. Exported names (`flet_video.__all__`) — verified 0.85.3

```
AdaptiveVideoControls
MaterialDesktopVideoControls
MaterialVideoControls
PlaylistMode
Video
VideoBarItem
VideoConfiguration
VideoControls
VideoControlsMode
VideoFullscreenButton
VideoMedia
VideoPlayOrPauseButton
VideoPositionIndicator
VideoSkipNextButton
VideoSkipPreviousButton
VideoSpacer
VideoSubtitleConfiguration
VideoSubtitleTrack
VideoVolumeButton
```

---

*Document regenerated 2026-11-01 against flet-video 0.85.3 in .venv (Python 3.14.9). All claims traceable to source files in `.venv/lib/python3.14/site-packages/flet_video/`.*