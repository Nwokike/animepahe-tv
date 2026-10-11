# Sherlock → animepahe-tv port reference

Source of truth: actual source read 2026-10-11.
Sherlock root: `C:\Users\nwoki\.zcode\workspace\default\Sherlock\src\`
animepahe-tv root: `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\src\`

Flet versions differ slightly (Sherlock comments say 1.0.1, animepahe-tv says 1.0.4) but the house APIs (`page.show_dialog` for SnackBar, `use_dialog` portal, `page.services`) are the same.

---

## 1. Feature inventory (Sherlock — what exists)

### 1.1 App architecture

- **Entry + controller:** `main.py:99-156` defines `AppController` owning `storage`, `ad_service`, `sherlock_service`, `email_service`, `enrich_service`, `update_service`, `connectivity`, `scan_notify`, plus task handles (`_search_task`, `_enrich_worker_task`, `_render_flush_task`), a history lock (`_history_lock`), and a progress-coalescing bridge. `main.py:1910-1953` wires `logging` + `in_memory_log_handler`, `page.on_error`, `page.on_disconnect`/`page.on_close` flush paths.
- **Init order:** `main.py:349-468` — page title/padding, bundled `Outfit` font (`main.py:357-363`), light+dark themes, `theme_mode=SYSTEM`, `FilePicker` singleton (`main.py:368-374`), `ft.Connectivity` listener (`main.py:376-388`), `mount_shared_services` (`main.py:384-387`), services construction, `_load_saved_state`, UMP consent + interstitial preload (`main.py:403-408`), site load, update check, `page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`, system-back guard.
- **ControllerMethods bridge:** `state/controller_ctx.py:45-82` — mutable dataclass with controller-owned async methods (`refresh_sites`, `start_search`, `cancel_search`, `start_email_search`, `cancel_email_search`, `save_selected_sites`, `check_for_updates`, `open_update_dialog`, `set_onboarding_done`, `open_cached_result`, `run_db_health`) plus AppShell-owned sync closures (`show_results`, `show_sites`, `show_settings`, `show_history`, `go_home`, `back`, `open_sheet`, `close_dialog`, `handle_system_back`). No-op defaults so screens render in tests.
- **AppShell branching:** `app_shell.py:1020-1227` — `use_state` for `active_tab`/`active_view`/`active_dialog`, `ft.use_dialog(active_dialog)` portal (`app_shell.py:1029-1035`), view-closure injection (`app_shell.py:1040-1070`), `_system_back` mapping results/sites→dashboard and settings/history→home (`app_shell.py:1048-1059`), `_sync_chrome` syncing `appbar` + `navigation_bar` via `use_effect` (`app_shell.py:1074-1160`), onboarding/results/sites/dashboard branches (`app_shell.py:1170-1227`), history-unseen nav badge (`app_shell.py:1109-1129`). Progress version deliberately excluded from chrome deps (`app_shell.py:1146-1160`).
- **System-back hardening:** `main.py:441-495` — `page.on_view_pop` → in-app navigation, plus `_guard_root_view_pop` setting `View.can_pop=False` + `on_confirm_pop` → `confirm_pop(False)` so Android back never kills the single-view shell.
- **Observable state:** `core/state.py:12-206` — `@ft.observable AppState` with search flags, dual-mode fields, theme, last-results, email-results, enrichments (cap `_ENRICHMENT_CAP=200`, `core/state.py:9`), history + `results_cache`, ~25 settings fields, site-DB fields, update fields. Collections assigned in `__init__` for Observable wrapping (`core/state.py:132-147`); `set_cached_result` LRU-30 (`core/state.py:149-160`); `set_enrichment` LRU-cap (`core/state.py:162-168`); `reset_search` preserves `is_online`/`search_mode` (`core/state.py:170-203`).
- **Background tasks:** `core/tasks.py:18-31` — `spawn()` wraps `asyncio.create_task` with a done-callback that logs failures (never bare `create_task`).
- **Shared services:** `core/shared_services.py:32-99` — `mount_shared_services(page)` mounts one `HapticFeedback` + `Clipboard` + `Share` + `UrlLauncher`, idempotent, stashed on page; `shared_*()` getters resolve mounted instance or fall back to fresh construction.
- **Storage:** `services/storage_service.py:63-286` — file-backed (`FLET_APP_STORAGE_DATA` or `.flet/storage/data`) vs `client_storage` web branch (`storage_service.py:83-95`), debounced 1s writes (`storage_service.py:18,196-217`), atomic temp-file + `os.replace` + `fsync` (`storage_service.py:146-176`), corrupt-file backup (`storage_service.py:21-29,135-139`), `flush()` outside lock via `to_thread` (`storage_service.py:270-285`), typed `get/set/delete/clear/get_all`. History helpers `load_history_entries`/`encode_history_entries` newest-first-display / oldest-first-storage, cap 50 (`storage_service.py:288-311`).
- **HTTP:** `services/http_client.py:38-85` — pooled `httpx.AsyncClient` with keepalive, rebuilt when `state.proxy_url`/`state.retries` change; explicit direct + proxy transports (comment explains why not `transport=+proxy=` combo, `http_client.py:55-57`); `_drain` closes replaced clients via `spawn` (`http_client.py:88-97`).
- **Scan engine + render budget:** `_kill_all_activity` (`main.py:160-206`), `_register_search_task`/`_start_render_flusher`/`_stop_render_flusher` (`main.py:272-301`), `_render_flusher` single ~2Hz `progress_version` bumper (`main.py:303-347`), `_progress_from_thread` 500ms coalescing bridge via `call_soon_threadsafe` (`main.py:1043-1083`), `_apply_progress` with cross-mode + supersede guards (`main.py:1085-1156`), enrichment generation counter (`main.py:134,183`), avatar warm budget 50 (`main.py:136,994-1010`).
- **History + result snapshots:** `_save_to_history` (`main.py:1644-1773`) — mode-shaped snapshots into `results_cache` + persisted `STORAGE_CACHED_RESULTS`, upsert-on-same-query+mode, newest-first observable mirror, `history_unseen` counter (`main.py:1767-1769`), `_history_lock` serialisation (`main.py:141-143`); primary-done bridge saves early so Recent populates before the recursive tail finishes (`main.py:1626-1642`). `open_cached_result` rehydrates `SearchProgress`/`EmailSearchProgress` objects without re-scanning, with live-scan re-attach guard (`main.py:1462-1624`).

### 1.2 Theme system (canonical 3-way house pattern)

- **Palette + helpers:** `core/theme.py:12-116` — `AppColors` brand/status/terminal/dark/light constants; `_resolve_page` fallback to `flet.context.page` (`theme.py:48-57`); `get_bg/get_surface/get_surface_2/get_border/get_text/get_text_dim/grey_dim` (`theme.py:59-116`).
- **Dark detection:** `is_dark_mode` (`theme.py:119-133`) — `theme_mode==DARK` or (`SYSTEM` + `platform_brightness==DARK`); `None` page defaults dark.
- **Glass + styles:** `adaptive_glass_bg/border` (`theme.py:144-155`); `AppStyles.section_card/glass_card/brand_gradient` (`theme.py:161-233`); M3 `get_light_theme/get_dark_theme` with Outfit, scrollbar/snackbar/tab/card/chip/page-transition themes (`theme.py:238-339`).
- **Cycle control (header):** `components/app_header.py:109-145` — `_cycle_theme`: DARK→LIGHT→SYSTEM→DARK, persists `STORAGE_THEME` via `spawn`, bumps `state.theme_mode` + `progress_version` so AppShell chrome re-syncs, `page.update()`. Icon maps current mode (`app_header.py:23-28`).
- **Picker (settings):** `screens/settings_screen.py:243-316` — `_on_theme_change(val)` sets `page.theme_mode` + `state.theme_mode`, persists + flushes; `_create_theme_card` 3 selectable cards (light/dark/system) with selected border/bg (`settings_screen.py:264-316`), used at `settings_screen.py:632-647`.
- **Restore:** `main.py:518-524` — reads `STORAGE_THEME`, maps `dark/system/light` (else LIGHT); init defaults `theme_mode=SYSTEM` (`main.py:364`).
- **Tokens:** `core/tokens.py:1-156` — font/spacing/radius/icon/animation/elevation/dimension/opacity scales consumed by every component.

### 1.3 Settings screen

- **Row + card primitives:** `_setting_row(icon,title,subtitle,trailing,stacked)` (`screens/settings_screen.py:129-209`) — icon backdrop box, two-line text col, `stacked=True` moves trailing (Slider/SegmentedButton stretch) to indented second line on narrow screens; `_settings_card` (`settings_screen.py:212-224`) — M3 `SURFACE_CONTAINER_HIGHEST` card with outline border + anti-alias clip.
- **Narrow detection:** `settings_screen.py:240` — `page.width < 600` drives `stacked=narrow` on every row.
- **Cards/sections:** Preferences (theme) → Scan Parameters → banner → Email Intelligence → Network & Proxy → Enrichment → banner → Connection & Speed → Custom Manifest → banner → Troubleshooting & Logs → About (`settings_screen.py:1498-1526`), each preceded by `SectionHeader` (`components/section_header.py:9-23`).
- **Controls:** Switches (recursive, permute, notifications, extract_info, exclusions, NSFW, curl, filters, deep-enrich, DNS only on desktop at `settings_screen.py:771-800,1250-1274`); SegmentedButtons (retries, DNS resolver, enrichment mode, scan depth `all/1000/500`); Sliders with split live-label vs commit-persist handlers (`_slider_live` `settings_screen.py:360-370`, `_slider_commit` `settings_screen.py:372-387`); TextFields validated on submit+blur (proxy `_parse_proxy` `settings_screen.py:67-90`, manifest `_validate_manifest` `settings_screen.py:93-126`, cookies existence `settings_screen.py:430-440`).
- **NSFW single-writer:** `_set_nsfw` (`settings_screen.py:318-329`) — writes `nsfw_enabled` + mirrored `safe_search`, persists both keys, refreshes sites.
- **DB actions:** update check with re-entrancy guard + button disable (`settings_screen.py:462-500`), health check with guard (`settings_screen.py:502-532`), both surfacing via `show_snack`.
- **Diagnostics terminal spec:** `_open_terminal` (`settings_screen.py:1307-1449`) — last 500 lines (`_TERMINAL_DISPLAY_LINES=500`, `settings_screen.py:1305`), `Courier New` on `TERMINAL_BG #0D0D0D` (`theme.py:28`) with `TERMINAL_GREEN #A6E22E` (`theme.py:29`), telemetry strip (`get_telemetry_snapshot`), subtitle line, explicit `height=260` log box (comment at `settings_screen.py:1421-1427` explains `expand` is a no-op in Column and bursts the dialog), Copy (clipboard + success snack) / Clear / Close actions, refresh-telemetry button; row shows `{log_count} entries recorded` (`settings_screen.py:1452-1464`).
- **About:** icon + name + tappable version → changelog dialog (`settings_screen.py:1108-1165`); UMP consent deliberately NOT a settings row (`settings_screen.py:1101-1105`).

