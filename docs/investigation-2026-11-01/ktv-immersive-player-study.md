# KTV Immersive Player Study

**Generated:** 2026-11-02  
**Subject:** KTV Player (`/home/maikel/Desktop/kiri-apps/ktv-player`) immersive player architecture vs animepahe-tv (`/home/maikel/Desktop/kiri-apps/animepahe-tv`) player

---

## 1. KTV Player Architecture Map

| Concern | Files & Key Lines |
|---------|-------------------|
| **Entry / mount** | `src/main.py:683-825` `play_stream()` creates `ImmersivePlayer` wrapped in `FocusScope` + `ft.View(route="/play")` appended to `page.views`. |
| **Player class** | `src/components/player/immersive_player.py:158` `class ImmersivePlayer(ft.Stack)` — owns `fv.Video`, overlay `Container`, controls via `fv.AdaptiveVideoControls`. |
| **Controls builders** | `src/components/player/controls.py:42` `build_player_controls()` — builds **fresh instances per branch** (touch + desktop/TV) to avoid double-mount. Chips (quality/audio/speed) tracked in lists; toast chip lives **inside** `video.controls` (top bar `Stack`) so it survives native fullscreen. |
| **Event handlers** | `src/components/player/handlers.py` — `cycle_speed`, `pick_subtitles` (track picker + local file), `open_quality_picker` (quick chip), `open_player_settings` (full sheet with quality/audio/fit/snapshot), `handle_stream_complete` (reconnect logic), `reconnect_stream`. |
| **Lifecycle (mount/unmount)** | `immersive_player.py:395-421` `did_mount()` registers fullscreen toast; `will_unmount()` unregisters, cancels watchdog, disarms auto-PiP, **sync position save** via orphan task (lines 406-420). |
| **Overlay vs route** | KTV uses a **route** (`/play` view) with a `/blank` underlay (`main.py:602-622`) so Android system back reaches Python (`view_pop`). The overlay inside the player is a `Container` in the `Stack` (loading/error/retry). |
| **Event wiring** | `video` callbacks: `on_duration_change` (684), `on_position_change` (685), `on_error` (686), `on_complete` (687), `on_enter_fullscreen` (688), `on_exit_fullscreen` (689). Back via `FocusScope.on_back` → `player._on_back` → `on_close` callback. |
| **Watchdog** | `_start_watchdog()` (1084-1105) 20s timeout; fires if no load/position/error event → shows retry/back UI. Started in `start_playback` (665), `_swap_media` (978), `_manual_retry` (1161). |
| **Position save/restore** | **Restore**: `__init__` (210-225) reads history sync → `_initial_resume_position`; `_check_and_trigger_seek` (761-775) + `_deferred_seek` (777-810) polls duration > 0 then seeks. **Checkpoint**: `_maybe_save_position_periodically` (730-759) every 10s. **Close-save**: `handle_close` (1229-1246) awaits `_save_current_position` (1164-1200) before stop/clear playlist. **Orphan tasks** (35-46) track saves started from sync `will_unmount` so shutdown can await them. |
| **Quality/variant handling** | HLS proxy manifest pinning: `_resource_url_for` (872-889), `list_variants` (997-1013), `list_audio_tracks` (1015-1032), `apply_variant` (1083-1089), `apply_audio` (1091-1097), `_swap_media` (1034-1081) captures position/duration, sets `_pending_seek`, swaps playlist, restarts watchdog. Probe once on first playback (`_probe_stream_options` 1037-1065) reveals quality/audio chips. |
| **Subtitles** | `handlers.py:37-156` `pick_subtitles` — dialog with Auto/Off/Load Local File; local `.srt/.vtt` via `FilePicker` → `VideoSubtitleTrack(src=path)`. Also in `open_player_settings` (264-481) with size/fit controls. |
| **Next/prev** | Not in player; shell owns `on_next`/`on_previous` callbacks passed at construction (`main.py:798-800`). |
| **Error cards** | Overlay shows spinner + "Go Back" always; on final error shows "Retry Stream" + "Go Back". Tap-to-close on error overlay → `_on_back` (833-850). |
| **Controls / D-pad** | `controls.py:276-357` `AdaptiveVideoControls` with `MaterialVideoControls` (touch) + `MaterialDesktopVideoControls` (TV/desktop). TV branch has volume slider, no gestures, 4s hover. Back button in top bar (both branches). |

