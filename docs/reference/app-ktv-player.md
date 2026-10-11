# KTV Player → animepahe-tv port reference

Study of the house-standard production TV player (`C:\Users\nwoki\.zcode\workspace\default\ktv-player\src`)
against the animepahe-tv baseline (`C:\Users\nwoki\ad-extensions\sources\animepahe-tv\src`).
Read from source, October 2026. Every claim cites its file; line numbers are
approximate to the revision read.

Conventions: **KTV** = `ktv-player/src/...`, **AP** = `animepahe-tv/src/...`.

---

## 1. Feature inventory (KTV, every user-facing ability)

### 1.1 Immersive player

| # | Ability | KTV source |
|---|---------|------------|
| P1 | Fullscreen in-app playback (flet-video `Video`, autoplay, wakelock, `BoxFit.CONTAIN`, `FilterQuality.MEDIUM`) | `components/player/immersive_player.py:304-359` |
| P2 | Adaptive controls: touch branch (double-tap seek, seek/volume/brightness gestures, 2× long-press) + desktop/TV branch (scroll-volume, 4 s hover hide) | `components/player/controls.py:352-405` |
| P3 | Per-branch fresh control instances (single-parent rule; stashed as lists via `_stash`) | `components/player/controls.py:57-68`, `immersive_player.py:1063-1070` |
| P4 | Loading overlay (spinner + status) shown from first frame; Go Back reachable immediately, plus tap-on-overlay-to-close | `immersive_player.py:629-640`, `905-921`, `880-900` |
| P5 | Final error card (spinner hidden, message + Retry + Go Back) | `immersive_player.py:1208-1221` |
| P6 | 20 s watchdog: any loading/reconnect state with no load/position/error event becomes the error card | `immersive_player.py:24-27`, `1155-1181` |
| P7 | Live reconnect budget (`STREAM_RECONNECT_MAX = 5`, `core/constants.py:218`), counter deliberately NOT reset on success, manual retry re-arms | `components/player/handlers.py:639-696`, `immersive_player.py:1223-1248` |
| P8 | Manual retry rebuilds playlist and replays; watchdog restarted; PiP gated on actual playing | `immersive_player.py:1223-1248` |
| P9 | Seek-error swallow (`Cannot seek` / `force-seekable` at the live edge) with variant/audio context in the log | `immersive_player.py:1190-1200` |
| P10 | Speed chip cycling 0.25/0.5/1.0/1.25/1.5/2.0, REFUSED on live channels with a toast | `components/player/handlers.py:15-37`, `immersive_player.py:288-295` |
| P11 | Speed re-applied after every playlist swap (swap resets native rate to 1.0) | `immersive_player.py:1031-1041` |
| P12 | HLS quality pinning (variant index → proxy rewrites master to one variant) + Auto | `immersive_player.py:1047-1053`, `925-943` |
| P13 | External audio rendition pinning (by NAME, dropped renditions removed, pinned one forced DEFAULT/AUTOSELECT=YES) | `immersive_player.py:1055-1061`; `services/hls_proxy.py:631-665` |
| P14 | One-shot option probe after first playback; quality/audio chips render a default label immediately so layout never shifts | `immersive_player.py:1118-1136`; `components/player/controls.py:116-170` |
| P15 | Quick quality/audio picker dialog (from chip) + full Player Settings dialog (quality/audio dropdowns with stale-pin fallback, aspect fit, snapshot prefs, subtitle size) | `components/player/handlers.py:191-302`, `308-618` |
| P16 | VOD resume: position loaded from history at construction (skips < 3 s and within-5-s-of-end), deferred polled seek (40 × 0.1 s for real duration), "Resumed from HH:MM:SS" toast | `immersive_player.py:174-202`, `791-845` |
| P17 | Position checkpoints every 10 s (survives app kill while minimized), awaited bounded save on close (3 s), orphan-tracked save on unmount, reset-to-0 near end | `immersive_player.py:766-789`, `1250-1298`, `374-391`, `1328-1342` |
| P18 | Snapshots: `video.take_screenshot()`, Android MediaStore insert (scoped-storage-safe) with filesystem fallback + gallery scan, safe filename, toast + click | `immersive_player.py:558-620`, helpers `64-126` |
| P19 | Subtitles: Auto/Off/Local-file picker (singleton FilePicker, `.srt`/`.vtt`, web-bytes path), persisted size (small 16 / medium 22 / large 30) | `components/player/handlers.py:40-188`; `immersive_player.py:404-432`; settings `308-361` |
| P20 | In-player favorite star (hidden for deep-link plays), optimistic toggle + click + awaited DB save, state recomputed per build | `components/player/controls.py:173-238` |
| P21 | In-controls toast chip (the only Flet surface visible in native fullscreen) + fullscreen-active tracking | `components/player/controls.py:71-113`; `utils/notifications.py:22-46`, `90-121` |
| P22 | Android PiP: availability probe, user button, auto-PiP armed only while actually playing (API 31+ `setAutoEnterEnabled`, API 26-30 lifecycle fallback), background flags synced so minimize hands a live frame to PiP, disarm on error/complete/close | `immersive_player.py:204-212`, `434-538`; `services/pip_service.py:51-160` |
| P23 | Pre-roll interstitial before every playback (20 s timeout, skipped on premium/non-mobile, close during ad cancels playback) | `immersive_player.py:641-655` |
| P24 | YouTube URLs resolved to direct streams (InnerTube, no yt-dlp binary); history key stays the original URL so resume survives | `immersive_player.py:660-680`; `services/youtube_resolver.py:338+` |
| P25 | mpv tuning: `cache yes / cache-secs 5 / demuxer-max-bytes 50M / demuxer-max-back-bytes 10M / framedrop vo / hr-seek-framedrop yes / network-timeout 10` (10 s, not the 60 s stock default) | `immersive_player.py:332-343` |
| P26 | Close path that cannot strand the user: back routes through one outer close (awaited save → stop bounded 2 s → playlist clear → pop); double-close guarded | `immersive_player.py:1328-1368`; `main.py:492-518` |