### 1.4 UI craft

- **EmptyState:** `components/empty_state.py:18-88` — circular icon backdrop, title + optional message (max-width 320) + optional FilledButton; warns when label has no handler (`empty_state.py:25-29`).
- **Snackbar:** `core/notify.py:18-52` — `page.show_dialog(SnackBar)` with explicit `ft.Duration(ms)`; on `RuntimeError` pops and re-shows only if popped is `None`/SnackBar, never dismissing a real AlertDialog; never raises.
- **Dialogs:** single `use_dialog` portal (`app_shell.py:1029-1035`) so dialog identity survives scan re-renders; history clear-confirm via portal (`screens/history_screen.py:121-187`); export sheet as `BottomSheet` with drag handle (`app_shell.py:895-908`); update dialog dual-mode (`components/update_dialog.py:154-235`).
- **Banners/ads:** `components/banner_ad.py:36-133` — pooled per-slot (`pooled_banner_ad`, `clear_banner_pool` on teardown/theme change), full-width glass stretcher Row with native 320×50 centred inside, mobile-only (zero-size elsewhere), `on_error` logs AdMob code to terminal; placements after recent/features in Home (`screens/home_screen.py:1122,1155`) and between settings sections (`screens/settings_screen.py:1505,1512,1517`).
- **Active-scan banner:** `components/active_scan_banner.py:15-109` — sticky progress card (target + checked/total + % + ProgressBar + View button); `finishing` state replaces stuck-100% text (`active_scan_banner.py:30-35`); built in AppShell with per-mode counters (`app_shell.py:1177-1216`).
- **Header:** `components/app_header.py:98-242` — icon + title/subtitle left; version chip (`app_header.py:31-95`, morphs to Update/News pill) + theme-cycle button + settings gear + `extra_actions` right; horizontally scrollable on narrow screens (`app_header.py:234`).
- **Pagination:** none — results are a single scan list; Sites screen uses category chips + search filter instead (`screens/sites_screen.py:305-362` per grep).
- **TV focus:** none — phone app; no D-pad/focus-ring/rail code.