---

## 2. BACK Path Exactly

| Step | Code |
|------|------|
| **1. FocusScope intercept** | `main.py:780-789` `FocusScope(on_back=_player_on_back)` → calls `self._close_player()` (NOT `player.handle_close()`). |
| **2. `_close_player()`** | `main.py:837-867` finds player in top view; if not `_close_already_saved` → `_begin_player_close(player)` (844-850). |
| **3. `_begin_player_close()`** | `main.py:561-574` guards on `player._is_closing` (in-flight flag); sets it, runs `_close_player_with_save` via `page.run_task`. |
| **4. `_close_player_with_save()`** | `main.py:1102-1138` **awaits** `_persist_player_position` (1155-1181), then teardown, clears playlist, pops view or exits. |
| **5. `view_pop` (system back)** | `main.py:1063-1100` same logic: if player in top view and not `_close_already_saved` → `_begin_player_close`. |
| **6. `_close_already_saved()`** | `main.py:548-559` predicate: `player._is_closing AND player._position_saved`. Prevents double-close race. |
| **7. KeyboardListener keys** | No global `KeyboardListener` — back is **only** via `FocusScope.on_back` + Android `view_pop`. TV D-pad back is handled by `FocusScope` → same path. |
| **Re-entrancy** | `_is_closing` guards `_begin_player_close`; `_position_saved` guards `will_unmount` (406) and `_persist_player_position` (1160). Orphan tasks (35-46) ensure sync `will_unmount` saves are awaited on shutdown. |

**Ordering:** position save **awaited** in `_close_player_with_save` → **then** `video.stop()` + `playlist=[]` + `update()` → **then** view pop / exit. The save runs **before** native teardown.

---

## 3. INTERSTITIAL Placement Exactly

| Aspect | Code |
|--------|------|
| **Owner's rule** | "Shown when the video actually starts playing, not at quality selection." |
| **Location** | `immersive_player.py:618-632` inside `start_playback()` — **after** YouTube resolution, **before** `playlist=` + `play()`. |
| **Await pattern** | ```python\ntry:\n    await asyncio.wait_for(self.ad_service.show_interstitial(), timeout=20.0)\nexcept TimeoutError:\n    logger.warning("Ad timed out")\nexcept Exception as ex:\n    logger.warning("Ad skipped: %s", ex)\n``` |
| **Skip conditions** | - `_is_closing` checked after ad (630-632) → early return if player closed during ad.\n- Timeout 20s → proceeds anyway.\n- Any exception → proceeds anyway (ad is non-blocking). |
| **Fallback** | No explicit "quality selection" interstitial. The rule is enforced by **placement in `start_playback`** — quality picker (`open_quality_picker` / `apply_variant`) calls `_swap_media` which restarts playback **without** re-showing the ad. |

---

## 4. Divergence Table: animepahe-tv vs KTV