### 1.2 Loopback HLS proxy (`services/hls_proxy.py`, 850 lines)

- Local hand-rolled HTTP/1.1 server on 127.0.0.1 with bounded reads (5 s timeout, 64 header lines, 8 KB headers, 16 KB query): `:348-351`, `_handle_client` `:353-505`.
- Upstream httpx client: HTTP/2, 50 keepalive/100 max connections, per-host TLS exemptions (`insecure_hosts`, verification ON by default): `:145-205`, `:134-137`.
- `get_proxy_url(url, referer, headers, variant, audio)` — base64url query encoding: `:244-271`.
- Playlist rewriting: variant pinning, `#EXT-X-MEDIA` audio proxy + pin, `#EXT-X-MAP` init segments, `#EXT-X-KEY` **and** `#EXT-X-SESSION-KEY` key URLs, nested-playlist heuristic with fetch-time Content-Type self-correction, non-playlist bytes streamed as `application/octet-stream`: `:507-567`, `:569-731`, `:795-813`.
- Segment/key passthrough streams 256 KB zero-copy chunks, forwards Range + conditional validators + ETag/Last-Modified/Cache-Control, mid-stream death ends the stream honestly: `:733-793`.
- Upstream error phrases forwarded verbatim (strict players reject "Unknown"): `:837-850`.
- `fetch_master` memoized per URL (30 s TTL) with shared UA; `PlaylistFetchError` distinguishes 404 from dead host: `:282-344`.
- Strict query validation: flat string map only, length caps, CRLF rejection, hop-by-hop header stripping, non-GET → 405: `:440-477`, `:379-386`.

### 1.3 TV interaction / D-pad / remote

- Declarative focus cue only: `card_button_style()` — per-`ControlState` border (FOCUSED 2.5 px PRIMARY) + overlay tint; no `on_focus` scale mutation (frozen `@ft.component` rule): `components/focus_styles.py:17-73`.
- Cards are Button-family controls (Container cannot take D-pad focus — verified against flet 1.0.4): AP's own docstring confirms the rule — `AP components/focus_styles.py:7-15`.
- `focus_scope(child, on_back)` — plain function returning `Container(KeyboardListener(autofocus=True))`; Back/Escape/BrowserBack keys, re-entrancy guard, logged failures; expanding Container is load-bearing (unbounded Stack = white player with sound): `hooks/use_focus_scope.py:18-72`.
- Desktop shortcuts hook: Ctrl/Cmd+K search, Ctrl/Cmd+R refresh via single-slot `page.on_keyboard_event` with chaining + identity-guarded unmount cleanup; Esc backs out unless a `/play` view is open (no double-close): `hooks/use_keyboard_shortcuts.py:60-126`.
- Leanback detection (`android.software.leanback` via shared android_bridge): `services/tv_detect.py` + `services/android_bridge.py:191 lines`.
- Back underlay (`/blank` at index 0) so system back can never expose an empty tree: `main.py:546+` (`_ensure_back_underlay`).
- Constants for the 10-foot UI: `FOCUS_SCALE 1.08`, `FOCUS_BORDER_WIDTH 3.5`, `FOCUS_ANIM_DURATION 200`, `COMFORTABLE` density as deliberate TV choice: `core/constants.py:238-241`; `core/theme.py:176-178`.