### 1.5 Search

- **Guards:** `_submit_guards` (`screens/home_screen.py:521-553`) — empty → error snack; offline → `MSG_SEARCH_OFFLINE`; `is_searching` busy → error; email mode → `validate_email` else `ERR_INVALID_EMAIL`; username mode → shape rule (≤64 chars, `[A-Za-z0-9_.\-]`) else message.
- **URL paste:** `_normalize_pasted_query` (`screens/home_screen.py:325-347`) — strips `@`, extracts last path segment of pasted profile URLs (URL-decoded, ≤64 chars).
- **Mode auto-switch:** `_maybe_switch_mode` on typing/paste (`screens/home_screen.py:587-595`); manual chip taps clear query, auto-switches keep it (`screens/home_screen.py:377-394`); quick-cycle chips for depth/timeout/toggles persist fire-and-forget (`screens/home_screen.py:398-500`).
- **Suggestions:** `ft.SearchBar` with `bar_trailing` clear+paste buttons and mode-filtered history `controls=[:5]` matched case-insensitively (`screens/home_screen.py:896-1002`); recent top-3 rows with mode icons + found/total + timestamp (`screens/home_screen.py:169-226,751-770`).
- **Submit:** `_on_search` → normalize → guards → haptics → `show_results` then `start_*_search` via `spawn` (`screens/home_screen.py:555-578`); history click → guards → mode sync → `open_cached_result` → fallback fresh scan (`screens/home_screen.py:613-637`); results-screen retry respects viewed mode and deliberately does NOT set `is_searching` optimistically (`app_shell.py:910-942`).
- **Scope card:** `TargetsCard` (`components/targets_card.py:22-112`) — all-vs-custom network summary with Customize affordance; opened via `controller.show_sites()`.
- **History screen:** relative timestamps (`screens/history_screen.py:30-69`), mount hydration (`history_screen.py:92-111`), badge consume on open (`history_screen.py:113-119`), clear-all confirm dialog (`history_screen.py:131-187`), open-cached-first then re-search (`history_screen.py:189-221`), newest-first render (`history_screen.py:231-234`), per-row delete with undo-restore + re-persist (`history_screen.py:369-423` per grep).

### 1.6 Update / telemetry / connectivity / errors