| Concern | KTV (Good) | animepahe-tv (Different/Worse) | Lines |
|---------|------------|--------------------------------|-------|
| **Back handling** | Single canonical path: `FocusScope.on_back` → `_close_player` → `_begin_player_close` → `_close_player_with_save` (awaited save) → pop/exit. `view_pop` and `route_change` funnel through same `_begin_player_close`. Guard `_close_already_saved` prevents double-close. | **Two parallel paths**: (1) `focus_scope(player, _player_back)` → `_player_back` → `player._on_back` → `on_close` → `_async_close_player` (642-690); (2) `controller.close_player` → `set_active_view("anime")` (159). **Re-entrancy bug**: `_back_in_flight` global (384) added 2026-11-01 to break infinite loop `player._on_back` → `on_close` → `_close_player` → `run_task(_player_back)` → `player._on_back`... Save is **fire-and-forget** in `will_unmount` (1067-1097) via `spawn()` — not awaited. | KTV: `main.py:488-574, 1063-1138`<br>animepahe: `app_shell.py:380-698` |
| **Phone playback failures** | `configuration.mpv_properties` uses `enable_hardware_acceleration=True` **without** forcing `hwdec="mediacodec"` (353-372). Comment: "auto-safe still uses MediaCodec when supported, but falls back to software instead of erroring out." | Same `enable_hardware_acceleration=True` but **no comment or fallback logic** (293-318). `filter_quality=MEDIUM` (297) vs KTV's `LOW` (338). No explicit hwdec handling — relies on flet_video defaults. | KTV: `immersive_player.py:353-372`<br>animepahe: `immersive_player.py:293-318` |
| **Code size (player only)** | `immersive_player.py`: ~1260 lines<br>`controls.py`: ~360 lines<br>`handlers.py`: ~530 lines<br>**Total: ~2,150 lines** | `immersive_player.py`: ~1750 lines (monolithic — controls, handlers, lifecycle, subtitles, snapshots, keyboard all in one file) | KTV: 3 files<br>animepahe: 1 file |
| **Quality/audio probe** | Probes **once on first playback** (`_hide_overlay` 825-831 → `_probe_stream_options`). Chips hidden until probe proves options exist. | Probes in `_start_playback` (569) via `spawn(self._probe_stream_options())` — same idea but **no guard against probe running before mount** (can race). | KTV: `immersive_player.py:825-831`<br>animepahe: `immersive_player.py:569` |
| **Subtitles: local sidecar** | `pick_subtitles` → `FilePicker` → `VideoSubtitleTrack(src=path)` (handlers.py:67-93). | `_pick_subtitle_file` → `FilePicker` with `with_data=True` → decodes bytes → `VideoSubtitleTrack(src=text)` (1339-1379). **KTV uses file path (native); animepahe uses raw text (works on web too).** | KTV: `handlers.py:67-93`<br>animepahe: `immersive_player.py:1339-1379` |
| **Downloaded-file playback** | `is_local_media_url` + `resolve_saf_path` (main.py:994-1006) normalizes `content://` → filesystem path so "Open With" and Local screen share history key. | No SAF normalization. `play_downloaded` uses `resource` from store — assumes direct file path. | KTV: `main.py:994-1006`<br>animepahe: (absent) |
| **Next/prev** | Shell-owned callbacks passed at construction (`on_next`/`on_previous`); player has **no** next/prev logic. | Player owns `on_next`/`on_previous` callbacks (146-147, 423-440) AND keyboard handlers (887-892) AND `_on_complete` auto-advance (1668-1687). **Duplicated in shell** (`_play_adjacent` 387-394). | KTV: `main.py:798-800`<br>animepahe: `immersive_player.py:146-147, 423-440, 887-892, 1668-1687` + `app_shell.py:387-394` |
| **Interstitial** | Shown **at video start** in `start_playback` (618-632). 20s timeout, skip on error. | **No interstitial at all** — `ad_service` exists but not wired into player. Quality dialog (`_build_quality_dialog`) is the gate. | KTV: `immersive_player.py:618-632`<br>animepahe: (absent) |
| **Resume via store** | `db_manager.get_history_entry_sync` in `__init__` (210-225) → `_initial_resume_position` → deferred seek. Periodic checkpoint every 10s. Close-save awaited. | `_read_resume_position` (517-545) spawns async read from store → `_initial_resume_position`. Checkpoint loop every 10s (1016-1026). Close-save **awaited** in `handle_close` (1719-1747) but `will_unmount` save is fire-and-forget. | KTV: `immersive_player.py:210-225, 730-759, 1164-1200`<br>animepahe: `immersive_player.py:517-545, 1016-1026, 1719-1747` |
| **TV D-pad** | `MaterialDesktopVideoControls` (controls.py:318-356) — volume slider, no gestures, 4s hover. Back button in top bar. Keyboard via `FocusScope` → `on_back`. | `handle_key` (854-905) — full key map (arrows, space, m, f, [], digits, s). Registered via `focus_manager.set_key_consumer(player.handle_key)` (app_shell.py:570-574). **No desktop controls branch** — uses same `AdaptiveVideoControls` but only `material` (touch) config; `material_desktop` not customized for TV. | KTV: `controls.py:318-356`<br>animepahe: `immersive_player.py:854-905` + `app_shell.py:570-574` |