### 1.4 Channel / content management

- Tiered channel provider with cache-dir playlist cache: `channels/provider.py:24+` (`_cache_dir`, `_cache_file`, `_cache_path`, `ChannelProvider`).
- M3U parsing: `services/m3u_parser.py:65 lines`; IPTV fetch with `PlaylistFetchError`: `services/iptv_service.py:81 lines`.
- Liveliness: LRU cache (500 entries, 300 s TTL), multi-subscriber fan-out, bounded 5000 dirty queue, newest-first DB preload (`services/liveliness.py:111`); 4-worker TaskPool + shared 4-permit probe semaphore, HEAD then ranged-GET fallback (405/501, HEAD-blocking middleboxes), pool-exhaustion vs remote-failure distinguished (unknown never paints red), shielded persist on shutdown (`services/liveliness_checker.py:239`); msgpack cache-dir store, atomic fsync+rename writes, 30-day prune, legacy JSON + DB migration (`services/liveliness_store.py:164`).
- No probes while offline; offline transition resets dots to neutral (`main.py:332-351`).
- Favorites: idempotent async toggle (re-read after write), sync fire-and-forget with in-flight dedupe (`utils/favorites.py:75`).
- History helpers: credential-stripping `display_name`, `resolve_entry` normalizing str/dict legacy shapes, logo disk-cache warmup on miss (`utils/history.py:82`).
- Logo disk cache: size-capped streaming downloads, failure recency, oldest-evict, worker pool (`services/logo_cache.py:369`).
- Per-CDN header overrides by host suffix (`CDN_HEADER_OVERRIDES`, `core/constants.py:184-188`) merged per request (`merge_cdn_headers`, `main.py:45-67`); valid-scheme allowlist + sensitive-path guard (`core/constants.py:170-183`; `core/url_validator.py:123`).
- Channel grid with pagination (`PAGE_SIZE = 24`) and per-page liveliness seeding; native-ad row every 24 rows (`AD_ROW_INTERVAL`, `core/constants.py:191-192`; `components/channel_grid.py:213`).
- Filter pills (country/category/custom) with counts: `components/filter_bar.py:417`; `utils/channels.py:158`.
- Custom content dialog (single channel vs playlist, URL validation, add cooldown 5 s): `components/add_custom_content_dialog.py:276`.
- Local device library: storage/MediaStore scan, SAF folder picking, permission flow, MediaStore delete with consent, cached video thumbnails with prewarm (`services/local_scanner.py:662`, `services/video_thumbnails.py:366`, `screens/local_screen.py`).
- Deep links IN (`ktv://` with base64 URL/title/headers) hide the favorite star and finish() the activity on close where needed: `core/deeplink.py:157`; `services/pip_service.py:163-186` (`exit_app`).

### 1.5 Theme

- **Two-way** toggle only (dark ↔ light Switch in Settings, §2.3.0-regression reactive mirror): `utils/theme_utils.py:16-44`; `screens/settings_screen.py:482-496`, `587-601`.
- Theme lives on `page.theme_mode` (SYSTEM default at boot); explicitly NO duplicate field in `AppState`: `main.py:139-143`; `core/state.py:26-29`.
- Persisted as `"dark"/"light"` in DB settings; restored at boot: `main.py:188-192`.
- Helpers: `is_dark` (explicit wins, SYSTEM follows device, dark fallback), `get_surface`/`get_card_bg`/`get_border_color`/`grey_dim`, full dark+light `ft.Theme` (dialog/card/nav/appbar/search themes, page transitions per platform, PRIMARY focus): `core/theme.py:227`.

### 1.6 Ads + monetization (AdMob via flet_ads)