- **UpdateService:** `services/update_service.py:61-119` — fetches `UPDATE_CONFIG_URL` (`constants.py:24-26`), 4s timeout via pooled client, `build_number`-gated (announcements gated too), `type` safelist (`update`/`announcement`), `_safe_https_url`/`_safe_text` sanitisers with length caps, returns dict.
- **Dialog:** `components/update_dialog.py:81-235` — up-to-date mode shows bundled `notes_for(APP_VERSION)` changelog offline + Check-for-Updates button (`update_dialog.py:196-219`); update mode shows server Markdown + platform buttons (Android: Play + Direct APK; else GitHub only, `update_dialog.py:81-137`); mandatory → modal no-Later; `check_from_dialog` re-checks live and morphs (`update_dialog.py:60-78`).
- **Controller:** `check_for_updates(notify_if_latest)` (`main.py:1810-1826`) sets `update_available/update_data`, auto-opens if mandatory; header chip + settings version row both open it.
- **Changelog:** `core/changelog.py` — `CHANGELOG` dict + `notes_for(version)` with latest-entry fallback.
- **Telemetry:** `core/logger_handler.py:21-89` — `MemoryLogHandler` class-level deque(maxlen=500) with `%H:%M:%S [name] LEVEL: msg` format; `get_telemetry_snapshot` returns CPU/RAM/App-RSS/battery via psutil or `psutil not loaded`.
- **Connectivity:** `ft.Connectivity` mounted (`main.py:380-382`), `_init_connectivity` probe defaulting online-True (`main.py:1843-1851`), `_on_connectivity_change` offline→`MSG_OFFLINE` 10s / online→`MSG_ONLINE` (`main.py:1854-1870`), lifecycle re-probe on RESUME/SHOW (`main.py:1872-1907`), resume scan-finished snack with View action (`main.py:1877-1900`).
- **Errors:** `ERR_NETWORK/ERR_GENERIC/ERR_OPEN_URL/ERR_INVALID_EMAIL` (`core/constants.py:73-77`); scan failures keyword-match dns/connect/network/offline/unreachable/timeout → `ERR_NETWORK` else `ERR_GENERIC` (`main.py:926-942,1399-1415`); `on_error` → generic snack (`main.py:1836-1839`); offline gates before kills so a doomed search never kills a healthy scan (`main.py:757-765,1216-1217`).

### 1.7 Other notable house patterns

- `core/actions.py:20-29` — `open_url_action` client-action builder with `None` fallback outside live page (P1-3 pattern).
- `core/format.py` — `format_count` (grouping, bool-safe) + `human_date` (precision-honest date humaniser).
- `core/permute.py` — `permute_username` separator-swap variants, cap `MAX_VARIANTS=5`, shape-validated.
- `services/ad_service.py` — UMP `gather_consent` (`ad_service.py:90-131`), `preload_interstitial` (`ad_service.py:175-209`), `show_interstitial` with `INTERSTITIAL_MIN_INTERVAL_SEC=30` (`ad_service.py:60,221-257`); shown on every search (`main.py:785-796,1247-1252`) + export (`app_shell.py:443-455`).
- `services/scan_notify.py:50-209` — OS notification mirror (progress/finished/cancelled, Cancel+View actions, same-id in-place updates).
- `services/cache_service.py` — atomic writes, corrupt backup, compiled-DB cache, avatar cache + `schedule_avatar_download`, fingerprinted report cache, geo cache, tag indices.
- Onboarding (`screens/onboarding_screen.py:122-133`, `main.py:1450-1460`), Sites DB scoping + health (`main.py:1777-1803`), export pipeline PDF/XMind/CSV/JSON/MD/HTML/TXT with `_safe_filename` slug (`app_shell.py:43-56,229-467`) + report cache, identity-graph dialog (`app_shell.py:469-776`), `test_id` automation hook gated by `SHERLOCK_TEST_IDS` (`core/constants.py:8-12`), window minimums 360×600 (`main.py:365-366`).

---

## 2. Implementation patterns worth porting (Sherlock → animepahe-tv gaps)

Each item names the Sherlock source, then the animepahe-tv counterpart and the exact gap.

### P1 — Observable `theme_mode` + Settings theme picker

- Sherlock: `core/state.py:37` (`theme_mode` observable), `components/app_header.py:109-145` (header cycle bumps `state.theme_mode` + `progress_version`), `screens/settings_screen.py:243-316` (`_on_theme_change` + `_create_theme_card` 3-card picker), `main.py:518-524` (restore).
- animepahe-tv: `core/state.py:55-132` has **no** `theme_mode` field; theme lives only in `screens/home_screen.py:214-225` (`_theme_cycle` returns icon+next, no observable bump) and `screens/home_screen.py:438-446` (`_toggle_theme` sets `page.theme_mode` + `save_theme_mode`, no state bump); `screens/settings_screen.py:1-362` has **no** theme section at all.
- Gap: port the observable field + a Settings 3-card picker mirroring `_create_theme_card`; keep animepahe-tv's existing `_theme_cycle` order or adopt Sherlock's DARK→LIGHT→SYSTEM order explicitly.

### P2 — Theme helper family (`get_*` + `is_dark_mode` + glass + section styles)