---

## 5. PORT PLAN: Rebuild animepahe-tv Player on KTV Skeleton

**Goal:** Replace animepahe-tv's monolithic `ImmersivePlayer` with KTV's modular skeleton (`ImmersivePlayer` + `controls.py` + `handlers.py`), swapping in animepahe-tv's domain features.

### Phase 1: Skeleton & Mount (1-2 days)
1. **Copy KTV player files** → `src/components/player/{immersive_player.py, controls.py, handlers.py}`
2. **Mount via route + underlay** (KTV style): `AppController.play_stream` creates `ft.View("/play")` with `FocusScope` + `ImmersivePlayer`; `_ensure_back_underlay` inserts `/blank` at index 0. Remove `page.overlay` imperative mount (`app_shell.py:_use_player_overlay`).
3. **Wire `view_pop` + `route_change`** to funnel through `_begin_player_close` (single canonical close path). Delete `_player_back`, `_async_close_player`, `_back_in_flight`, `_close_player` from `app_shell.py`.

### Phase 2: fv.Video + mpv Tuning (0.5 days)
4. **Port `configuration`** from animepahe-tv: `filter_quality=MEDIUM`, `_mpv_props(referer)` with `network-timeout: 10`, `cache-secs: 5`, `demuxer-max-bytes: 50M`. Keep KTV's `enable_hardware_acceleration=True` **without** forcing `hwdec` (auto-safe fallback).
5. **Subtitle configuration**: KTV's `VideoSubtitleConfiguration` (size 22, weight 600, bgcolor BLACK_54) → animepahe-tv's persisted size/fit from store.