- Unit IDs: banner / interstitial / native (`services/ad_service.py:22-24`).
- UMP consent: open-by-default, mobile-only flow, failed UMP ≠ denial, privacy-options form with honest status strings (`form_shown|not_required|no_manager|error:`): `:53-112`.
- Three banner shapes (native 300×250, standard 320×100, anchor 320×50) in a labeled support container; all gated on mobile + non-premium + consent: `:114-199`.
- Interstitial: **preloaded**, load-event awaited (10 s), preloaded shown first, on-demand fallback (10 s), 30 s close wait, keep-alive refs in `page.services` against service GC, retry with backoff (5 × 30 s), re-preload after every close, clean `close()` releasing services + joining the retry: `:201-385`, `:257-271`.
- Premium = Kiri License ECDSA entitlement: offline token verify, boot load, periodic reconcile + checkout watch, listener fan-out (`services/premium_service.py:377`, `services/license_token.py:311`, `services/kiri_license.py:475`); platform-honest toasts (`utils/notifications.py:143-161`).

### 1.7 Services architecture / store / tasks

- No `core/tasks.py`: fire via `page.run_task(coro_fn)` (takes a function, not a coroutine — the `_await_result` shim, `immersive_player.py:39-42`); fire-and-forget DB writes tracked in `_orphan_tasks` so shutdown can await them: `:1289-1298`, `:33-36`.
- Generic AnyIO worker pool (`TaskPool`: supervisor, workers, bounded queue, drain-on-stop): `services/anyio_pools.py:176`.
- Shared httpx client (HTTP/2 transport, connect-only retries, shutdown-only close, single owner): `services/http_client.py:67`.
- Single JSON database manager (history + positions + favorites + playlists + custom channels + settings): `database/manager.py` (`save_history:222`, `update_history_position:250`, `get_history_entry_sync:275`, favorites `:371-396`).
- Cache-vs-durable split: re-derivable data (liveliness verdicts) lives in `FLET_APP_STORAGE_CACHE` msgpack, never in the durable DB: `services/liveliness_store.py:1-20`.
- Crash reporter (file per crash, old-crash cleanup, page error hook): `core/crash_reporter.py:162`.
- Tiny Android-only UI clicks (lazy `ToneGenerator` singleton, STREAM_MUSIC): `utils/sfx.py:78`.
- Dual-layer notify (SnackBar + fullscreen toast chip, 3 s auto-hide, warning/error colors): `utils/notifications.py:124-140`.

### 1.8 Everything else notable

- Update flow: `version.json` on main, `UpdateInfo` dataclass (version/build/type/mandatory/title), mandatory modal that re-shows on dismiss, announcement type, in-dialog re-check, markdown changelog with link taps, build-number compare tolerating publisher typos: `services/update_service.py:167`; `components/version_dialog.py:371`.
- `OfflineFlow` retry/skip-to-offline card: `components/offline_flow.py:49`.
- `EmptyState` plain function (icon/title/message/optional autofocused action): `components/empty_state.py:54`.
- `LoadingState` spinner + label: `components/loading_state.py:52`.
- Onboarding (terms + country with TV nav hint): `screens/onboarding_screen.py`; `core/constants.py:50-62`.
- Settings: appearance, region picker, history/library management with busy states, activity terminal (copy/clear/refresh/paged), version row, legal: `screens/settings_screen.py`.
- Search screen, recently-watched screen + carousel sharing `utils/history.py`.
- Per-screen `on_play(url, title)` contract (title defaults None): `utils/history.py:17`; `screens/home_screen.py:164-192`.

---

## 2. Implementation patterns worth porting

Each row: what KTV has → the AP file that lacks it → the AP surface it improves.

