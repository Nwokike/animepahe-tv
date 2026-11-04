# Socolive TV — App Architecture Map (port reference)

Read-only survey of every file in `socolive-tv/src` (38 files, 6,111 lines), written as the
reference map for porting work between `socolive-tv` and `animepahe-tv`.
Root: `/home/maikel/Desktop/kiri-apps/socolive-tv`. All paths below are relative to that root.
Nothing in either repo was modified.

Tech stack (`pyproject.toml`): Python >= 3.13, `flet==0.85.3`, `flet-video==0.85.3`, `httpx>=0.28.1`,
`primp>=2.0.1`, `anyio>=4.13.0`. Note: `flet_webview` is imported lazily by
`services/embed_mint.py:40` but is **not** a declared dependency (it arrives transitively /
platform-side; the minter degrades to `None` if the import fails).

---

## 1. Top-level shape

- **Entry**: `src/main.py:797-808` — `async def main(page)` → `AppController(page)` →
  `controller.init()` → wire `page.on_route_change` / `page.on_view_pop` →
  `await controller.route_change()`. Launched via `ft.run(main, assets_dir="assets")` (`main.py:808`).
- **There is no `page.render()`** anywhere in the repo. The app is a **Flet `View` stack app**:
  navigation = appending/popping `ft.View` objects onto `page.views` and keeping
  `page.route` in sync (e.g. `main.py:383-387`, `main.py:441-449`, `main.py:667-669`).
  Routes are cosmetic labels — every transition is a manual stack mutation; `route_change`
  only reacts to `/`, `/home` (rebuild Home) and `/settings` (`main.py:726-751`).
- **No tabs.** `app_shell.py` (`build_app_frame`, lines 42-91) wraps content in an adaptive
  nav (NavigationRail >= 600 dp or Android TV, NavigationBar below — `app_shell.py:15-25`),
  but it is used **only inside the Home view** with two destinations, `Live` and `Settings`
  (`views/home.py:799-812`). Selecting "Settings" does not switch a tab — it pushes the
  `/settings` View on the stack via `on_open_settings` (`views/home.py:811`). Both nav
  variants are mounted once and only `visible` flips on resize (`app_shell.py:66-77`) so
  D-pad focus is never lost (flet 0.85.0 cannot re-focus a rail programmatically).
- **Player mounting**: the player is **a View**, not an overlay/dialog.
  `main.py:_open_player` (644-669) appends `build_player_view(...)` (route `/player`) to
  `page.views`. Dialogs (`page.show_dialog`) are used for: KTV install prompt, update
  prompt, "Resolving…" spinner, stream picker, and the WebView mint window — never for the
  player itself.
- **Back handling** (three layers):
  1. `core/focus_manager.py:13-15` — global keyboard events (`Escape`, `Go Back`,
     `Browser Back`, `Backspace`) → `AppController._handle_global_back` (`main.py:414-433`):
     close any open dialog first, else pop the view stack (guarded by a `_popping`
     re-entrancy flag).
  2. `page.on_view_pop = controller.view_pop` (`main.py:753-764`) — same pop logic for
     Flet's own pop event.
  3. Per-screen explicit back buttons do their own stack pop
     (`views/match_detail.py:13-18`, `screens/settings_screen.py:150-155`), and the player's
     close button calls `AppController._close_player` (`main.py:671-679`) which pops only if
     the top view is `/player` and resets all `_play_*` playback state.

## 2. Startup order (annotated)

`AppController.init` (`main.py:219-278`), in order:

1. Page chrome: title, zero padding/spacing, `on_error` → error snackbar (`main.py:220-224`).
2. Fonts/theme: Outfit via `assets/outfit.css`, light+dark `AppTheme`, `ThemeMode.SYSTEM`
   (`main.py:226-231`); then the persisted 3-way theme is restored from the store
   (`main.py:234-235`).
