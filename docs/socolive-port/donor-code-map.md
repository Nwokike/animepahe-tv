# Donor Code Map: animepahe-tv → socolive-tv

READ-ONLY research artifact. Maps exactly WHAT to copy from this repo
(`animepahe-tv`, the donor) into `socolive-tv` (the target) when converting it
to the donor's multi-backend architecture, and what must adapt for a
LIVE-SPORTS app: matches replace episodes, live HLS replaces VOD m3u8, and
there is no downloads engine.

Ground truth: every path below was read in full on 2026-11-04. Target state
verified against `/home/maikel/Desktop/kiri-apps/socolive-tv/src` (it already
carries a *slim* port of this architecture — router 263 vs 543 lines, base.py
78 vs 247, live_player.py 173 vs the 1,508-line player stack, hls_proxy 205 vs
919, store 190 vs 542 — so most of this port is an UPGRADE of existing files to
the donor's battle-tested versions, not greenfield).

Line references are donor paths unless prefixed `socolive:`.

---

## 0. The downloads question, answered first

**Would downloads even apply? No.** Verdict: SKIP the entire downloads engine.

- The donor engine (`src/services/downloads.py`, ~large; plus
  `screens/downloads_screen.py`, the store `downloads` section, the
  `downloads` notification channel, and the six `download_*` controller
  methods) walks a *finite* VOD playlist segment-by-segment until
  `has_more` ends, then writes a local `index.m3u8`. A live playlist never
  ends: the engine would loop forever and only ever capture the rolling
  window; and when the match ends, the signed/minted m3u8 URL dies — there
  is nothing left to fetch afterwards.
- Live-sport "download" means *recording* (a continuous DVR capture that
  must run while the match is live). That is NEW code, not a port; nothing
  in the donor approximates it. Do not port unless recording is explicitly
  wanted.
- The owner watches live football — there is no "watch later" library to
  download from. The donor's own copy string ("Saved in the format the
  source serves") has no live analogue.
- What DOES carry over from the downloads story: (a) the external-player
  handoff (`external_player` store flag, `ktv://` deep link — socolive
  already has it), (b) `play_downloaded`'s slot in the shell's error-view
  retry must be replaced (see §2.4), (c) CF-on-file-host callbacks die with
  the engine.

---

## 1. Backend machinery

### 1.1 `src/services/router.py` (543 lines) — COPY-ADAPT

The failover core. Imports: `anyio`, `core.config` (4 breaker constants +
`STARTUP_PROBE_BUDGET`), `services.providers.base` (`CloudflareBlocked`,
`Provider`, `owner_of`).

Copy verbatim:
- `_Breaker` (3 failures → OPEN, 30s cooldown, one half-open trial, failed
  trial doubles cooldown, cap 5min) and `ProviderHealth`.
- `_attempt`'s `CloudflareBlocked` passthrough: the wall is a SIGNAL, never
  a breaker failure. **socolive's current router lacks this** — a walled
  sports provider today reads as "all circuits open".
- The first-then-race shape of `_run` (owner answers alone; the rest race
  only on failure/empty) and `session_owned` vs owner-prefixed ordering.
- `probe_all` (parallel, `move_on_after` budget, deadline does not
  fabricate failures), `_record_health`, `set_pin`, `last_winner`.

Adapt for live sports:
- Public ops: keep `latest_releases` (today's match window) and `search`
  (both `session_owned` — the app IS the chosen backend). `sources` takes
  ONE session arg in socolive (a match has no episode); drop the donor's
  two-arg form.
- `episodes_for_title_any` / `sources_for_title_any` become the
  match-domain equivalent ("Try another source" for playback: every OTHER
  provider, title/team in → sources out). Keep the `force` flag semantics —
  the user asking to watch overrides a tripped breaker. This cross-provider
  path is the single biggest functional gain of the port; socolive's router
  has no equivalent.
- `discover_provider` / `discover_filters` / `browse`: SKIP unless a sports
  provider ships a filter vocabulary. If kept, delete the hardcoded
  `kayoanime` fallback (lines 421–429) — that name is donor-specific; fall
  back to the first provider with a `browse` attribute instead.
- `_is_empty`'s tuple inspection stays as-is.

### 1.2 `src/services/providers/base.py` (247 lines) — COPY-ADAPT

Imports: `core.state` (dataclasses). socolive already has the
namespace helpers (`make_session`/`split_session`/`owner_of`) verbatim with
`DEFAULT_OWNER = "socolive"`.

Copy verbatim: `CloudflareBlocked` (with its docstring contract — raised
deliberately, never counted as failure; the router AND the controller's CF
gate depend on it), `close_client` (the primp 2.0.1 `__aexit__`-only release
quirk — socolive's hls_proxy will hit this), `page_slice` (rename
`EPISODES_PER_PAGE` → matches per page), `releases_from_anime` (renamed to
shape Match rows into release-grid rows), `all_episodes` → `all_matches`
(needed only if a follow/reminder checker is ported, see §3.4).

Adapt: `PROVIDER_ORDER` — donor's `(anikato, kayoanime, animepahe,
animeout)` becomes the sports order (with the same cost-rule commentary:
no-verification sources first, walled sources last; there is NO "automatic"
option in any UI, ever). `Provider` Protocol: keep socolive's one-arg
`sources(match_session)`; add the title-keyed pair
(`sources_for_match_any`) if the "try another source" path is ported.
`BrowserProvider` Protocol: only if discover is kept.

### 1.3 `src/core/config.py` — COPY-ADAPT (one block)

Copy the breaker block verbatim: `BREAKER_FAIL_THRESHOLD = 3`,
`BREAKER_OPEN_SECONDS = 30.0`, `BREAKER_OPEN_MAX_SECONDS = 300.0`,
`STARTUP_PROBE_BUDGET = 12.0`, plus the provider cache TTLs. Skip:
`KTV_PLAY_STORE_URL` / `KTV_DEEP_LINK_SCHEME` (socolive keeps its own),
`ANIMEOUT_API`/`KAYOANIME_API`/`DRIVE_*` (anime endpoints), and — for a
VOD-free app — `CACHE_TTL_EPISODES` semantics change to match listings
(shorter; a match list is time-sensitive).

### 1.4 Backend picker UI — `src/app_shell.py:767–879` (`_build_backend_picker`) — COPY-ADAPT

The picker dialog: every provider in `PROVIDER_ORDER` order, one health dot
per row (ERROR when breaker `open`, WARNING `half_open`, SUCCESS otherwise),
latency + first 40 chars of `last_error`, the hints line, "serving now" /
"tap to pin", the footer caption ("Tried in this order at launch…").

Dependencies: `services.providers.base.PROVIDER_ORDER`,
`controller.sources_status()`, `AppColors` (ERROR/WARNING/SUCCESS),
`state.current_source_name`, `controller.pin_backend`, and the shell's
**dialog portal** — the `portal_owner`/`active_dialog` elif chain +
`use_dialog` + `_close_dialog` flag-clearing (app_shell.py:187–252). The
portal machinery is house pattern and copies verbatim; it is what lets
Back/Cancel actually dismiss a flag-driven dialog.

Adapt: only the `hints` dict is anime copy — write sports hints ("no
verification", "many leagues", "PT-BR commentary · needs verification"…).
Everything else is provider-agnostic.

### 1.5 Backend badge — `src/components/app_header.py` (`backend_title` :117, `_backend_badge` :223) — COPY-ADAPT

`"<Backend> TV"` title pill + the second badge readout (hidden below the
600dp `BREAKPOINT_TABLET`, tooltip "Served by X — tap to switch", zero-size
placeholder instead of a suspended row on phones). Adapt: name strings;
keep the hide-below-tablet rule and the "no 'auto' label — the badge names
the provider that is serving" rule. socolive's
`components/backend_badge.py` can be replaced by this pattern once the
controller exposes `current_source_name` + `open_backend_picker`.

### 1.6 Controller backend management — `src/main.py` — COPY-ADAPT

- `sources_status()` (:1689–1699) — COPY-VERBATIM: `router.health()` →
  plain dicts, exactly the shape the picker's `_row` reads.
- `test_all_sources()` (:1389–1425) — COPY-ADAPT: probe + one REAL search
  per provider, nothing faked. Change the probe query ("one piece") to a
  sports term that every provider can answer. socolive's existing version
  (:347) probes only — it lacks the search check and never restores
  `_record_health` on success.
- `resolve_startup()` (:1788–1828) + `_ordered_backend()` (:1830) —
  COPY-ADAPT: stored pin → else the fixed order race, single-flight lock,
  splash stays up through the first home fetch, `_gate_solver(pin ==
  "<walled provider>")`. Live note: the paint-first home snapshot hydrate
  (:1822) matters MORE for sports (a stale match list still names today's
  games).
- `set_backend_pin` / `pin_backend` / `open_backend_picker` (:1851–1890) —
  COPY-ADAPT: switching away from the walled provider clears
  `state.cf_blocked`, resets Discover, persists, re-runs `resolve_startup`
  through the splash.
- Startup splash `_startup_splash` (app_shell.py:90–113) +
  `state.startup_ready` / `startup_stage` + the "past all hooks" gate —
  COPY-VERBATIM.
- Router registration block (main.py:231–266): the by-name dict +
  `PROVIDER_ORDER`-ordered registration + `set_pin(await store.get_backend())`
  — copy the shape, swap provider names.

---

## 2. The player stack

### 2.0 What is live-specific vs VOD-specific — the one-line map

| Donor concern | Verdict for live sports |
|---|---|
| Watchdog (20s backstop → retry/back UI) | KEEP — live-critical |
| `_show_progress` / `_show_final_error` / retry+back overlay | KEEP — live-critical |
| `reconnect_stream` + `STREAM_RECONNECT_MAX = 3` (handlers.py) | KEEP — this IS the live path |
| `handle_stream_complete` reconnect branch | KEEP; the VOD auto-advance branch stays harmlessly dead (a live stream reports duration 0) |
| Quality/audio variant pinning via HLS proxy | KEEP — live HLS masters carry variants too |
| Interstitial inside `start_playback` | KEEP (placement §4) |
| Close funnel (`_is_closing`/`_position_saved`), teardown w/ fullscreen-exit-first | KEEP verbatim |
| Toast chip inside the controls (fullscreen visibility) | KEEP verbatim |
| mpv props (`network-timeout: 10`, cache-secs, framedrop) | KEEP; maybe raise `cache-secs` for live |
| Resume + periodic checkpoints + deferred seek | SKIP — a live stream has no duration/position; the `dur_sec > 0` guards already no-op, but strip the machinery for clarity |
| Skip intro/outro chip | SKIP — VOD-only |
| Auto-advance next/prev episode buttons | SKIP or repurpose ("next match" is a shell concern; a fan closes and picks) |
| Subtitle tracks (source + local .srt picker) | Mostly SKIP; keep only if any sports provider serves tracks |
| Playback-speed cycling | Optional keep; note handlers.cycle_speed persists via save_position — decouple from resume |
| Live-edge seek / "Go live" / DVR bar | NOT IN DONOR — new code required for socolive (see §2.5) |

### 2.1 `src/components/player/immersive_player.py` (1,508 lines) — COPY-ADAPT

Imports: `flet`, `flet_video`, `core.theme.AppColors`; lazy imports of
`services.ads`, `core.notify`, `core.snapshots`, `core.shared_services`,
`components.player.handlers/controls`.

Keep verbatim (the skeleton is KTV's, landed in commit `d0d0bfc`): the
Stack-of-[black, video, overlay] shape, `_run_async`/`_keep` orphan-task
tracking, `did_mount` → `start_playback`, `_event_seconds` (flet.Duration
coercion — the bug that silently zeroed resume), `_check_and_trigger_seek`
(no-op on live), `_swap_media` (variant/audio swap restarting playback),
`_probe_stream_options` with its 3-try reveal loop, watchdog start/cancel,
`_show_final_error`, `teardown()` (exit native fullscreen BEFORE popping —
the `FlutterEngineRemoveView kInvalidArguments` fix, commit `34b54e7`),
`handle_key`.

Remove for live: `_read_resume_position`, `_maybe_save_position_periodically`,
`_start_checkpoints`/`_cancel_checkpoints`, `_persist_position`,
`save_position_now`, `_pending_seek`/`_deferred_seek` machinery, skip-window
helpers (`_window`/`_active_window`/`_update_skip_chip`/`_on_skip_chip`).
The shell's close funnel calls `save_position_now()` — the funnel adapts to
a save-less close (§2.4).

### 2.2 `src/components/player/controls.py` (285 lines) — COPY-ADAPT

Keep verbatim: `build_player_controls` structure, every button WHITE
(owner's call — ash-grey reads as disabled), the toast chip living INSIDE
the video controls (media_kit's fullscreen route is above the whole Flet
tree; only this surface survives — do not move it to a Stack overlay),
quality/audio chips revealed by `_probe_stream_options`, `AdaptiveVideoControls`
dual-branch (material + material_desktop) with `seek_bar_position_color=
AppColors.PRIMARY`.

Adapt: remove `prev_btn`/`next_btn` and `skip_chip`; replace the
`VideoPositionIndicator` slot with a LIVE pill (+ optionally elapsed-since-
kickoff); consider `display_seek_bar=False` on material, or keep it for DVR
windows. The shared-chip-instance trick (one branch renders per platform)
is safe to keep.

### 2.3 `src/components/player/handlers.py` (421 lines) — COPY-ADAPT

Keep verbatim: `STREAM_RECONNECT_MAX = 3`, `reconnect_stream` (the live
reconnection — playlist re-attach + watchdog restart), `open_player_settings`
(Stream/Quality + Video Fit sections; drop the audio/subtitle dropdowns if
unused — the refresh loop already hides them by count).

Adapt/skip: `pick_subtitles` (skip unless tracks exist), `cycle_speed`
(keep the UI cycle; move the rate persistence to a settings key, not a
resume record), `handle_stream_complete` (keep the reconnect branch; the
first VOD-ending branch stays dead on live since `dur == 0`).

### 2.4 The `/play` view mount — `src/app_shell.py:373–716` — COPY-ADAPT

This is the KTV-exact mount and the reason Android system Back reaches
Python (`on_view_pop`) instead of exiting the app. Copy as a unit:
`_active_player`/`_active_key` module state, `_use_player_view` (ft.View
route="/play", padding=0, key comparison = retry/switch remount), `_pop_play_view`,
`_close_player` → `_begin_player_close` (single close-guard funnel: player
Back + FocusScope + system back + shell all converge), `_close_player_with_save`
(→ drop the `save_position_now` await for live; teardown + pop remain),
`_release_player_page_state` (wakelock off + `focus_manager.set_key_consumer(None)`),
`_in_overlay` (identity membership — controls are dataclasses, `in` compares
by value), `_use_resolve_overlay` ("Resolving stream…" stage + Cancel —
COPY-VERBATIM; minting sports embeds takes seconds, the tap must be
acknowledged), `_build_player_error` (black stage + Retry/Go Back).

Adapt: (a) the player spec keys — `episode_session` → `match_session`/
`room_id`; keep `resource`, `source_url`, `source_referer`, `source_headers`
(sports CDNs need Referer/Origin per source — same mechanism), `variants`,
`variant_index`, `proxied`; (b) the error view's Retry currently calls
`controller.play_downloaded(session)` — replace with re-resolve of the
match's sources; (c) the mount instantiates `ImmersivePlayer` with
`resume_key`/`store` — drop for live (or keep store for presentation
settings only: `subtitle_size`, `video_fit` via `get_setting`).

Also copy with it: `src/components/guarded_controls.py` (COPY-VERBATIM,
flet-only — it exists precisely to close the "tap on an already-replaced
player stage" RuntimeError crash class the imperative mount creates) and
`src/hooks/use_focus_scope.py` (93 lines, COPY-VERBATIM: plain FUNCTION,
not a @ft.component; the expanding-Container-is-load-bearing note; the
`run_task`-takes-a-function trap). Player key routing also needs
`src/core/focus_manager.py` (COPY-VERBATIM — chained `page.on_keyboard_event`,
`set_key_consumer` for the window-level arrow-key stream that Flutter's
focus traversal otherwise eats).

### 2.5 Genuinely new live code (not in the donor)

Flag these as NEW, so nobody hunts for a donor source: a live-edge policy
("Go live" affordance or seek-bar clamp), the LIVE pill/minute display
sourced from the match state, and source cycling WITHIN the player
(socolive's current live_player has one-tap source cycling — decide whether
that folds into the donor's settings dialog or stays a dedicated button).
Donor equivalents exist only for the reconnect/retry part.

---

## 3. Core plumbing

| File | Verdict | Notes / dependencies |
|---|---|---|
| `src/core/tasks.py` (62) | COPY-VERBATIM | `spawn` (never bare create_task), `session_alive` (page.session probe), `ui_set`. Deps: asyncio, logging, flet. |
| `src/core/tokens.py` (116) | COPY-VERBATIM | The generic scale; `GRID_COL`/`GRID_SPACING` is the one grid contract. No app-specific values. |
| `src/core/theme.py` (232) | COPY-ADAPT | Machinery verbatim: `THEME_MODES`/cycle fns, `is_dark_mode` (dark-when-unknown), `_DARK/_LIGHT_SURFACE_ROLES` pinning, `_PAGE_TRANSITIONS`, glass helpers. Adapt: `AppColors.PRIMARY` rose `#F43F5E` is animepahe's brand — keep the token names, re-point values if socolive rebrands. Picker/badge rows read `PRIMARY/SUCCESS/WARNING/ERROR`. |
| `src/core/notify.py` (79) | COPY-VERBATIM | Snack via `page.show_dialog` (no `page.open` in flet 1.0.4), the same-snack-on-stack RuntimeError skip, dual dispatch to the fullscreen toast registry. Deps: flet only. |
| `src/core/notify_service.py` (201) | COPY-ADAPT | Keep: service construction w/ `on_tap` once, `_stable_id`, channels setup + one permission ask, `update_available`. Rename channel `new_episodes` → kickoff/match reminders (reuse the follow-progress store pattern). SKIP: `download_progress`/`download_done`/`download_failed` (no downloads). Deps: flet-notifications (graceful ImportError), `core.constants.APP_NAME`. |
| `src/core/logger_handler.py` (87) | COPY-VERBATIM | Ring buffer for the settings terminal + console handler + root-level INFO fix + `get_telemetry_snapshot`. |
| `src/core/storage.py` (116) | COPY-VERBATIM | `app_data_dir`/`app_cache_dir` — the storage contract. |
| `src/core/shared_services.py` (103) | COPY-VERBATIM | One launcher/clipboard/file-picker for the whole app. |
| `src/core/focus_manager.py` (179) | COPY-VERBATIM | Global Back delivery + `FieldFocusTracker` + `set_key_consumer` (player keys). |
| `src/state/app_state.py` (14) | COPY-ADAPT | One `@ft.observable` singleton via `ft.create_context` — the pattern is verbatim; the field list renames (episodes→matches; keep `startup_ready/startup_stage`, `player_open/player_spec/player_error`, `is_resolving/resolve_stage/busy_version`, `current_source_name`, `backend_picker_open`, `cf_blocked`, version counters). SKIP: downloads/`download_choice_open`/quality-dialog trio (socolive's room picker replaces the quality dialog — reuse the portal machinery instead), follows unless reminders are ported. |
| `src/state/controller_ctx.py` (86) | COPY-ADAPT | `ControllerMethods` dataclass with no-op defaults + "AppShell MUTATES the same instance" identity rule — verbatim. Adapt method set: `open_anime`→`open_match`, `play_episode(anime,episode)`→`play_match(match)`, drop `download_*`/`play_downloaded`/`earn_kwik_qualities`/`choose_download_quality`; keep `open_backend_picker`/`pin_backend`/`test_all_sources`/`sources_status`/`set_backend_pin`/`cancel_resolve`. |
| `src/services/store.py` (542) | COPY-ADAPT | Sections inventory: `search_history` (COPY), `continue_watching` (socolive's `recent_matches` already covers it), `positions` (SKIP — no resume), `clearance` **host-keyed** (COPY — the returning-user-skips-the-webview trick; needed for any walled sports host), `theme_mode` (COPY), `downloads` (SKIP), `follows` (COPY only as the kickoff-reminder base: `get_follow_progress`/`set_follow_progress`), `external_player` (COPY), `backend` (COPY — and adopt the donor's discipline: empty = fixed order, never write "auto"; socolive still persists "auto"), `artwork_defaults` (COPY-ADAPT if poster-shape learning is wanted), `settings` k/v + `get_setting` SYNC read (COPY-VERBATIM — the player constructor reads presentation settings before any coroutine runs). Also the atomic `_atomic_write_json` + singleton `get_store()`. |
| `src/services/hls_proxy.py` (919) | COPY-ADAPT | **Needed for live, yes.** Referer/Origin-gated sports CDNs are the same problem as kwik's CDNs (socolive's own hls_proxy docstring says so). Copy verbatim: the primp-impersonation client (`httpx` 403s where primp 200s), hand-rolled HTTP/1.1 with the hardening bounds, header injection (`url`/`referer`/`headers` b64 query params + CRLF/header-key validation), playlist/segment/key routes, Range + conditional-validator passthrough, **variant pinning + `parse_hls_variants`/`parse_hls_audio_tracks`** (live masters carry variants — quality switching works identically), the `/image` route (team logos/competition art via CORS or guarded hosts) with negative caching, `set_display_context`/`image_url` (drop the animepahe `PROBE_REFERERS`/`guarded_host` deps from `core.artwork` — inline a sports guarded-host list). Media-playlist rewriting is already live-safe (segments have no duration dependency). Keep socolive's existing `goat_ts` WEBP→TS unwrap as a target-side extra route. |
| `src/services/cache.py` (147) + home snapshot (`_save_home_snapshot`/`_hydrate_home_snapshot`, main.py:498–546, `HOME_FEED_SNAPSHOT_TTL`) | COPY-ADAPT | Paint-first launch. Optional but high-value for sports (today's card list). |
| `src/core/snapshots.py` | SKIP | Screenshot saving — keep only if the player's snapshot button is kept (fans DO screenshot goals; cheap to keep). |

### 3.1 Cloudflare story — `services/cf_judge.py` (193) + `services/webview_solver.py` (462) + `services/desktop_cf_solver.py` — COPY-ADAPT

- `cf_judge.py`: COPY-VERBATIM except the per-site markers —
  `TARGET_COOKIE_MARKERS` lists animepahe/animeout session cookies; replace
  with the sports hosts' own session cookies (or leave only the generic
  rules + host rule active). The seven-rule ordering (hard block → own
  cookies → challenge-in-URL → empty title → target host → plain nginx
  page) is the shared judge for BOTH transports and must stay one function.
- `webview_solver.py`: already de-hardcoded (mobile flet_webview + pyjnius
  CookieManager for HttpOnly cf_clearance; TV D-pad scroll; the
  FletUnsupportedPlatformException desktop fallback; no DOM mutation — the
  Turnstile reload-loop fix). COPY-ADAPT nearly verbatim.
- `desktop_cf_solver.py` subprocess: COPY-VERBATIM (site-agnostic).
- `services/ddos_solver.py`: DONOR-SPECIFIC (`BASE = "https://animepahe.com"`,
  the scraper's session). COPY the *shape* — "does this body look like a
  challenge" markers + a solver that stores host-keyed clearance — and
  instantiate it per walled sports provider.
- The gate (main.py:831–880: `_gate_solver`, `_user_action` ref-counted
  context manager, `_may_solve`): COPY-ADAPT — "a verification window opens
  only for a deliberate user action on the walled provider's own content;
  background work never flips the gate" carries over verbatim;
  `_may_solve`'s `owner_of(session) != default_owner` becomes the walled
  provider's name.

---

## 4. Ads (Yandex)

| File | Verdict | Notes |
|---|---|---|
| `src/services/ads.py` (231) | COPY-ADAPT | Machinery verbatim: graceful ImportError, `is_ads_supported` (mobile OR Android TV), preload-one-interstitial + re-preload after dismiss, 30s `INTERSTITIAL_MIN_INTERVAL_SEC` guard, app-open on cold start w/ 4h reconnect cadence, consent/location/age setters. **Adapt: unit IDs are the owner's animepahe Yandex app (`R-M-20208795-*`) — socolive needs its own Yandex partner app IDs** (env-override plumbing already exists). |
| `src/components/banner_ad.py` (139) | COPY-VERBATIM | Glass container, 320x50 sticky / inline sizing, ONE bounded reload after a failed fill (dead unit must not spin forever), 0x0 on desktop/web. Unit id rides `AD_UNITS` from ads.py. |
| `src/components/ad_breaks.py` (37) | COPY-VERBATIM | `grid_with_ads`: chunks of 24 cards + inline banner between chunks. Applies unchanged to match-card grids. |

**Placements to replicate** (grep-verified): a banner row on every screen —
home (`:413` inline grid breaks + `:428`), discover (`:499–506`),
search (`:407–412`), the detail screen (`:36` + `:574` episode grid),
settings (`:570–583`), downloads (`:447`); interstitial INSIDE
`start_playback` right before the playlist attaches (never at selection
time, owner-verified KTV placement); app-open at cold start via
`on_initialized`. Live-sport adjustments: the 30s guard already prevents
ad-on-every-reconnect (interstitial fires only in `start_playback`, never
in `reconnect_stream`); one match open ≈ one episode open, so the cadence
carries over as-is; never mid-play (the donor never does).

---

## 5. SKIP list (animepahe-specific)

- `services/kwik_resolver.py`, `services/kwik_files.py`,
  `services/animeout_solver.py` — file-host resolvers.
- `services/providers/*` — anikato, kayoanime, animepahe_provider,
  animeout (socolive has its own ten providers).
- `services/downloads.py`, `screens/downloads_screen.py`, the Downloads
  tab in `app_shell._TABS`, `download_*` controller methods, the
  `downloads` store section and notify channel (see §0).
- `services/aes.py` (kwik payload decryption), `core/html_extract.py`
  (animepahe page scraping), `core/artwork.py` (keep only the guarded-host
  idea if hls_proxy's /image route is ported).
- Resume/checkpoints/skip-intro in the player (§2.0).
- `screens/*` bodies — socolive has its own views; the portable pieces are
  the ad integrations, `focus_styles.py`, and the empty/offline states
  (`components/empty_state.py`, `offline_state.py` — worth a look, not
  mapped here).
- `cloudflare-worker.js`, `tools/*` (donor dev tooling), the `animepahe`
  keystore.

---

## 6. Dependency chains (what to land together)

```
core/tasks.py ────────────────► everything that spawns
core/tokens.py ──► core/theme.py ──► every component
core/logger_handler.py (import side-effect: root logging config) ──► main entry first
core/state.py dataclasses ──► providers/base.py ──► services/router.py ──► main.py controller
core/config.py (breaker block) ────────────────► services/router.py
state/app_state.py + state/controller_ctx.py ──► app_shell.py + screens
services/store.py ◄── core/storage.py, core/artwork(≈guarded hosts)
services/hls_proxy.py ◄── primp; optional core/artwork refs (inline them)
services/cf_judge.py ──► services/webview_solver.py ──► services/desktop_cf_solver.py
components/guarded_controls.py ──► app_shell (portal buttons) + player
hooks/use_focus_scope.py + core/focus_manager.py ──► the /play mount
components/player/controls.py ──► handlers.py ──► immersive_player.py ──► app_shell._use_player_view
services/ads.py ──► components/banner_ad.py ──► components/ad_breaks.py ──► screens
services/ads.py ──► immersive_player.start_playback (interstitial)
core/notify.py ◄── immersive_player (fullscreen toast registry), all snack callers
core/notify_service.py ◄── flet-notifications, core/constants
```

---

## 7. Suggested port order

1. **Core plumbing** (all verbatim or near): `tasks`, `tokens`,
   `logger_handler`, `storage`, `shared_services`, `focus_manager`,
   `guarded_controls`, `notify`, `theme` (re-point palette),
   `core/constants`.
2. **State layer**: `core/state.py` (keep Match/Room/Source; add `headers`
   per source), `state/app_state.py`, `state/controller_ctx.py`.
3. **Config**: breaker block + provider order + cache TTLs into
   socolive's `core/config.py`.
4. **Backend machinery**: `providers/base.py` (add `CloudflareBlocked`,
   `PROVIDER_ORDER`, helpers) → `router.py` (breaker/health/failover +
   first-then-race + CF passthrough) → controller: `sources_status`,
   `test_all_sources`, `resolve_startup`/`_ordered_backend`,
   `set_backend_pin`/`pin_backend`/`open_backend_picker`, splash gate.
5. **Store**: replace with the donor's `store.py` minus
   positions/downloads, plus host-keyed clearance and settings k/v.
6. **Backend UI**: dialog portal in `app_shell` → `_build_backend_picker`
   (sports hints) → header badge + title pill → Settings backend row +
   test panel.
7. **HLS proxy**: donor's 919-line proxy (headers, variant pinning, /image)
   + keep socolive's WEBP→TS unwrap route.
8. **Player stack**: `controls.py` (live chrome) → `handlers.py`
   (reconnect-keep) → `immersive_player.py` (resume/skip stripped) →
   `use_focus_scope` → the `/play` view mount + resolve overlay + error
   view (retry = re-resolve). Add the NEW live-edge/LIVE-pill bits here.
9. **Ads**: `ads.py` with socolive's own unit IDs → `banner_ad` →
   `ad_breaks` → interstitial into the player start; wire app-open in init.
10. **CF story** (only for walled providers): `cf_judge` →
    `webview_solver` → `desktop_cf_solver` → per-provider ddos-solver
    shape → the gate in the controller.
11. **Notify service**: channels renamed to kickoff reminders, update
    channel verbatim.
12. **Delete**: socolive's slim `router`/`base`/`hls_proxy`/`store`
    superseded in steps 4–7; the downloads slot stays empty (§0).

Each step leaves the app running: 1–3 are inert, 4 changes data behavior
behind the same call sites, 6 is UI-only, 8 swaps the player last after the
proxy it depends on.

---

## 8. Summary (8 bullets)

1. **socolive already has the skeleton; the port is an upgrade.** Its
   263-line router, 78-line base, 205-line proxy, 190-line store and
   173-line player are slim first drafts of the donor's hardened versions
   (543 / 247 / 919 / 542 / 1,508+285+421) — copy-over-replace, not
   merge.
2. **The router upgrade's two must-haves**: `_attempt`'s
   `CloudflareBlocked` passthrough (a wall is a signal, never a breaker
   failure) and the first-then-race failover in `_run` with
   `session_owned` semantics — plus the title-keyed "try another source"
   pair, which socolive lacks entirely.
3. **The player port keeps the KTV skeleton, strips the VOD organs:**
   watchdog, reconnect (`STREAM_RECONNECT_MAX=3`), retry/back overlay,
   variant pinning, toast chip and the fullscreen-first teardown copy
   verbatim; resume, checkpoints, skip-intro/outro, next/prev-episode and
   subtitle-track machinery go. Live-edge seek and a LIVE pill are NEW
   code the donor cannot supply.
4. **The `/play` ft.View mount is the linchpin of TV correctness** — it is
   what routes Android system Back into Python; port it as a unit with
   `focus_scope` (plain function), `FocusManager.set_key_consumer`,
   `guarded_controls`, and the single close funnel. The error-view retry
   must be re-pointed from `play_downloaded` to re-resolve.
5. **Downloads: SKIP entirely.** The donor engine walks finite VOD
   playlists; a live playlist never ends and its URL dies at full time.
   Recording would be new code. The owner watches live football — the
   feature has no user story, and the Downloads tab/channel/controller
   methods all drop out.
6. **The CF story ports almost whole**: `cf_judge` is pure (only per-site
   cookie markers change), `webview_solver` was already de-hardcoded, the
   desktop subprocess is site-agnostic; only `ddos_solver` needs a
   per-provider rewrite, and the gate discipline ("background work never
   opens a verification window") carries over verbatim.
7. **HLS proxy: yes, needed for live** — Referer/Origin-gated sports CDNs
   are the same problem the donor solved for kwik; headers injection,
   variant pinning, the hardened local HTTP/1.1 socket and the /image
   artwork route all apply; add socolive's WEBP→TS unwrap as an extra
   route and inline the guarded-host list.
8. **Ads copy verbatim except the unit IDs** (`R-M-20208795-*` are
   animepahe's Yandex app — socolive needs its own): banner-on-every-
   screen, 24-card grid breaks, interstitial inside `start_playback`
   (its 30s guard naturally prevents ad-on-reconnect), app-open on cold
   start.