- Sherlock: `core/theme.py:48-155` (`_resolve_page`, `get_bg/get_surface/get_surface_2/get_border/get_text/get_text_dim`, `is_dark_mode` with SYSTEM+brightness at `theme.py:119-133`, `adaptive_glass_bg/border`), `core/theme.py:161-233` (`AppStyles.section_card/glass_card/brand_gradient`).
- animepahe-tv: `core/theme.py:34-71` has only `_is_dark` (requires non-None page, no context fallback), `get_glass_bg/get_hover_bg/get_surface_variant`; no `get_bg/get_text/get_border` family, no `AppStyles`.
- Gap: port `is_dark_mode`-with-fallback + `get_*` accessors so screens stop branching on `page.theme_mode` inline (e.g. `screens/home_screen.py:214-225`, `core/theme.py:58-71`).

### P3 — Single-writer toggle + slider commit patterns

- Sherlock: `_set_nsfw` dual-key single writer (`screens/settings_screen.py:318-329`, mirrored in Home at `screens/home_screen.py:446-466`); `_slider_live` label-only vs `_slider_commit` persist-once (`screens/settings_screen.py:360-387`).
- animepahe-tv: `screens/settings_screen.py:210-229` (external-player toggle persists via store directly, no dual-key issue but no shared helper); no sliders exist yet.
- Gap: adopt the live-vs-commit split verbatim when sliders arrive; adopt the single-writer comment contract for any mirrored keys.

### P4 — Input validators that restore + warn instead of saving bad values

- Sherlock: `_parse_proxy` (`screens/settings_screen.py:67-90`), `_validate_manifest` (`settings_screen.py:93-126`), cookies-existence check (`settings_screen.py:430-440`) — all `show_snack(WARNING)` + restore control value + return early.
- animepahe-tv: `screens/settings_screen.py:265-270` (`_on_backend_change` saves pin with no validation needed — nothing to port here); no proxy/manifest/cookie fields exist, so no validator counterpart.
- Gap: port the restore-and-warn shape for the next validated field (URL, path, token).

### P5 — Terminal spec details (telemetry content + fixed-height log box + copy feedback)