### Phase 3: Variants/Quality (1 day)
6. **Keep KTV's HLS proxy pinning**: `_resource_url_for`, `list_variants`, `list_audio_tracks`, `apply_variant`, `apply_audio`, `_swap_media` (captures position, sets `_pending_seek`, restarts watchdog).
7. **Probe once on playback start** (KTV's `_hide_overlay` → `_probe_stream_options`). Reveal quality/audio chips only when `len(variants) > 1` or `len(tracks) >= 2`.
8. **Settings sheet** = KTV's `open_player_settings` (handlers.py:264-481) + animepahe-tv's fit/size/subtitle sections. Quality/audio dropdowns populated from `_variants_cache`/`_audio_tracks_cache`.

### Phase 4: Subtitles incl. Local Sidecar (0.5 days)
9. **Merge subtitle handlers**: KTV's `pick_subtitles` (Auto/Off/Load Local File via `FilePicker` → `VideoSubtitleTrack(src=path)`) + animepahe-tv's source tracks (`apply_subtitle` from `self.subtitles` proxy URLs) + local file text fallback (animepahe-tv's `apply_local_subtitle` using raw text for web compat).
10. **Default subtitle**: animepahe-tv's `_apply_default_subtitle` (1381-1390) on first ready.

### Phase 5: Downloaded-File Playback (0.5 days)
11. **Add SAF normalization**: `resolve_saf_path` (KTV `local_scanner.py`) in `route_change` for `file://`/`content://` schemes. Normalize to filesystem path so history/resume key is stable.
12. **Local file playback**: `is_local_media_url` check → `show_favorite=False`, no proxy, direct `VideoMedia(path)`.

### Phase 6: Next/Prev from Downloads Store (0.5 days)
13. **Move next/prev to shell**: `AppController.play_adjacent(delta)` reads from downloads store, calls `play_stream` for next/prev episode. Player receives `on_next`/`on_previous` callbacks (like KTV). Remove `on_next`/`on_previous` from player, remove keyboard handlers for `]`/`[`/`n`/`p`, remove `_on_complete` auto-advance.

### Phase 7: Yandex Interstitial at Video-Start (0.5 days)
14. **Integrate `ad_service.show_interstitial()`** in `start_playback` **exactly at KTV's location** (after YouTube resolution, before `playlist=` + `play()`). Use `fya` show/wait_for_dismiss pattern:
    ```python
    if self.ad_service and not self._is_closing:
        try:
            await asyncio.wait_for(self.ad_service.show_interstitial(), timeout=20.0)
        except (TimeoutError, Exception) as ex:
            logger.warning("Ad skipped: %s", ex)
    if self._is_closing:
        return
    ```
15. **Preload interstitial** at boot (KTV `main.py:650-655`) for non-premium users.

### Phase 8: Resume via Store (0.5 days)
16. **KTV's resume flow**: sync read in `__init__` → `_initial_resume_position` → `_check_and_trigger_seek` → `_deferred_seek` polls duration > 0 → seek. Periodic checkpoint every 10s (`_maybe_save_position_periodically`). Close-save **awaited** in `handle_close` → `_persist_player_position`. Orphan tasks track sync `will_unmount` saves.
17. **Adapt to animepahe-tv store**: `store.get_position(resume_key)` → `{position, duration, rate}`. Save `_speed_rate` on checkpoint.

### Phase 9: TV D-pad (0.5 days)
18. **Use KTV's `MaterialDesktopVideoControls`** (controls.py:318-356) — volume slider, no gestures, 4s hover, back button in top bar.
19. **Keyboard**: `FocusScope.on_back` handles Back/Esc. Arrow keys / media keys handled by `FocusScope` → player's `handle_key` (if needed) or rely on flet_video's built-in desktop controls. Remove animepahe-tv's custom `handle_key` map.

### Phase 10: Cleanup & Verify (1 day)
20. Delete animepahe-tv's monolithic `immersive_player.py`, `app_shell.py:_use_player_overlay`, `_player_back`, `_async_close_player`, `_close_player`, `_back_in_flight`, `_active_player`, `_active_mount`, `_active_key`.
21. Verify: cold start → play → back (save position) → reopen (resume) → quality switch (position restored) → next/prev episode → phone playback (no codec error) → TV remote (D-pad works) → interstitial shows at video start → downloaded file plays.

---

## Summary (8 bullets)

- KTV uses a **route-based player** (`/play` view + `/blank` underlay) with a **single canonical close path** (`_begin_player_close` → awaited save → teardown → pop/exit) funneled by `FocusScope.on_back`, `view_pop`, and `route_change`; animepahe-tv has **two parallel close paths** with a re-entrancy bug fixed by a global `_back_in_flight` flag.
- KTV's **interstitial runs at video start** inside `start_playback` (after YouTube resolve, before `play()`), with 20s timeout and skip-on-error; animepahe-tv has **no interstitial** — quality dialog is the gate.
- KTV **probes variants once on first playback** and reveals quality/audio chips only when options exist; animepahe-tv probes on `start_playback` but without a mount guard.
- KTV **saves position three ways**: initial resume (sync read in `__init__` → deferred seek), periodic checkpoints (10s), and **awaited close-save** (orphan tasks track sync `will_unmount` saves); animepahe-tv's close-save is awaited but `will_unmount` save is fire-and-forget.
- KTV **does not force `hwdec=mediacodec`** — uses `enable_hardware_acceleration=True` with auto-safe fallback, avoiding phone MKV "Could not open codec" failures; animepahe-tv copies the flag but lacks the fallback comment/logic.
- KTV's **controls are split** (`immersive_player.py` + `controls.py` + `handlers.py` ≈ 2,150 lines) with fresh instances per touch/TV branch; animepahe-tv's player is **monolithic** (1,750 lines in one file) and lacks a customized TV/desktop controls branch.
- KTV **normalizes SAF `content://` URIs** to filesystem paths so "Open With" and Local screen share one history key; animepahe-tv has no SAF handling.
- KTV's **next/prev lives in the shell** (callbacks passed to player); animepahe-tv duplicates next/prev in player (keyboard, buttons, `_on_complete` auto-advance) AND shell (`_play_adjacent`).