| # | KTV pattern (file + ref) | AP gap (file + ref) | Improves |
|---|--------------------------|---------------------|----------|
| 1 | Snapshots: `take_screenshot` + MediaStore insert + fsync-free fallback + gallery scan (`immersive_player.py:558-620`, `_save_screenshot_android:64-112`, `_scan_for_gallery:115-126`) | `AP components/player/immersive_player.py` — no snapshot path at all (its own docstring lists snapshots as dropped, `:4-5`) | Episode player: viewers snapshot scenes; desktop fallback is ~15 lines |
| 2 | Fullscreen-aware toasts: `register_fullscreen_toast` + `_dispatch` to chip AND SnackBar (`utils/notifications.py:22-46`, `90-131`) | `AP core/notify.py:91` (`show_snack` only) + player top bar has no toast chip (`immersive_player.py:350-357`) | Resume/speed/skip confirmations are invisible in native fullscreen today |
| 3 | Local subtitle files via boot-singleton FilePicker + persisted size (`handlers.py:40-188`, `open_player_settings:308-361`; KTV `main.py:147-156`) | `AP components/player/immersive_player.py:209-218` (fixed size-16 config, no picker); no FilePicker anywhere in AP | Accessibility + fansub viewing; size pref is a 3-line DB setting |
| 4 | Aspect-fit switcher (CONTAIN/COVER/FILL) in player settings (`handlers.py:363-368`) | AP player hardcodes `fit=CONTAIN` (`immersive_player.py:206`) | Cropping letterboxed encodes; trivial dropdown |
| 5 | Unmount safety-net position save via `_orphan_tasks` (`immersive_player.py:33-36`, `374-391`, `1289-1298`) | AP relies on checkpoint loop + close path only (`immersive_player.py:737-747`, `995-1017`); no `will_unmount` save | Overlay-removal races lose resume; ~15 lines |
| 6 | PiP service: `is_pip_supported/api_level/enter_pip/set_auto_pip/exit_app` + arm-only-while-playing + background-flag sync (`services/pip_service.py:178`; `immersive_player.py:434-538`) | No PiP in AP (docstring `:4-5`); AP hardcodes `pause_upon_entering_background_mode=True` (`immersive_player.py:202`) | Background audio + multitasking on phones; TV build unaffected (feature-gated) |
| 7 | `focus_scope` as a plain function with re-entrancy guard + mount-bounds comment (`hooks/use_focus_scope.py:18-72`) | AP `hooks/use_focus_scope.py` is a `@ft.component` (frozen-subtree hazard — AP's own shell comment says so, `app_shell.py:380-388`) | Replace component with function; kills a known crash class |
| 8 | Keyboard-handler chaining + identity-guarded cleanup (`hooks/use_keyboard_shortcuts.py:110-123`); Esc skips `/play` (`:84-98`) | AP `core/focus_manager.py:28` **overwrites** `page.on_keyboard_event` with no chaining — any second installer silently kills the first | Correctness of global Back as more installers appear |
| 9 | Mandatory-update modal discipline (modal + re-show on dismiss) + `UpdateInfo` dataclass + announcement type + in-dialog re-check (`components/version_dialog.py:253+`; `services/update_service.py:47-63`) | AP `components/update_dialog.py:76` (mandatory branch exists, no re-show; dict, no type field); AP `services/update_service.py:34` | Users can back out of mandatory security updates today |
| 10 | Crash reporter: per-crash files, rotation, page hook (`core/crash_reporter.py:162`) | AP has log buffer + terminal but no crash persistence (`core/logger_handler.py:91`) | Field diagnosis for native-bridge failures |
| 11 | Desktop shortcuts (Ctrl+K search, Ctrl+R refresh) as a mount-once hook (`hooks/use_keyboard_shortcuts.py:99-109`) | No keyboard shortcuts in AP | Desktop/TV-keyboard usability; ~40 lines |
| 12 | CDN host-suffix header overrides merged per request (`core/constants.py:184-188`; `main.py:45-67`) | AP carries per-source `headers` (`core/state.py:Source`) but no host-level default map | New CDNs work without touching every source row |
| 13 | Toggle-save race guard: cancel pending theme write so fast double-toggle persists the FINAL mode (`utils/theme_utils.py:34-44`) | AP home-header toggle fires raw `save_theme_mode` per tap (`screens/home_screen.py:438-449`) | Cheap write-ordering fix if saves ever overlap |
| 14 | Theme `ft.Theme` completeness: dialog/card/nav/appbar/search themes + explicit per-platform page transitions (`core/theme.py:126-227`) | AP themes set only scheme + focus + density (`core/theme.py:108-138`) | Visual consistency of dialogs/cards/transitions |
| 15 | `OfflineFlow(on_retry, on_skip)` card (`components/offline_flow.py:49`) | AP has offline labels + `connectivity_version` bump (`main.py:224-234`) but no retry/skip surface | Dead-end browsing when the CDN is down but cache could serve |
| 16 | `toggle_favorite_async` re-read-after-write idempotency + sync dedupe guard (`utils/favorites.py:75`) | AP `services/store.py:352-366` (`toggle_favorite`) reads-modifies-writes without re-read | Rapid double-tap on the detail favorite can clobber |
| 17 | Upstream reason-phrase forwarding over the proxy (`hls_proxy.py:837-850`) | AP `_send_response` uses its own table only (`AP services/hls_proxy.py:786-801`) | Strict-player rejection of forwarded CDN errors; 3 lines |
| 18 | Native-ad row cadence in content grids (`AD_ROW_INTERVAL = 24`, `core/constants.py:192`) | AP monetizes banners + interstitials only (`components/banner_ad.py:84`, `services/ads.py:111`) | Extra inventory without new formats (needs Yandex native or banner rows) |
| 19 | Consent-shape honesty: open-by-default, failure ≠ denial, status-string returns (`ad_service.py:53-112`) | AP hardcodes `user_consent=True` (`services/ads.py:46`) | Regulatory posture if Yandex UMP/consent is ever wired |
| 20 | `display_name` credential-stripping title fallback + legacy str/dict `resolve_entry` (`utils/history.py:20-67`) | AP continue-watching records are well-formed today (`services/store.py:171-203`) — defensive only | Future-proofing if record shapes ever drift |
| 21 | `channels_hash` (order-sensitive sha256 over url/group/country/name) as the memo-invalidation key (`core/state.py:88-106`) | AP uses per-collection version counters (`core/state.py`) — equivalent; no change needed, listed for completeness | — |
| 22 | Player settings double-open guard on the instance (`handlers.py:522-527`) | AP `open_stream_settings` has no re-entry guard (`immersive_player.py:816-910`) | Double-tap settings chip stacks dialogs |

---

## 3. Ranked port opportunities

Ranked by (user value × AP fit) ÷ effort. "Not ported" = verified absent
(deliberately different domains are in §4 instead).

### P0 — do first

1. **In-player toast chip + dual dispatch.** KTV `utils/notifications.py:32-46,90-131`
   + chip construction `components/player/controls.py:86-113`.
   AP `core/notify.py:show_snack` renders only via `page.show_dialog` — invisible
   in native fullscreen, exactly the hole KTV's module docstring (`:1-10`)
   describes. AP surface: `components/player/immersive_player.py:350-357`
   (top bar) + every `show_snack` call after resume/seek/skip.
2. **Local subtitle Picker + persisted size + aspect fit.** KTV
   `components/player/handlers.py:40-188` (`pick_subtitles`),
   `:308-368` (size/fit application), `immersive_player.py:404-432`
   (size table). AP `components/player/immersive_player.py:209-218`
   (fixed size-16, Auto-only). Needs the boot-singleton FilePicker
   (KTV `main.py:147-156`); AP has none. AP surface: player bottom bar
   (new subtitle button) + `open_stream_settings` (`:816-910`).
3. **Snapshot button.** KTV `immersive_player.py:558-620` + `:64-126`.
   AP docstring admits it dropped (`immersive_player.py:4-5`). Desktop
   fallback path works without jnius; MediaStore path is Android-only and
   isolated. AP surface: player bottom bar next to the fullscreen button
   (`:347`).

### P1 — high value, small

4. **Unmount safety-net save.** KTV `immersive_player.py:374-391`
   (`will_unmount` + `_position_saved` latch) + `_orphan_tasks:33-36,1289-1298`.
   AP `components/player/immersive_player.py:995-1017` saves only on the
   close path; overlay-removal races skip it.
5. **Mandatory-modal discipline + UpdateInfo typing.** KTV
   `components/version_dialog.py:253+`, `services/update_service.py:47-63`.
   AP `components/update_dialog.py:21-55`, `services/update_service.py:34`.
   Re-show on dismiss + `type` field (announcement vs update) + build-number compare.
6. **Plain-function FocusScope.** KTV `hooks/use_focus_scope.py:18-72` →
   AP `hooks/use_focus_scope.py` + `app_shell.py:380-388` (which already
   works around the component form with a hand-rolled listener; adopt the
   KTV function and delete the workaround).
7. **FocusManager chaining.** KTV `hooks/use_keyboard_shortcuts.py:110-123` →
   AP `core/focus_manager.py` (single-slot overwrite). Chain + identity-guarded
   restore before a second installer appears.
8. **Favorite-toggle idempotency.** KTV `utils/favorites.py:19-43` →
   AP `services/store.py:352-366`. Re-read-after-write; keep AP's dict shape.

### P2 — medium

9. **Crash reporter.** KTV `core/crash_reporter.py:88-153` →
   AP `core/logger_handler.py` (buffer exists; add file persistence +
   rotation + `install_crash_handler` at boot in `main.py`).
10. **CDN header-override map.** KTV `core/constants.py:184-188` +
    `main.py:45-67` → AP `core/config.py` / `services/router.py:299`
    (per-source `headers` already exist in `core/state.py:Source`; add the
    host-suffix fallback layer).
11. **Player settings double-open guard.** KTV
    `components/player/handlers.py:522-539` → AP
    `components/player/immersive_player.py:816-910` (`_settings_open` flag).
12. **Theme completeness.** KTV `core/theme.py:126-227` (dialog/card/nav/
    search themes, transitions) → AP `core/theme.py:108-138`. Keep AP's
    palette + surface-role pinning; add the missing theme slots.
13. **Offline retry/skip card.** KTV `components/offline_flow.py:13` →
    AP browse screens (AP `main.py:224-234` already detects the transition;
    render the card where grids go empty offline).
14. **Settings Appearance section.** KTV `screens/settings_screen.py:587-601`
    → AP `screens/settings_screen.py` (no theme row at all — verified by
    grep; the only toggle is the home-header 3-way cycle,
    `screens/home_screen.py:214-224,438-449`). Add the cycle to Settings
    for discoverability on TV (header button is far from focus start).
15. **Upstream reason-phrase forwarding.** KTV
    `services/hls_proxy.py:837-850` → AP `services/hls_proxy.py:786-801`
    (add the `reason_phrase` parameter).

### P3 — consider / low priority

16. **PiP.** KTV `services/pip_service.py:178` + arm/disarm
    (`immersive_player.py:458-538`). Phone-only value; TV build unaffected.
    AP must also flip `pause_upon_entering_background_mode`
    (`immersive_player.py:202`) to PiP-aware sync (KTV `:434-454`).
17. **Desktop shortcuts** (Ctrl+K / Ctrl+R). KTV
    `hooks/use_keyboard_shortcuts.py:99-109`. Desktop/TV-keyboard only.
18. **SFX clicks.** KTV `utils/sfx.py:78`. Android-only; pairs with the
    toast chip (audio confirms where the chip cannot draw).
19. **Ad-row cadence** (`AD_ROW_INTERVAL`). Needs a Yandex native/banner
    row unit; KTV uses AdMob native (`ad_service.py:138-157`).
20. **Toggle-save race guard** (`utils/theme_utils.py:34-44`). One-line
    insurance; AP's save path is a single await today.
21. **Consent-shape honesty** for ads. Pattern-level only (different SDK):
    KTV `ad_service.py:53-112` vs AP `services/ads.py:42-51`.

### Explicitly NOT recommended (verified, not assumed)

- `insecure_hosts` TLS exemptions (KTV `hls_proxy.py:134-137,150-164`):
  AP's primp client negotiates the hosts fine; do not weaken verification.
- `_looks_like_playlist` extension heuristic (KTV `:569-586`): AP already
  removed this class of bug by routing media lines to `/segment`
  unconditionally (AP `hls_proxy.py:681-691` with the `.jpg-segment` note).
- Kiri License / premium pack (`premium_service.py`, `license_token.py`,
  `premium_pack_url`, `core/constants.py:199-217`): different business
  model; AP monetizes via Yandex + rewarded early-access.
- Preloaded interstitials (KTV `ad_service.py:201-292`): Yandex API is
  one-shot per the official example (AP `services/ads.py:4-11`); the
  keep-alive-in-`page.services` discipline still applies and AP already
  follows it (`:60-64,74-80`).

---

## 4. Things animepahe-tv already does better or equivalently

Stated plainly, with sources on both sides.

1. **Theme cycle.** AP has the 3-way DARK → LIGHT → SYSTEM cycle with
   per-mode icons and persistence of `"system"`
   (`screens/home_screen.py:214-224`, `main.py:164-191`). KTV has only a
   2-way dark↔light Switch (`utils/theme_utils.py:16-29`) and cannot even
   restore `"system"` (`main.py:188-192`). **AP wins; nothing to port —
   the assignment premise is backwards.**
2. **HLS proxy transport.** AP uses primp with Chrome impersonation because
   the hosts fingerprint TLS and 403 plain httpx
   (AP `services/hls_proxy.py:162-170`); KTV uses httpx/HTTP-2. AP also
   fixed the extension-heuristic bug class KTV still carries (§3,
   not-recommended). **AP wins.**
3. **Provider failover.** AP's `ProviderRouter` — ordered failover,
   per-provider circuit breaker (3 failures → OPEN, half-open probe,
   `force=True` bypass), per-op latency/error health surfaced in Settings
   (`services/router.py:40-155`; `screens/settings_screen.py:288-...`) —
   exceeds KTV's liveliness dots for AP's VOD domain. KTV liveliness itself
   is correctly **N/A** (no live content in AP).
4. **Rewarded ads.** AP `build_rewarded_ad` unlocks the episode past the
   free line for 24 h (`services/ads.py:84-111`, `store.py:382-400`).
   KTV has no rewarded flow at all. **AP wins.**
5. **App-open ad.** AP shows one on SDK init (`main.py:1331-1343`,
   `services/ads.py:69-81`). KTV has no app-open format. **AP wins.**
6. **Download-for-offline.** AP `DownloadManager` (segment workers,
   manifest, resume, atomic writes, progress throttle —
   `services/downloads.py:447`) vs KTV's local-device-file library
   (`services/local_scanner.py:662`). Different features, both complete
   in their domain; AP's is the right shape for metered-network anime
   viewers. **Equivalent, correctly scoped.**
7. **Shared services.** AP `core/shared_services.py:73` (one Clipboard +
   one UrlLauncher, lazy mount) vs KTV's per-call service appends.
   **AP wins** (this is the pattern KTV should backport).
8. **Background-task hygiene.** AP `core/tasks.py:spawn` (named tasks,
   failure-logging done-callback) is cleaner than KTV's bare
   `loop.create_task` + `_orphan_tasks` set. Only the shutdown-await
   half (KTV `_orphan_tasks`) is worth taking back (§2.5). **AP wins.**
9. **Surface-role pinning.** AP `_DARK/_LIGHT_SURFACE_ROLES`
   (`core/theme.py:79-106`) neutralizes Material's purple-tinted fallback
   roles — a completeness KTV's theme lacks. **AP wins** (take only the
   missing dialog/card/transition slots, §2.12).