3. **Provider bench** (`main.py:246-259`) — 10 providers in editorial order:
   `DamiTV, StreamedPK, CdnLiveTV, CamelTV, PPV, LiveLeagues, Dlive, TimStreams, Ball808,
   Socolive`. The order is "config, not code" — ranked by verified completeness, with
   socolive (the app's namesake, Vietnamese locale) demoted to the reliability backstop.
4. **Pin restore**: `router.set_pin(await get_store().get_backend())` (`main.py:260`) — the
   persisted pin ("auto" or a provider name) moves one provider to the front; failover
   stays enabled either way.
5. **Startup probe race** — `page.run_task(self._startup_select)` (`main.py:266`,
   implementation 287-300): sets `state.startup_stage = LBL_FINDING_SERVER`, awaits
   `router.probe_all()`, then clears the stage. Home never waits for this; it only shows
   the loader copy.
6. **Loopback HLS proxy**: `HLSProxy()` → `await self.hls_proxy.start()` (`main.py:270-271`)
   — binds a random port on 127.0.0.1, primp Chrome-148 client.
7. **Focus/back**: `FocusManager(self.page)` + `set_back_handler(self._handle_global_back)`
   (`main.py:273-274`).
8. **Update check**: `UpdateService` + `page._show_update_dialog` shim +
   `run_task(_check_for_updates_bg)` (`main.py:276-278`; background task sleeps 2 s,
   `main.py:389-396`; `update_service.py:15-34` polls
   `https://tv.kalerosemary7.workers.dev/config` for key `"socolive"`).

Then `main()` calls `route_change()` which builds the Home view; Home itself triggers the
first data load (`views/home.py:833-835`).

## 3. Architecture map (file:line)

### Entry / frame
| File | What it is |
|---|---|
| `src/main.py` (808 ln) | Entry + `AppController`: init, probe race, backend select, match load, play pipeline, player view mgmt, error/retry policy, settings wiring, route/pop handlers (§1, §2, §4) |
| `src/app_shell.py` (91 ln) | `build_app_frame`: adaptive rail/bar, `NAV_BREAKPOINT=600` (line 15), TV always rail (lines 18-25), visibility-flip on resize (70-77) |

### Views
| File | What it is |
|---|---|
| `src/views/home.py` (840 ln) | Home: header (badge+logo+refresh+version+theme, 428-529), date tabs -2..+2 days (258-299), live/upcoming/finished sections of responsive match cards (370-414), empty state with "Switch server" nudge (334-369), failover notice banner (785-797), promo slide carousel (AnimePahe TV / Nkiri TV / Support, 618-783, auto-rotates every 10 s via `asyncio.create_task` 749-774), adaptive frame (799-812), first-load trigger (833-835), `page_obj.update_home = update_home` callback stashed on the page (837) |
| `src/views/match_detail.py` (199 ln) | Detail: back btn (49-60), status pill/teams/score/league/kickoff (62-140), "Watch Match" button only when `status in ("live","upcoming")` (142-167), route `/match?id={match.match_id}` (189) |

### Components
| File | What it is |
|---|---|
| `src/components/player/live_player.py` (173 ln) | `build_player_view`: `fv.Video` (flet-video/mpv) + live chrome overlay (§7) |
| `src/components/backend_badge.py` (150 ln) | `build_backend_badge`: PopupMenuButton — "Automatic (recommended)" first, then one row per provider with health dot **+ word** (`ok/retrying/down/…`, lines 24-35), locale pill, latency-or-error meta (112-139). Docstring (1-16): answers "which backend am I on" and swaps in one tap — "the anime app never built it" |
| `src/components/player/__init__.py` | empty |

### Core
| File | What it is |
|---|---|
| `src/core/state.py` (128 ln) | Dataclasses `Competition` (6-16, unused in practice), `Match` (19-43, namespaced `session` "damitv:166123"), `Room` (44-55, SD/HD URL + language), `Source` (56-70, url/quality/label/referer/headers/**mint** ""\|"embed"), `AppState` (73-125) + module singleton `state` (128) |
| `src/core/config.py` (46 ln) | KTV deep link `ktv://play?url=` (13), Worker base URL (16), backend URLs (23-33), breaker budgets `3 fails / 30s / 300s cap / 1 half-open trial` (40-43), probe budgets 8 s / 4 s (45-46) |
| `src/core/constants.py` (47 ln) | UI copy incl. `LBL_FINDING_SERVER`, `LBL_BACKEND_FALLBACK` ("{pinned} is unreachable — showing {active} instead.", line 29), `STATUS_COLORS`/`STATUS_LABELS` (36-45) |
| `src/core/theme.py` (166 ln) | `AppColors` (YouTube dark tokens, red `#FF0000` owns selection/live), `AppTheme` dark/light surface-role pinning (78-141), 3-way `cycle_theme_mode` Dark→Light→System (144-150) + str converters |
| `src/core/focus_manager.py` (16 ln) | Keyboard back handler bridge |
| `src/core/__init__.py` | empty |

### Screens
| File | What it is |
|---|---|
| `src/screens/settings_screen.py` (195 ln) | `build_settings_view` (route `/settings`): PLAYBACK (external-KTV-player Switch, 32-41), CONTENT SOURCE (auto/pin Dropdown 57-69 + per-provider `ListTile` status rows 71-85 + "Test all sources" TextButton 87-90), APPEARANCE (3-way theme Dropdown 44-55), ABOUT (101-111). Pure function of injected state + callbacks; back is its own stack pop (150-155) |

### Services
| File | What it is |
|---|---|
| `src/services/router.py` (263 ln) | `ProviderRouter` — ordered failover + per-provider circuit breakers + probe race (§6) |
| `src/services/rotation.py` (195 ln) | `RotationResolver` — **domain** rotation for the Score808/808ball family only (§6.3) |
| `src/services/hls_proxy.py` (205 ln) | Loopback HLS proxy for minted embed.st streams (§6.4) |
| `src/services/goat_ts.py` (57 ln) | GOAT/RIFF-WEBP → MPEG-TS unwrap (pure logic; `goat_ts_meta` 11-43, `unwrap_segment` 46-57) |
| `src/services/embed_mint.py` (112 ln) | `mint_m3u8(page, embed_url, timeout=25)`: opens the embed URL in a `flet_webview.WebView` **inside a modal AlertDialog** (88-99), polls `performance.getEntriesByType('resource')` for the first `*.m3u8` (21-26, 48-66), pokes `<video>.play()` after ~8 s (27-33, 60-64), also captures console-log m3u8 URLs (68-79). Returns `None` on timeout — "a RESULT, not a crash" (36-38) |
| `src/services/player.py` (30 ln) | Pure playback policy: `RETRIES_PER_SOURCE=1`; `retry_same_source` (12-14); `next_source_index` cycles the resolved list skipping burned sources (17-27) |
| `src/services/store.py` (190 ln) | `JsonStore` singleton over `FLET_APP_STORAGE_DATA` (29-44), atomic temp-file writes (47-56). Sections: `search_history` (105-130), `recent_matches` (139-158), `theme_mode` (164-169), `external_player` (176-180), `backend` pin (186-190) |
| `src/services/update_service.py` (34 ln) | Worker `/config` poll, build-number compare, returns `{version, release_notes, apk_url, mandatory}` |
| `src/services/__init__.py` | empty |

### Providers (`src/services/providers/`)
| File | name | Catalog | sources() today | locale |
|---|---|---|---|---|
| `base.py` (78 ln) | — | `Provider` Protocol: `probe/latest_releases/search/sources/close` (47-69); `make_session/split_session/owner_of` (29-44); `DEFAULT_OWNER="socolive"` (26) | — | — |
| `damitv.py` (230 ln) | damitv | `/papi/api/streams` grouped JSON, football category, 120 s TTL (182-197) | `/papi/extract-url/{id}` mints signed HD+SD (`hlsUrl`/`sdUrl`, ~2 h expiry, never cached) + per-language `sdStreams[]` alternates (108-172); no WebView needed | en |
| `streamedpk.py` (250 ln) | streamedpk | Official API `/api/matches/football` + `/api/matches/live` for live ids (166-188); badges/posters via image-proxy tokens (240-251) | Server rows → `embed.st` player URLs with **`mint="embed"`** (147-156); tier labels from community name table (34-46) | en |
| `cdnlivetv.py` (263 ln) | cdnlivetv | Keyless JSON events+channels APIs (35-36, 207-225) | Pure-Python page decode: find base64-assembly line, decode vars in order (41-82); nested token expiry `<id>:<unix>:<domain>` cached until expiry-60s (55-62, 172-201); 4 retries on flaky player fetch (179-187) | en |
| `cameltv.py` (207 ln) | cameltv | `living_group_match` + `home_match` (5 group keys), sports.com logo CDN, real scores (116-207) | **`return []`** — capture-gated on `loadSign` token params (39-48, 104-106) | en |
| `ppv.py` (168 ln) | ppv | `/api.ppv.st/api/streams` football/soccer groups (124-142) | iframe (taifood-blog.asia) + `substreams[]` language alternates, **`mint="webview"`** (84-116) | en |
| `liveleagues.py` (186 ln) | liveleagues | HTML hub → tag pages → broadcast sub-pages; `event_start_ts` from `siteConfig` (29-43, 119-165), asyncio.Semaphore(8) | Sub-page URLs, **`mint="webview"`** (93-109) | en |
| `dlive.py` (170 ln) | dlive | HTML home, regex on `/stream/stream-{N}.php` anchors, title-div/img-alt labels (25-45, 125-157) | Stream page `dembed.st` iframe, **`mint="webview"`** (94-117) | en |
| `timstreams.py` (129 ln) | timstreams | **`latest_releases` returns `[]`** (119-122) — hub is one live channel; value is the decrypt ladder | XOR-deobfuscated embed JS yields the signed m3u8 directly — "the decrypt IS the mint", no WebView (97-117) | en |
| `ball808.py` (125 ln) | ball808 | **`latest_releases`/`search` return `[]`** — schedule capture-gated (70-77); only `match_page()` works (SSR title parse, 90-125) | **`return []`** — channel-fetch capture-gated (78-80) | en |
| `socolive.py` (361 ln) | socolive | JSONP day files `matches_{YYYYMMDD}.json` for a ±2-day window, anyio limiter 5, 120 s cache (181-258); status derived from kickoff ±2 h (224-234); plus unused-by-UI `all_live_rooms.json` live feed (266-281, parser 324-361) | Room anchors (cached at catalog time, line 239) → `room/{n}/detail.json` JSONP → signed `stream.m3u8`/`hdM3u8`, anyio limiter 4 (283-321); SD+HD per room, `referer=https://socolive.club/` (139-171). Datacenter egress gets CF 1009 (1-20) | vi |

## 4. Data flow: launch → match list → play

```
ft.run(main)                                                     main.py:808
 └─ AppController.init                                           main.py:219
     ├─ theme restore ← store.theme_mode                         main.py:234
     ├─ ProviderRouter(10 providers) + set_pin(store.backend)    main.py:246-260
     ├─ run_task(_startup_select)  — non-blocking probe race     main.py:266
     ├─ HLSProxy().start()  — 127.0.0.1 random port              main.py:270
     └─ FocusManager(back) + UpdateService(bg poll @2s)          main.py:273-278
 └─ route_change("/") → page.views.clear() + build_home_view     main.py:730-743
     └─ no state.matches → run_task(load_matches)                home.py:833-835

load_matches (lock per key, re-entrancy safe)                    main.py:451-500
 ├─ state.is_loading = True → update_home()  (spinner + startup_stage copy)
 ├─ router.latest_releases(1)                                    router.py:205-206 → _run
 │    ├─ order: [pin] + rest; breaker.allow() gates each         router.py:166-179
 │    ├─ first NON-EMPTY payload wins → last_winner              router.py:189-194
 │    └─ exception → breaker.record_failure + health, continue   router.py:183-188
 ├─ state.matches / state.leagues / active_backend / backend_health
 ├─ failover notice if pin && winner != pin → backend_notice     main.py:481-491
 └─ state.active_date = today; is_loading=False → update_home()

update_home (full re-render of the scroll column)                home.py:301-416
 ├─ date tabs (Today/Tomorrow/… ±2 d, per-date counts)           home.py:260-294
 └─ filtered_matches → LIVE / UPCOMING / FINISHED ResponsiveRow  home.py:371-414

card click → _open_match_detail                                  main.py:435-449
 └─ look up match in state.matches by session; push detail view

detail "Watch Match" (only live|upcoming) → play_match           main.py:502-598
 ├─ modal "Resolving…" dialog
 ├─ router.sources(session)  — owner-routed to the session's backend first
 │    (router.py:211-212, owner_of() at base.py:42-44)
 ├─ no sources → snackbar LBL_NO_STREAM
 └─ stream-picker dialog: one Button per Source.label            main.py:562-598
      └─ on_select → state.selected_source → _begin_playback     main.py:604-642
           ├─ store.external_player? → _play_stream: b64url → ktv:// deep link
           │    (launch failure → KTV install dialog)            main.py:715-724
           ├─ source.mint == "embed" → mint_m3u8 (WebView harvest) →
           │    hls_proxy.get_playlist_url(m3u8, referer) → rebuild Source mint=""
           │    (main.py:619-635)   ← NOTE: only "embed" is handled, see §8
           └─ stash _play_match/_play_sources/_play_index/_play_attempts
                → _open_player(index) → append /player View      main.py:637-669

in-player failure → _on_player_error                             main.py:681-699
 ├─ retry_same_source(attempts) → _reopen_player(same idx)       (1 retry)
 ├─ else next_source_index(...) → _reopen_player(next)
 └─ exhausted → _close_player + LBL_NO_STREAM snackbar
"Switch source" (user) → _cycle_source → _reopen_player(next)    main.py:701-708
```

**Refresh patterns.** Manual refresh button only (`home.py:440-447` → `load_matches`).
No timer, no pull-to-refresh, no live score polling; date tabs filter the already-loaded
list client-side (`state.filtered_matches`, `state.py:117-125`) — switching dates never
refetches, so counts for non-today dates are 0 unless the winning backend's catalog spans
them (socolive fetches ±2 days; damitv/streamedpk/cdnlivetv return their rolling
catalogs). Each provider additionally caches its own catalog in memory (60-120 s TTLs),
so repeated refreshes are cheap. The Home view is fully rebuilt by `update_home()` on
every state change — `AppState` is `@ft.observable` but nothing subscribes; updates are
pushed via the `page_obj.update_home` callback (`home.py:837`) that
`controller._update_home` (`main.py:766-777`) invokes.

## 5. State model

`core/state.py:73-128` — one module-level `AppState` singleton (`state`), plain mutable
fields, no persistence, no pub/sub:

- `is_loading`, `startup_stage` (loader copy while the probe race runs, `main.py:291/299`)
- `matches: list[Match]`, `selected_match`, `rooms: list[Room]` (never written), `selected_source`
- `leagues` (unique competition names), `active_date` (client-side date filter)
- **Backend tracking**: `backend_pin` ("auto" | name, persisted), `active_backend`
  (the router's `last_winner`), `backend_health` (name → state/latency/last_error),
  `backend_providers` (badge/Settings row dicts built by `AppController._provider_rows`,
  `main.py:306-324`), `backend_notice` (transient failover message)
- `update_available`, `update_data` (from the bg update check)
- Derived properties: `live_matches` / `upcoming_matches` / `finished_matches` /
  `available_dates` / `filtered_matches` (96-125)

**How the current backend is switched** — exactly two entry points, both calling
`AppController.set_backend(name)` (`main.py:326-336`): the header badge dropdown and the
Settings dropdown. `set_backend` → `router.set_pin(name)` → persist to store → reset
`backend_notice` → rebuild `_provider_rows` → **immediately `load_matches()`** → update
Home. There is no in-player backend switch; in-player recovery is source-level only
("Switch source" cycles the resolved `Source` list, never re-resolves via another backend).

**Settings screen** (`screens/settings_screen.py`) exposes: external-player toggle
(KTV deep link vs in-app player), content-source pin (auto + 10 providers) with live
per-provider health tiles and a "Test all sources" button (`main.py:347-366` — real
`probe()` + real `latest_releases(1)` per provider, recording failures into breakers and
health, then re-opens Settings), 3-way theme, and an About card. No search, no favorites,
no recents, no downloads.

## 6. The backend / rotation story as it exists today

### 6.1 Router (`services/router.py`) — already an animepahe-2.0 port
- Editorial order + per-request failover (providers never locked; `router.py:166-199`).
- Per-provider breaker (`_Breaker`, 61-95): 3 consecutive transport/parse failures → OPEN,
  30 s cooldown, one half-open trial; only a **failed trial** doubles the cooldown, cap
  300 s (`core/config.py:40-43`).
- Empty payload ≠ answer — chain continues; **only the last provider's empty is final**
  (`_is_empty` 98-104, check at 191-194). With ball808 (empty catalog) at position 9 and
  socolive last, the browse chain effectively terminates on socolive.
- `force=True` bypasses OPEN breakers (`sources_forced`, 214-216) — **defined but never
  called** (the retry path re-opens the same source list instead).
- Owner routing: `sources(session)` runs the session's own provider first
  (`owner_of`, `base.py:33-44`; call at `router.py:212`).
- Health recorded on every op (`_record_health`, 155-160) and consumed by badge/Settings
  via `AppController._provider_rows` (`main.py:306-324`) and `load_matches`
  (`main.py:467-477`).
- Startup probe race `probe_all` (223-253): all providers' `probe()` in parallel, 8 s
  total budget, 4 s per probe; a failed probe records **one** breaker failure (of three) —
  "dead backends get their breakers pre-tripped" (`main.py:262-265`). Wired and called
  (unlike the anime app, where the docstring at `router.py:19-21` says it was left dead).
- Pin semantics (`set_pin`, 135-142): "auto" keeps editorial order; a name pins first
  **with full failover retained** — the pinned backend that cannot serve is surfaced via
  `LBL_BACKEND_FALLBACK` in the notice banner (`main.py:481-491`, banner at `home.py:785-797`).

### 6.2 What "rotation" means here
`services/rotation.py` is **not** backend failover — it is **domain rotation** for the
Score808/808ball family (seizures/host moves). `RotationResolver` (100-183) probes an
ordered candidate list (`SCORE808_CANDIDATES`, 39-52, redirector first), certifies a host
through a 4-pass gate (status 200 + body > 30 KB, title `808Ball|Score808`, Nuxt marker,
**same-host match-page probe returning a known matchId** — 55-56, 82-97; the gate that
kills brand clones), caches the winner in memory, re-validates hourly via cheap `GET /`
(119-133), and re-runs from the top on any match-page failure (`invalidate`, 135-138).
Its only consumer is `Ball808Provider.__init__` (`ball808.py:60`). The module docstring
(21-22) claims store-backed caching, but ball808 never calls `load_cached` — the cache is
memory-only and lost on restart.

### 6.3 Auto-failover at play time
Play-time failover is **source-level, not backend-level**: `services/player.py` (1 retry
on the same source, then wrap-around through the resolved source list) executed by
`main.py:681-708`. If the whole source list fails, the app gives up with a snackbar — it
never returns to the router to try a different backend for the same match.

### 6.4 `hls_proxy.py` vs animepahe-tv's
socolive's proxy (`services/hls_proxy.py`, 205 ln) is a **minimal special-purpose** loopback
proxy for minted embed.st streams:
- Two endpoints only: `/playlist.m3u8?url=<b64>&referer=<b64>` and `/segment?...`
  (115-120). Upstream pulls use primp `impersonate="chrome_148"` (69) with
  UA/Accept/Sec-Fetch + Referer/Origin headers (44-56) — the GOAT CDN 403s plain httpx.
- Manifest rewrite (154-176): every segment URI and every embedded `URI="..."` (keys/maps)
  is pointed back through the proxy.
- Segment responses are unwrapped from the RIFF/WEBP GOAT container to raw MPEG-TS
  (`goat_ts.unwrap_segment`, 190; `goat_ts.py`).
- Hand-rolled HTTP/1.1 responses; status table is 200/400/404/405/502 only (199).
- **No Range/206, no caching, no variant or audio pinning, no key fetching, no
  negative-caching, no image proxying.**

animepahe-tv's proxy (`animepahe-tv/src/services/hls_proxy.py`, 919 ln) is the full
general-purpose version of the same idea (primp impersonation, hand-rolled HTTP/1.1, URI
rewriting) **plus**: a status/reason table including 206/416/418/429 (lines 46-62),
Range/Partial-Content support, **variant pinning (`quality=`) and audio-rendition pinning
(`audio=`)** on `get_playlist_url` (324-342) with `parse_hls_audio_tracks` (128+), a
memoized master-playlist cache (222-224, 364-388), and an image proxy with negative
caching (174-178, 227-228). Signature difference: socolive calls
`get_playlist_url(m3u8, referer)` (`main.py:628`); animepahe's accepts
`(target_url, referer, headers, quality, audio, ...)`. That is the seam a quality picker
would ride (§9).

## 7. The player (`components/player/live_player.py`)

- Core: `fv.Video` with `VideoMedia(resource, http_headers)` (line 45) — per-source
  Referer/Origin headers; `PlaylistMode.SINGLE`, `autoplay`, `AdaptiveVideoControls`,
  `BoxFit.CONTAIN`, `wakelock`, `fullscreen` (46-58).
- mpv tuning (24-28): `network-timeout=10`, `cache=yes`, `cache-secs=4` — "a small startup
  cache so live streams don't stall on the first segment request". This is the **entire**
  live-edge handling; there is no explicit live-edge logic (no `--demuxer-cache-pause`,
  no DVR window tracking, no re-jump-to-live).
- Chrome (overlaid via a `Stack` at 154-165): top bar (117-132) = match header with score,
  LIVE pill showing `match.minute` or "LIVE" (89-91), locale pill; bottom bar (135-152) =
  `Source: {label}` + "Switch source" button; close button (111-115). The error and
  next-source callbacks come from `AppController` (`main.py:651-665`).
- **What's missing vs a full VOD/anime player**: no seek-to-arbitrary-position UX beyond
  whatever `AdaptiveVideoControls` draws (meaningless on a live edge), no resume/positions
  (live), no subtitles (no subtitle track selection or `fv.Subtitle`), **no quality
  selector** (quality rides the source label only — variant pinning in the proxy is not
  exposed), no audio-track selector, no speed control, no stats/debug overlay, no
  PiP, no aspect/zoom toggle, no brightness/volume gestures, and no "Back to live"
  affordance. External-player mode (`ktv://`) exists as the escape hatch for anything the
  built-in player can't do (`main.py:715-724`).

## 8. Verified gaps / dead code (things that exist but do nothing)

1. **`mint="webview"` sources are never minted.** `main.py:619` checks
   `if source.mint == "embed":` only. `streamedpk` emits `"embed"` (mints fine), but
   `ppv.py:99/113`, `liveleagues.py:106` and `dlive.py:115` emit `mint="webview"` — those
   HTML embed-page URLs are handed straight to the mpv-backed player, which cannot render
   an HTML page → playback errors → retry policy exhausts → "No stream" snackbar. The
   fix is one condition (`source.mint in ("embed", "webview")`); the minter itself is
   generic (harvests any page's `.m3u8` from resource timing).
2. `router.search` + every provider's `search()` — implemented and chained
   (`router.py:208-209`) but **no UI call site exists**; there is no search screen.
3. `store.search_history` / `store.recent_matches` — fully implemented (105-158) but never
   called from anywhere.
4. `state.rooms` / `Room` — populated conceptually by the socolive provider but rooms are
   flattened into `Source`s inside `sources()`; `state.rooms` is never written.
5. `sources_forced` (`router.py:214`) — dead code.
6. `Competition` dataclass + `state.leagues` — leagues computed at `main.py:464-466` but
   never displayed (no league filter UI).
7. `rotation.py` store-cache claim — `load_cached` never wired (§6.2).
8. Promo slides deep-link to `WORKER_BASE_URL/anime` and `/movies` (cross-app funnel,
   `home.py:626/634`) — plus the same Worker serves this app's update checks.

## 9. Seams where animepahe-tv machinery can bolt on

The direction of previous porting is animepahe → socolive (router, breaker constants,
`_is_empty`, probe race, store layout, `Source.headers/referer` all say so in comments).
The remaining seams:

1. **Proxy upgrade (highest value)**: replace socolive's 205-line `HLSProxy` with
   animepahe's 919-line one. Same conceptual API (`start()/close()/get_playlist_url`),
   so `main.py:628` is the only call site to adapt (`get_playlist_url(url, referer)` →
   `(target_url, referer, headers, quality, audio)`). This immediately unlocks a real
   quality selector in the player (variant pinning) and audio-language selection, plus
   Range support and CDN-quota hygiene (master cache, negative cache) for the
   segment-heavy live case.
2. **The `mint="webview"` gap (§8.1)** is the one-line bolt-on that makes three existing
   providers (ppv, liveleagues, dlive) actually playable — animepahe's
   `webview_solver`/`cf_judge`/`ddos_solver` machinery is the hardened version of the
   same `flet_webview` harness socolive's `embed_mint.py` uses ad hoc; consolidating on
   it (or at least routing `mint=="webview"` through `mint_m3u8`) closes the gap.
3. **Typed backend failures**: animepahe's `providers/base.py:21` defines
   `CloudflareBlocked` and a `BrowserProvider` protocol (line 176). Socolive's router
   treats every exception identically. Porting the typed exception would let
   capture-gated backends (cameltv `loadSign`, ball808 channel-fetch) signal "needs
   WebView capture" distinctly from "dead", which the router could then use to trigger
   the minter instead of burning breaker failures.
4. **Provider protocol delta**: socolive's `sources(match_session)` is the analog of
   animepahe's `sources(anime_session, episode_session)`; animepahe additionally has
   `episodes()`, `episodes_for_title()`, `sources_for_title()` (base.py:154-170). Socolive's
   `Room` (SD/HD + language) already models the episode/quality dimension — a "rooms"
   listing endpoint per match would slot into the same shape if a quality/language
   picker-before-play is wanted (currently the picker lists flat `Source` labels).
5. **Store**: socolive's `JsonStore` is a subset of animepahe's 542-line store with the
   recents/search sections already stubbed in but unwired (§8.3-8.4). Porting animepahe's
   favorites/positions sections is additive — the namespaced-session keying
   (`base.py:29-44`) is identical, so per-backend favorites work "by construction" as the
   docstrings promise.
6. **Downloads**: animepahe's `services/downloads{,.py}` has no socolive counterpart and
   no UI anywhere; only relevant if highlights/VODs (finished matches) become a feature.
7. **Reverse-direction port (socolive → animepahe)**, explicitly flagged in-repo: the
   backend badge (`backend_badge.py:4-5`: "the anime app never built it"), the
   Settings content-source mirror with "Test all sources", the failover notice banner,
   the `startup_stage` loader copy, and the `_provider_rows` shape are all newer here
   than anything in animepahe-tv.
8. **Update plumbing**: `update_service.py` is byte-for-byte the same pattern as
   animepahe's (Worker `/config`, build-number compare) differing only in `APP_KEY`
   ("socolive") and current build — a shared module or config-driven key is trivial.
9. **Non-seam (keep separate)**: `goat_ts.py` (WEBP→TS unwrap) and `rotation.py` (domain
   certify gate) are socolive-specific and have no animepahe equivalent; animepahe's
   `kwik_resolver`/`aes.py`/`kwik_files.py` are its own VOD-side counterparts.

## 10. Eight-bullet summary

- **Navigation is a manual `page.views` stack, not render/tabs**: Home (with a decorative
  adaptive rail/bar whose "Settings" item just pushes a view), Match Detail, Settings,
  and the player are all Views appended/popped by `AppController`; back = FocusManager
  keyboard handler + `on_view_pop` + per-screen buttons, with dialog-close taking priority.
- **Startup never blocks on the network**: controller init restores theme/pin, builds the
  10-provider router, starts the loopback HLS proxy, then fires a non-blocking 8 s probe
  race whose only visible effect is loader copy (`state.startup_stage`) and pre-tripped
  breakers; Home triggers `load_matches` itself on first paint.
- **The data layer is `ProviderRouter` (already the animepahe-2.0 port)**: ordered
  failover, 3/30 s→300 s circuit breakers, empty-payload-continues, owner-routed
  `sources()` via namespaced sessions, `set_pin` for persistence, and a
  persisted-pin-fallback notice — the badge/Settings mirror reads live health.
- **"Rotation" here means domains, not backends**: `rotation.py` is a 4-pass certify gate
  (SSR size/brand/Nuxt/same-host match-page) for the Score808 family, used only by
  `ball808`, memory-cached only (the store-cache claim is unwired); backend-level
  auto-failover exists for browse but play-time failover is source-level only.
- **Play flow**: detail → `router.sources()` → picker dialog → (external KTV deep link |
  WebView-mint `embed.st` → loopback proxy) → full-screen player View with score/LIVE
  chrome, "Switch source", and a 1-retry-then-cycle policy; playback state lives in
  `AppController._play_*` fields, not in `AppState`.
- **The player is live-only minimal**: mpv with `network-timeout=10`/`cache-secs=4` as the
  entire live-edge strategy — no seek/resume/subtitles/quality/audio selection, and
  quality pinning is impossible until animepahe's variant-pinning proxy replaces the
  205-line one.
- **Verified dead ends**: `mint="webview"` sources (ppv/liveleagues/dlive) are never
  minted so those backends can't actually play today; `search`, store recents/search
  history, `sources_forced`, `state.rooms`, and the `Competition`/leagues UI are all
  implemented-but-unwired; cameltv/ball808 `sources()` are capture-gated `[]`s.
- **Cleanest bolt-on seams for animepahe machinery**: swap in the 919-line proxy
  (one call-site change → quality/audio switching), route `mint in ("embed","webview")`
  through the shared WebView solver, adopt `CloudflareBlocked` typing so capture-gated
  backends trigger the minter instead of breaker failures, and add favorites/positions to
  the already-compatible `JsonStore` — while back-porting socolive's badge/Settings/
  notice UX to animepahe, which its own docs say was never built there.