- Sherlock: psutil CPU/RAM/RSS/battery strip (`core/logger_handler.py:55-89`); `height=260` fixed log container with no-op-`expand` rationale (`screens/settings_screen.py:1408-1427`); Copy → success snack (`settings_screen.py:1324-1333`); row subtitle shows live log count (`settings_screen.py:1452-1464`); `TERMINAL_BG/TERMINAL_GREEN` constants (`core/theme.py:27-29`).
- animepahe-tv: uptime/platform/pid/buffered-lines telemetry (`core/logger_handler.py:79-91`); `log_box` uses `expand=True` inside a Column (`screens/settings_screen.py:113-120` — the shape Sherlock's comment warns against); `_copy` has no success/failure snack (`settings_screen.py:129-134`); colours hardcoded `"#0D0D0D"`/`"#A6E22E"` (`settings_screen.py:98-115`); row subtitle already shows count (`settings_screen.py:181-190` — equivalent).
- Gap: port fixed-height log box, snack on copy, and optionally the psutil strip (or keep uptime strip — deliberate product choice, but make it explicit).

### P6 — Shared-services breadth (haptics/share + FilePicker)

- Sherlock: 4 services mounted once (`core/shared_services.py:40-61`), getters with live-page fallback (`shared_services.py:82-99`); `FilePicker` singleton appended in init (`main.py:368-374`) with Android-registration rationale; `Connectivity` appended as a service (`main.py:380-382`).
- animepahe-tv: 2 services (`launcher`, `clipboard`) in a `SharedServices` class (`core/shared_services.py:23-66`); `mount_shared_services` exists and is called in `main.py:127-129` (equivalent shape); **no** haptics/share getters, **no** FilePicker, connectivity mounted in `_mount_connectivity` (`main.py:204-222` — equivalent).
- Gap: add `shared_haptics`/`shared_share` (share is needed the day animepahe-tv shares links); add FilePicker singleton only when a save-file flow arrives.

### P7 — ControllerMethods completeness (dialog portal typing + system-back handler)

- Sherlock: `state/controller_ctx.py:45-82` types `open_sheet/close_dialog` (`_noop_dialog`) + `handle_system_back` + `show_results/show_sites/show_settings/show_history` + `open_cached_result` + `run_db_health`.
- animepahe-tv: `state/controller_ctx.py:18-46` types navigation + data actions only; AppShell still assigns `controller.open_sheet/close_dialog` dynamically (`app_shell.py:121-122`) and publishes `ui_state` for back (`app_shell.py:124-131`) without dataclass typing; back precedence lives in `FocusManager` + `_handle_global_back` (`main.py:251-275`, `core/focus_manager.py:1-28`).
- Gap: type `open_sheet/close_dialog` (+ `quality`/`dialog` state already in `core/state.py:97-103`) in the dataclass; keep the FocusManager (TV need) but add Sherlock's `on_view_pop`/`can_pop=False` root guard (`main.py:441-495`) if Android back ever kills the shell.

### P8 — Result-snapshot cache + instant history open

- Sherlock: `core/state.py:149-160` (LRU-30 `results_cache`), `_save_to_history` snapshots + persists `STORAGE_CACHED_RESULTS` (`main.py:1644-1725`), `open_cached_result` rebuilds progress objects with live-scan guard (`main.py:1462-1624`), history rows open cached-first (`screens/history_screen.py:189-199`, `screens/home_screen.py:613-637`).
- animepahe-tv: `services/store.py:59-130+` persists history/continue/favorites/downloads with atomic writes (equivalent durability); `core/state.py:55-132` has **no** `results_cache`; search rows re-open via `controller.open_anime(session)` (`screens/search_screen.py:203-226`) — correct for its domain (detail refetch is cheap) — but repeated searches always hit network (`main.py:1263-1281` wires `load_search` with no cache read).
- Gap: only if search latency warrants it — port a small LRU snapshot (query+page → row list) behind the existing `Cache` (`services/cache.py`) rather than the full progress-object rebuild.

### P9 — History UX (relative time, badge, confirm-clear, undo delete)

- Sherlock: `_relative_time` (`screens/history_screen.py:30-69`), `history_unseen` badge (`core/state.py:67`, `app_shell.py:1109-1129`, consumed at `history_screen.py:113-119`), clear-all confirm dialog via portal (`history_screen.py:131-187`) + success snack, per-row delete with indexed restore (`history_screen.py:369-423` per grep).
- animepahe-tv: history rows `{title, session, ts}` newest-first deduped cap 20 (`services/store.py:105-130`); search suggestions show top-8 (`screens/search_screen.py:240-246`); clear via `controller.clear_search_history()` with no confirm (`screens/search_screen.py:329`, `main.py:1240-1244`); **no** relative-time formatter, **no** unseen badge, **no** undo.
- Gap: port `_relative_time` + clear-confirm dialog; badge/undo only if history becomes a tab (today it is suggestions-only).

### P10 — Update hardening (URL safelist, announcement type, offline changelog, live re-check)

- Sherlock: `_safe_https_url/_safe_text` (`services/update_service.py:24-33`), announcement gating on build_number (`update_service.py:83-87`), platform button rule (`components/update_dialog.py:81-137`), bundled `notes_for` offline path (`components/update_dialog.py:196-219`, `core/changelog.py`), `check_from_dialog` morph (`update_dialog.py:60-78`), version chip morphs to Update/News pill (`components/app_header.py:31-95`).
- animepahe-tv: `services/update_service.py:15-34` (per-app-key config, build compare, no safelist/type/changelog), `components/update_dialog.py:21-76` (mandatory-aware, `show_app_dialog`-registered, apk_url launch — equivalent modal rule), `_version_pill` morphs (`screens/home_screen.py:109-157` — equivalent), bg check sets state (`main.py:193-198` — equivalent).
- Gap: port the https safelist + a bundled changelog fallback so the up-to-date dialog works offline; announcements only if the worker config ever gains a campaign use-case.

### P11 — Connectivity toasts + lifecycle re-probe + resume signal

- Sherlock: offline 10s + online toasts (`main.py:1865-1870` with `MSG_OFFLINE/MSG_ONLINE` at `core/constants.py:80-86`), resume re-probe (`main.py:1872-1907`), scan-finished-with-View resume snack (`main.py:1877-1900`).
- animepahe-tv: offline snack on loss, silent on restore except CF retry (`main.py:224-239`); `connectivity_version` bump drives re-render (`core/state.py:73`, `main.py:231,235`); offline banner distinct from CF gate (`screens/home_screen.py:387-...`, `screens/search_screen.py:185-189` — equivalent layering).
- Gap: port the online-restored toast + RESUME/SHOW re-probe (one `use_effect`-free controller method, same as Sherlock's); resume-download/cart snack only if downloads need it.

### P12 — Error taxonomy + offline-gate-before-kill ordering

- Sherlock: `ERR_NETWORK` vs `ERR_GENERIC` keyword heuristic (`main.py:926-942,1399-1415`), `ERR_*`/`MSG_*` constants (`core/constants.py:73-86`), kill-after-gate ordering (`main.py:757-765`).
- animepahe-tv: `ERR_*`/`LBL_*` constants (`core/constants.py:5-39` — equivalent), `_show_error_snackbar` funnel (`main.py:241-244` — equivalent), `_on_page_error` generic (`main.py:1252-1260` — equivalent), search gates offline-before-CF (`screens/search_screen.py:185-200` — equivalent ordering).
- Gap: only the keyword heuristic (network-vs-generic message) is missing; low value unless misdiagnosed errors appear in the terminal.

### P13 — Ad subsystem discipline (pool + interval + consent placement)

- Sherlock: `pooled_banner_ad`/`clear_banner_pool` (`components/banner_ad.py:44-66`), 30s interstitial interval (`services/ad_service.py:60,232-242`), consent-then-preload at init (`main.py:403-408`), interstitial on search + export (`main.py:785-796`, `app_shell.py:443-455`), error-to-terminal (`banner_ad.py:101-102`).
- animepahe-tv: `build_banner_ad` inline/sticky (`components/banner_ad.py:41-84`), `show_interstitial`/`show_app_open`/`build_rewarded_ad` (`services/ads.py:42-...`), SDK service mounted in `main.py` tail (equivalent init placement); **no** pool, **no** interval guard, **no** consent flow (Yandex vs AdMob/UMP — provider difference, not a gap).
- Gap: port the slot pool (prevents ad reset/flash on re-render) + a minimum-interval guard for interstitials; do not port UMP.

### P14 — Small pure helpers (filename slug, count/date format, URL action, test ids, window minimums)

- Sherlock: `_safe_filename` (`app_shell.py:43-56`, NFKD slug + Windows-reserved guard + 64-cap), `format_count/human_date` (`core/format.py`), `open_url_action` with `None` fallback (`core/actions.py:20-29`), `test_id` gated by env (`core/constants.py:8-12`), `window.min_width/min_height` 360×600 (`main.py:365-366`).
- animepahe-tv: no counterparts found (grep for `safe_filename|format_count|human_date|OpenUrl|TEST_IDS|min_width` returns nothing outside unrelated hits).
- Gap: port on demand — slug when file-save arrives, `human_date` when dates render, `test_id` when UI automation arrives; `open_url_action` only if client-action buttons appear.

---

## 3. Ranked port opportunities (evidence-backed)

Ordered by value ÷ effort, citing the exact gap.

1. **Settings theme picker + observable `theme_mode`** — Sherlock `screens/settings_screen.py:243-316`, `core/state.py:37`; animepahe-tv has cycle-only `screens/home_screen.py:214-225` and no Settings theme row. Small, visible, zero-risk; makes the house 3-way pattern complete.
2. **`get_*` theme accessors + `is_dark_mode` fallback** — Sherlock `core/theme.py:48-155`; animepahe-tv `core/theme.py:34-71` forces every call site to branch. Removes a whole class of light/dark bugs; mechanical refactor.
3. **Banner slot pool + interstitial interval** — Sherlock `components/banner_ad.py:44-66`, `services/ad_service.py:60,232-242`; animepahe-tv `components/banner_ad.py:41-84` rebuilds per render, `services/ads.py:54-66` has no guard. Fixes ad flash + accidental stacking; medium-small.
4. **History clear-confirm + relative timestamps** — Sherlock `screens/history_screen.py:30-69,131-187`; animepahe-tv `screens/search_screen.py:329`, `main.py:1240-1244` clears with no confirm. Prevents one-tap data loss; tiny.
5. **Terminal fixed-height box + copy snack (+ optional psutil strip)** — Sherlock `screens/settings_screen.py:1408-1427,1324-1333`, `core/logger_handler.py:55-89`; animepahe-tv `screens/settings_screen.py:113-134`, `core/logger_handler.py:79-91`. Avoids the dialog-burst bug Sherlock already documents; tiny.
6. **Update https-safelist + offline changelog fallback** — Sherlock `services/update_service.py:24-33`, `core/changelog.py`, `components/update_dialog.py:196-219`; animepahe-tv `services/update_service.py:15-34`, `components/update_dialog.py:21-76`. Trust + offline correctness; small.
7. **Online-restored toast + lifecycle re-probe** — Sherlock `main.py:1854-1907`; animepahe-tv `main.py:224-239`. Closes the stale-offline-on-resume hole; tiny.
8. **Type `open_sheet/close_dialog` in `ControllerMethods` + document root-back guard** — Sherlock `state/controller_ctx.py:66-79`, `main.py:471-511`; animepahe-tv `state/controller_ctx.py:18-46`, `app_shell.py:121-122`, `main.py:251-275`. Prevents the next dialog/back regression; tiny.
9. **`shared_haptics`/`shared_share` getters** — Sherlock `core/shared_services.py:82-99`; animepahe-tv `core/shared_services.py:23-66`. Needed the day share/haptics appear; trivial.
10. **Search shape validators + pasted-URL normaliser** — Sherlock `screens/home_screen.py:325-347,504-553`; animepahe-tv `screens/search_screen.py:174-201,248-252` (has clamp + guards, lacks shape/URL handling). Only if junk queries reach the worker; small.
11. **Search-result snapshot LRU** — Sherlock `core/state.py:149-160`, `main.py:1462-1624`; animepahe-tv has durable `services/store.py` + `services/cache.py` but no query cache. Only if repeat searches feel slow; medium.
12. **Small pure helpers on demand** (`_safe_filename`, `format_count`/`human_date`, `test_id`) — Sherlock `app_shell.py:43-56`, `core/format.py`, `core/constants.py:8-12`; no animepahe-tv counterpart. Pull individually when the need lands; trivial each.

Explicitly **not** recommended: UMP consent flow (AdMob-only, Sherlock `services/ad_service.py:90-131` vs animepahe-tv Yandex `services/ads.py`); scan OS notifications (no long scan in animepahe-tv, Sherlock `services/scan_notify.py`); permute/recursive search, enrichments, graph, exports, Sites DB (Sherlock domain features with no animepahe-tv analogue); phone `NavigationBar`-only chrome (animepahe-tv's rail-for-TV in `app_shell.py:39-50` is the correct TV adaptation).

---

## 4. Things animepahe-tv already does equivalently (no port needed)

- **Controller owns services; shell owns navigation** — `main.py:52-162` + `app_shell.py:53-211` mirror Sherlock `main.py:99-156,349-468` + `app_shell.py:1020-1227`; `state/controller_ctx.py:18-46` documents the same mutate-in-place contract as Sherlock `state/controller_ctx.py:45-82`.
- **3-way theme cycle** — `screens/home_screen.py:214-225` (`DARK→LIGHT→SYSTEM`) + `main.py:164-191` (restore/save via store) + `main.py:77-81` (SYSTEM default, Outfit on both themes) match Sherlock `components/app_header.py:109-145` + `main.py:357-364,518-524`. Only the Settings picker + observable (P1) are missing.
- **Tracked `spawn`** — `core/tasks.py:13-27` is the same done-callback pattern as Sherlock `core/tasks.py:18-31`.
- **Snackbar guard** — `core/notify.py:25-52` (skip same-instance re-show, never pop a real dialog) is the newer-correct variant of Sherlock `core/notify.py:18-52` (pop-and-replace-if-snack). Keep animepahe-tv's; do not "port" Sherlock's older guard.
- **Shared-services mount-once** — `core/shared_services.py:59-73` + `main.py:127-129` match Sherlock `core/shared_services.py:32-61` + `main.py:384-387` in shape; breadth gap (haptics/share) is P9, not architecture.
- **Diagnostics terminal** — `screens/settings_screen.py:95-190` (500-line buffer, Courier New, telemetry strip, copy/clear/close) + `core/logger_handler.py:21-91` (ring buffer, root attach) port Sherlock `screens/settings_screen.py:1307-1449` + `core/logger_handler.py:21-52`. Remaining deltas are P5 details.
- **Setting row/card primitives** — `_setting_row` (`screens/settings_screen.py:45-80`) + `_settings_card` (`settings_screen.py:34-42`) match Sherlock `screens/settings_screen.py:129-224` minus `stacked` narrow mode (P3-adjacent, low priority on TV).
- **Search debounce placement** — `screens/search_screen.py:172` (`use_debounce(query,250)`) filtering suggestions only (`search_screen.py:240-246`) + `hooks/use_debounce.py:15-36` mirror Sherlock `screens/home_screen.py` + `hooks/use_debounce.py:17-41`. Correct in both: debounce never gates the network call.
- **Search guards ordering** — empty → double-submit → offline → CF-gate (`screens/search_screen.py:174-201`, `_pick` at `203-226`, `_warn_offline` at `228-235`) mirror Sherlock `_submit_guards` (`screens/home_screen.py:521-553`); offline-before-CF layering matches Sherlock's offline-before-kill rule.
- **Empty states** — `components/empty_state.py:14-68` (icon/title/message/action + `autofocus_action` for TV) covers Sherlock `components/empty_state.py:18-88`; TV autofocus is the correct addition.
- **Canonical banner rule** — `components/banner_ad.py:1-11` states the Sherlock house rule verbatim; placements in Home feed (`screens/home_screen.py:493,504`) + Settings (`screens/settings_screen.py:342`) follow it. Only pooling (P3) is missing.
- **Update pill + dialog + bg check** — `_version_pill` morph (`screens/home_screen.py:109-157`), `components/update_dialog.py:21-76` (mandatory-aware), `_check_for_updates_bg` (`main.py:193-198`) mirror Sherlock `components/app_header.py:31-95`, `components/update_dialog.py:154-235`, `main.py:1810-1826`. Only safelist/changelog (P10) are missing.
- **Connectivity listener** — `_mount_connectivity` + `_on_connectivity_change` (`main.py:204-239`) + `is_online`/`connectivity_version` (`core/state.py:72-73`) mirror Sherlock `main.py:376-388,1843-1870`. Only online-toast/lifecycle (P11) are missing.
- **Error funnel + page handler** — `_show_error_snackbar` (`main.py:241-244`) + `_on_page_error` (`main.py:1252-1260`) + `ERR_*/LBL_*` (`core/constants.py:5-39`) mirror Sherlock `_show_snack` (`main.py:1830-1834`) + `on_error` (`main.py:1836-1839`) + `core/constants.py:73-86`.
- **Dialog portal + back registry** — `ft.use_dialog(active_dialog)` (`app_shell.py:117-120`) + `core/dialogs.py:18-47` (top-check before pop) mirror Sherlock `app_shell.py:1029-1035` + `core/notify.py:40-50`. Keep both.
- **Atomic durable store** — `services/store.py:47-99` (temp-file + `os.replace`, singleton, sections) + `services/cache.py` sweep match Sherlock `services/storage_service.py:146-217` in durability; web-branch/corrupt-backup are web-only/non-issues here.
- **About/support** — Settings about card (`screens/settings_screen.py:343-357`) + `components/support_dialog.py` (GitHub-issues routing) cover Sherlock's about card (`screens/settings_screen.py:1113-1165`); support dialog is the correct animepahe-tv addition (Sherlock has no equivalent).
- **TV-only craft Sherlock lacks** (keep, do not regress): `NavigationRail`-for-TV + window-class switch (`app_shell.py:39-50,174-211`), `FocusManager` + `FocusScope` Back delivery (`core/focus_manager.py`, `hooks/use_focus_scope.py:18-...`, `app_shell.py:380-409`), focus-ring pager/cards (`components/pagination.py:17-116`, `components/focus_styles.py`), player overlay + resolve overlay + error card (`app_shell.py:133-144,214-...`), provider router + source-test panel (`services/router.py`, `screens/settings_screen.py:247-332`), downloads/favorites/continue-watching (`core/state.py:84-122`, `services/downloads.py`, `services/store.py`).