10. **Focus zoom helpers.** AP `card_focus_scale` / `attach_focus_zoom`
    with frozen-control guards (`components/focus_styles.py:76-110`)
    extend KTV's `card_button_style` without breaking its rule. **AP wins.**
11. **EmptyState styling.** Same contract; AP adds ON_SURFACE colors +
    brand PRIMARY button (`components/empty_state.py:68` vs KTV `:54`).
    **Equivalent, AP slightly nicer.**
12. **Back-key coverage.** AP `_BACK_KEYS` (5 keys incl. `"Go Back"` /
    `"Browser Back"`, `app_shell.py:394`) is a superset of KTV's 3
    (`hooks/use_focus_scope.py:15`). KTV documents dropping `"Go Back"`
    as non-standard — the two disagree, but AP's superset is harmless.
    **Equivalent.**
13. **Watchdog / error card / tap-to-close / seek-swallow / deferred seek /
    speed-reapply / quality-audio pinning / proxy memoization.** Ported
    faithfully; AP `components/player/immersive_player.py:1022` matches
    KTV behavior point for point (verified pairs: watchdog 20 s `:712`
    vs KTV `:27`; swallow `:953-955` vs `:1190-1200`; poll 4 s `:767`
    vs `:814`; reapply `:625-633` vs `:1035-1041`; labels+visibility
    `:635-661` vs `:1072-1116`; TTL 30 s in both proxies). **Equivalent —
    no action.**
14. **Auto-advance on complete.** AP's duration-known + within-5-s guards
    (`immersive_player.py:962-981`) correctly replace KTV's reconnect
    budget for VOD. **AP correct as-is.**
15. **Activity terminal.** Both have it (KTV `settings_screen.py:170+`;
    AP `screens/settings_screen.py:95-190` + telemetry snapshot). **Equivalent.**
16. **Connectivity detection.** Both use `ft.Connectivity` + `is_online`
    (KTV `main.py:282-295`; AP `main.py:204-234`). KTV's liveliness-clear
    on offline is N/A to AP; AP's `connectivity_version` bump is the
    idiomatic equivalent. **Equivalent.**
