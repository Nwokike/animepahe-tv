# Swarm Audit — 2026-10-13

Full-repo quality audit: 98 subagents (94 single-file audit agents + 4 comparison agents)
run in batches against the installed `.venv` as the only source of truth.
Audited: **59 files in `src/` + 32 files in `tests/`** (91 files; 4 assigned paths did not
exist — see §8). Every Flet/third-party API claim was verified against installed
packages (flet 1.0.4, flet-video/webview 1.0.4, flet-notifications 0.1.4,
flet-yandex-ads 0.1.0, primp 2.0.1, pywebview 6.2.1, anyio 4.15.1, httpx 0.28.1,
msgpack 1.2.3). Dep docs under `docs/reference/` are version-stale in places
(flet doc says 0.85.3, primp 1.3.1, oauthlib 3.3.1, flet-notifications 0.1.3) —
install source wins.

Verdict tally: **5 PERFECT · ~18 GOOD · ~68 NEEDS_FIXES**.
Baselines: `pytest` = 1 failed / 265 passed (`test_surface_api.py::test_the_two_known_phantoms_stay_gone`,
root cause found — §1.20); `ruff check src tests` = 402 findings.

---

## 1. Critical bugs (crash / hang / data-loss — fix first)

### 1.1 primp 2.0.1 API hallucinations (5 files — root cause: dep-primp.md documents 1.3.1)
`AsyncClient` has **no** `aclose`/`close`/`is_closed` (cleanup is `__aenter__/__aexit__` only),
`AsyncResponse` has **no** `reason_phrase`/`history`.
- `src/services/animeout_solver.py:96` — `await client.aclose()` in `finally` → AttributeError on
  every probe path, so persisted clearance is **never reused** (the file's whole purpose) + client leak.
- `src/services/providers/animeout.py:402`, `:543` — same hallucinated close (shutdown path + owned client).
- `src/services/providers/kusonime.py:608-610` — `aclose()` + `is_closed` (neither exists).
- `src/services/hls_proxy.py:728` — `resp.reason_phrase` �� AttributeError on **every** `/segment`
  and `/key` request before headers are sent. The proxy cannot run as written.
- `src/services/hls_proxy.py:194,232` — `aclose()` on bind-failure path and `stop()`.
Fix: use `async with primp.AsyncClient(...)` / `await client.__aexit__(None, None, None)`;
drop `reason_phrase` reading (keep/extend the local reason table — `docs/reference/app-ktv-player.md`
§3 P2.15 reason-phrase forwarding is **not implementable** on primp 2.0.1; delete the dead plumbing).

### 1.2 Undefined name — guaranteed NameError
- `src/main.py:1318` — `notifications_stable(anime_session)` is referenced but defined nowhere
  in src or docs → NameError on the first follow-with-HTTP-poster notification path.
  Fix: import/define the stable-filename helper.

### 1.3 Broken providers
- `src/services/providers/anikato.py:732` — `for n, ids in entries` unpacks 5-tuples
  (`_parse_episode_list` returns width-5) → `ValueError` on **every** `sources()` call.
  Fix: `for n, ids, *_ in entries`. Zero test coverage (no `sources()` test exists).
- `src/services/providers/kayoanime.py:336-338` — `anime()` caches `(anime, folders)` tuple but
  returns `Anime` on miss / tuple on hit (type break on 2nd call);
  `:395-397` — `_quality` never populated in `anime()`, so `sources()` resolution stays 0;
  `:431,355-380` — one folder's transport error aborts the whole `episodes()` walk (unguarded).
- `src/services/providers/animeout.py:300`, `src/services/providers/kusonime.py:492` —
  `return []` breaks the `tuple[list[Episode], bool]` contract → unpack crash.
- `src/services/providers/anikato.py:591,640,316` — base64 `ids_token` unquoted in query
  (`+` decodes as space), `episode_id` always sent as `""`, `content=urlencode(...)` str vs bytes.
- `src/services/providers/base.py:40-79` — `Provider` Protocol omits
  `episodes_for_title`/`sources_for_title` (router calls them on every provider) and wrongly
  requires `filters`/`browse`; `latest_releases` annotation mistyped.

### 1.4 Downloads engine
- `src/services/downloads.py:813-819` — segment worker swallows exceptions and re-appends with
  **no retry cap** → one 404 segment livelocks the job forever.
- `:720-734` — HLS path never acquires `self._job_limiter` (only `_run_direct` does at :577)
  → N HLS episodes run N×6 unbounded concurrent fetches.
- `:443-462` — `pause()` pops `_tasks`/`_cancel` without cancelling the running task → orphaned
  writer; a later `start()` spawns a **duplicate writer on the same dir**.
- `:895-896` — 200 (not 206) response resets mode to `wb` but `done` still starts at `have`
  → byte progress overcount; `:269,358` — `state == completed` short-circuit never verifies
  files exist (deleted segs + stale manifest = permanently unplayable row);
  `:476-481` — `resume()` prefers passed `url` over manifest url (wrong bytes appended);
  `:103` — `(pending_key or count == 0 or True)` dead guard; `:840` — `variants[-1]` is the
  last variant, not top bandwidth.
- Fixes per `docs/reference/dep-anyio.md` §9.4/§9.5 still open for the HLS path:
  wrap segment fetch in the shared limiter; `to_thread.run_sync` manifest read/write.

### 1.5 Player + TV
- `src/components/player/immersive_player.py:1317` — `await self.video.seek(end + 1)` passes raw
  seconds; `flet-video` `seek(position: DurationValue)` treats int as **milliseconds** →
  skip-intro seeks to ~85 ms instead of ~85 s. Fix: `ft.Duration(seconds=end + 1)`.
- `:106` — `_stream_variants` relative-URI resolution collapses every variant onto the first
  media URI (`uri = line if http else base`) → quality pins all point at one rendition.
- `:484-486` — resume-read sets `_speed_rate` + chip text but never assigns `video.playback_rate`
  (initial speed lost). `:1146-1151` — screenshot snack fires before `take_screenshot()` succeeds.
  `:1118-1120` — `_on_first_ready` hides overlay unconditionally (can hide a just-raised error card).
  `:1224-1244` — overlapping `_toast_show` hides kill newer toasts early.
- `src/hooks/use_focus_scope.py:36` — `page.run_task(lambda: result)` raises
  `TypeError: handler must be a coroutine function` → **player Back broken** for the app's only
  caller (`app_shell.py:442` sync lambda). Fix: wrap in `async def _run(): await result`.
- `src/core/focus_manager.py:3` — `"Backspace"` in `_BACK_KEYS` with no focus guard → global Back
  fires while typing in search/discover/detail TextFields. Also `:26-35` chained async previous
  handler never awaited; `:34` back-handler call unguarded.
- `src/components/focus_styles.py:76-87,100-110` — `card_focus_scale(scale)` validates then
  discards `scale`; `attach_focus_zoom` **clobbers** pre-existing `on_focus`/`on_blur`
  (e.g. `FocusManager.make_scroll_on_focus`); frozen-guard contradiction (assignment unguarded,
  `except RuntimeError` too narrow).
- `src/screens/anime_detail_screen.py:721` — `_preset()` passes `ui` into the `downloads` param →
  preset never sticks + `r.get` on str crashes. `:124` — `PopupMenuButton` nested inside
  `FilledButton` content → menu unreachable on D-pad (parent eats focus). `:333` — report
  dialog `checked` set never re-rendered. `:425` — string breakpoint keys.
- `src/app_shell.py:96` — `close_player` flips the view but never clears `state.player_open` /
  unmounts `page.overlay` → player stage leaks (audio can bleed). `:91` — `open_discover` never
  calls `set_active_tab`. `:512-539` — double `handle_close()` (redundant). `:192,297,372` —
  `page.overlay.append/remove` + `update()` during render (side-effect-in-render).
- `src/components/cross_promo.py:73-79` — `_rotate()` task never cancelled on unmount → leak;
  `:76` — stale `pinned` closure makes pinning a no-op; `:103-110` — `page` can be None →

### 1.6 Cloudflare solvers
- `src/services/desktop_cf_solver.py:58-99` — **user closes window → 2-minute UI hang**: the
  120×1 s poll keeps calling `get_cookies()` on a dead uid and the parent's `communicate()` has
  no timeout. Fix: break on `window.events.closed`, exit non-zero. Also case-sensitive
  `XSRF-TOKEN` marker miss (`:24`), silent timeout exit 0 (`:98`), divergent UA fallbacks (`:6`).
- `src/services/webview_solver.py` — routes `ANDROID_TV` to the mobile WebView path, but
  `flet_webview._check_mobile_or_mac_platform` allows only ANDROID/IOS/MACOS → on real TV every
  method raises `FletUnsupportedPlatformException` and the solver spins forever. `:265-274` —
  `set_javascript_mode`/`disable_zoom` called **before mount** → `RuntimeError` swallowed, both
  are dead code. `:72-80` desktop `communicate()` no timeout, no Cancel. `:141-148` blocking
  pyjnius `getCookie` on the loop. (Good news: all four `dep-flet-webview.md` §7 API bugs —
  bad ctor kwargs, `on_page_finished`, `run_javascript_returning_result`, `e.url` — are FIXED.)
- `src/services/ddos_solver.py:248-260` — re-solve reuses the same primp client whose
  `cookie_store=True` jar still holds a dead `cf_clearance` → stale cookie resent. Also double
  `solve()` per `get()`, un-checked retry result, concurrent `get()` races on `_solved`, and
  `logger.info` logs the full Cookie header (leaks `cf_clearance`).
- `src/services/kwik_resolver.py:127` — `_verify` calls `_headers(url)` on the CDN URL instead of
  `_headers(referer)` → Referer always falls back to `https://kwik.cx/`. Unguarded `get()` calls
  break the documented None contract.

### 1.7 HLS proxy (besides 1.1)
- `src/services/hls_proxy.py:530,305` — `headers.get("content-type")` assumes lowercase (primp
  returns origin case). `:742` — upstream header values written raw (response-splitting: strip
  CRLF). `:383` — single unbounded `readline()`. `:288` — `_master_cache` keyed by URL only
  (ignores headers), never pruned. `:225-228` — `stop()` CancelledError path skips cleanup.

### 1.8 State / store / services
- `src/core/state.py:184-189` — only 5 of ~20 collections are reassigned in `__init__`; the rest
  stay shared class-level raw lists/dicts, **never wrapped** by ObservableList/ObservableDict →
  in-place mutations before first reassignment never notify → silent UI staleness.
  `:180` — `starting_downloads: set` is unobservable by design. `:99` — `player_error` declared
  twice. `@dataclass(unsafe_hash=True)` with mutable fields will crash if hashed.
- `src/services/store.py:411-427` — `get_follows` bypasses `self._lock` while every other
  accessor serialises. `:47-56` — `_atomic_write_json` never fsyncs before `os.replace`
  (docstring promises durability). `:8-10` — docstring claims a debounce that doesn't exist
  (every `put_section` flushes synchronously). `:236,:467` — non-dict corrupt rows crash
  `record_watch`/`add_follow` eviction sorts. (`toggle_follow` idempotency already landed —
  ktv doc §2 row 16 is stale.)
- `src/core/notifications.py:123` — `on_tap` assigned post-registration with **no update push**
  → Dart may never learn the handler; taps silently never fire. `:198,242,176` — `_unavailable`
  short-circuit only set in `request_permissions`, so other invoke-failure paths re-pay the full
  timeout forever, contradicting the module docstring.
- `src/services/update_service.py:29` — `apk_url` passes `update_url` through **unsanitized** →
  a compromised worker drives arbitrary-URL launch via update_dialog. `:24` — string `server_build`
  raises TypeError. Fix per Sherlock P10: `_safe_https_url` + `_safe_text` + int coercion.
- `src/services/animepahe.py:234,237-238,378-380` — `int()/float()` on empty-string attributes
  raise; `"1080p"`-style resolution crashes; `:210` int `params` value violates primp's
  `Mapping[str,str]`; empty results negatively cached; unbounded poster fan-out.
- `src/core/dialogs.py:31-44` — native (framework) dismiss bypasses `_app_dialog`, leaving a
  stale registration that eats one Back press and closes nothing; single slot orphans stacked
  dialogs; registration cleared before the close attempt (unretryable, still returns True).
- `src/services/external_player.py:128` — `launch_url` returns True unless it raises, so the
  KTV-install dialog never shows for unhandled `ktv://` schemes (use `can_launch_url` first).
  `.rstrip("=")` padding loss; `quote(title)` leaves `/` unescaped.
- `src/core/shared_services.py:30` — `page.services.extend()` duplicates flet 1.0.4's
  auto-registration (`Service.__post_init__` registers via context) → double-mount.
- `src/components/update_dialog.py:39-53` — mandatory update escapable via global Back
  (`close_app_dialog` clears + pops without re-showing). `support_dialog.py:25-30` and
  `settings_screen.py:143-144` bypass the top-of-stack check (`close_app_dialog`) → can pop a
  SnackBar and orphan the dialog. `update_dialog.py:36` KeyError on missing `apk_url`.
- `src/screens/settings_screen.py:319-328` — `ft.dropdown.Option("auto", ...)` is a 0.x leftover
  (1.0.4 exposes `ft.DropdownOption(key=, text=)`) → suspected crash on the content-source
  dropdown. `:309-314` — double-spawn: screen `spawn()`s what `main.py:2193` already spawns.
  `:252-254` — async `save_theme_mode` called un-awaited → theme never persists.
- `src/state/controller_ctx.py` — ~12 attributes monkey-patched at runtime but undeclared;
  `open_backend_picker`/`pin_backend` declared but never wired → picker taps are silent no-ops.
- `src/core/config.py` / `constants.py` — ~60% dead constants (4 unreferenced config values,
  7 `ERR_*` + 13 `LBL_*` never imported while screens hardcode the same strings);
  `DRIVE_WEB_KEY` hardcoded with no env override. `kusonime.py:22-23` redefines
  `KUSONIME_API/BASE` locally instead of importing config (drift risk).
- `src/core/tokens.py` — zero importers (dead scale; call sites hardcode duplicates;
  missing the pervasive 16 px step). `src/services/cache.py` — still unused (no get/set callers);
  `close()` never called (sweep task leaks); corrupt non-dict entries crash `get()`.

### 1.9 Good news (verified fixed since the docs were written)
- `src/services/ads.py` — `show() → wait_for_dismiss() → destroy()` ordering now correct
  (fixes the flet-yandex-ads §7.2 race); rewarded leak no longer applies (intentionally unwired).
- `src/services/webview_solver.py` — all four documented §7 API crashes fixed.
- `src/core/theme.py` — observable `theme_mode` + 3-way cycle + Settings picker landed
  (Sherlock P1 / ktv §2.14 mostly closed); terminal dialog uses fixed height + copy snack
  (Sherlock P5); `toggle_follow` re-read-after-write (ktv P1.8); FocusManager chains
  (ktv P1.7); `use_focus_scope` is a plain function (ktv P1.6); `core/notify.py` has
  fullscreen dual-dispatch toasts (ktv P0.1); mandatory update re-shows on dismiss (ktv P1.5).
- `src/services/router.py` — anyio task-group race partially adopted (tail races; head still
  sequential-without-deadline, `asyncio.wait_for` per dep-anyio §9.1 remains).

### 1.10 Remaining API-level nits worth fixing
`search_screen.py:421` + `home_screen.py:344` — `row["anime_session"]` KeyError on malformed
rows; `result_card.py:118` `col=None` vs `FilledButton.col` typing; `animepahe_provider.py:172`
unguarded `ddos.get`; `:189` `sources_for_title` bypasses `self.episodes()` so `_anime_ids`
never populates (loses audio/filesize/download_url); `downloads_screen.py:228` `size_bytes=None`
sum crash, `:49` unclamped percent, `:63` orphaned-row dead end, `:184` `ink=True` without
`on_click`; `use_debounce.py:35` missing `delay_ms` dep; `logger_handler.py:87` telemetry
`started` shows now-not-start; `notify.py:62` rapid snacks stack (the `RuntimeError` guard
can't trip on distinct instances); `empty_state.py:46` silently drops a lone action arg.

## 2. Test-suite status
- **`test_surface_api.py::test_the_two_known_phantoms_stay_gone` (the 1 failure) is a STALE TEST,
  not a src regression**: line 57 asserts `not hasattr(ft, "OutlineInputBorder")`, but installed
  flet 1.0.4 added that class (`controls/material/form_field_control.py`). No src file uses a
  phantom (grep clean). Line 67's `field.border is ft.InputBorder.OUTLINE` also fails (identity
  check on a deprecated enum member). Fix in the test: drop/invert the phantom assertion and
  compare shapes with `==`.
- Systematic test blind spots (would not catch the criticals above): no `anikato.sources()` test
  (the :732 crash), probe tests stub out the real `_probe` (the aclose bug), no
  `DownloadManager` lifecycle tests (livelock/limiter/pause), no `kayoanime.anime()` second-call
  or raising-folder tests, router empty-then-raise KeyError untested, `test_variants.py` asserts
  only `variants[0].uri` (hides the aliasing bug) and uses a sorted master (hides the
  last-variant pick), `test_download_quality.py:242` builds choices by hand so `_source_choices`
  key-drop is invisible, `test_wiring.py:89` allowlists the two never-wired picker actions.
- Vacuous/misleading tests: `test_house_layer.py:90` (recomputes `not [] and not False` inline),
  `test_notify.py:90-111` (asserts an unreachable `RuntimeError` branch — the real stacking bug
  is the opposite), `test_craft_layer.py:90` (name promises rotation-pausing, asserts only a
  constant), `test_player_spec.py:47` (never calls `choose_quality`), `test_search_history_rows`
  dialog lacks `modal` asserts, `test_state_dataclasses`-style round-trips assert defaults only.
- Infra: `[tool.pytest.ini_options]` block from `docs/reference/dep-test-stack.md` §5 still not
  applied (emits `PytestDeprecationWarning` every run); 10 `asyncio.run` call sites could become
  native `@pytest.mark.asyncio` tests (`test_store.py` sets `FLET_APP_STORAGE_DATA` at module
  import — leaks to every other module); ruff still reports ~402 findings incl. 3 `F821`.

## 3. Dependency opportunities confirmed still open (from docs/reference/dep-*.md, re-verified)
- **flet 1.0.4**: `use_memo`/`use_callback` (zero hits; makes existing `@memo` effective);
  `SharedPreferences` service for settings; `GridView` virtualisation for poster grids and
  episode grids (`anime_detail_screen.py:413` builds every card eagerly); `Hero`+
  `AnimatedSwitcher` poster→detail; `FilePicker`+`StoragePaths` for downloads dir/export;
  `Share`/`HapticFeedback` (Sherlock P6); `SearchBar`+`AutoComplete` evaluated and **rejected**
  (AutoComplete suggestions are str-keyed; can't carry `{title, session}`; route-overlay breaks
  TV Back — keep the hand-rolled field, but add `autofocus` and focusable suggestion rows).
- **flet-video 1.0.4**: `controls` dict form (NORMAL vs FULLSCREEN; `VideoVolumeButton` is
  desktop-only and unused); `on_track_change` re-arm after playlist swap;
  `VideoSubtitleTrack.none()/auto()`; mpv_properties are already in use (good).
- **flet-webview 1.0.4**: replace the 1.5 s `get_current_url()` poll with `on_url_change`;
  `get_title()`/`get_user_agent()` instead of JS round-trips; `on_progress`/
  `on_web_resource_error` stall signals; `clear_cache()`/`clear_local_storage()` between attempts;
  `prevent_links`; call `set_javascript_mode`/`disable_zoom` **after mount**.
- **flet-notifications 0.1.4**: tap-payload deep link → detail screen; immediate `show()` (not
  `schedule()`); per-anime stable id + `InboxStyle` batching; `NotificationAction` buttons;
  `are_notifications_enabled()` probe; cold-start `get_notification_app_launch_details()`.
- **flet-yandex-ads 0.1.0**: production `R-M-XXXXXX-Y` ids (still all `demo-*-yandex`);
  `set_user_consent` toggle (GDPR; currently hardcoded True); `on_impression`/ILRD telemetry;
  preload-next + `on_load_failed` retry; `cancel_loading()` on fast skips; banner `max_height`
  + periodic `reload()`.
- **anyio 4.15.1**: `CapacityLimiter` around HLS segment fetches (§1.4); `to_thread.run_sync`
  for manifest + completion-sweep I/O; `fail_after` instead of `wait_for` in router probes.
  (Pin note: anyio is already a direct dependency — `pyproject.toml:11`.)
- **msgpack 1.2.3**: only worth it if poster/thumbnail bytes ever get cached on disk.
- **pywebview 6.2.1**: pin UA via `start(user_agent=)`; event-driven cookie checks
  (`loaded`/`response_received`); renderer guard (`renderer in ('edgechromium','cef')`) to
  convert the silent-MSHTML 120 s spin into a fast error; hidden-first window with on-demand show.

## 4. Comparison-agent results (Sherlock + ktv-player, verified against current code)
### Still-open gaps worth porting (ranked by value/effort)
1. **Update hardening** (both apps): https safelist + `_safe_text` + offline changelog —
   `update_service.py:15-34` / `update_dialog.py:36` (Sherlock `services/update_service.py:24-33`;
   ktv `UpdateInfo` dataclass + `type`/announcement).
2. **Storage durability**: fsync before `os.replace` + 1 s write debounce + corrupt-file .bak —
   `store.py:47-56,82-99` (Sherlock `storage_service.py:146-217`).
3. **Ads**: banner slot pool + 30 s interstitial interval + preload-next —
   `banner_ad.py:49-123`, `ads.py:54-76` (Sherlock `banner_ad.py:44-66`, `ad_service.py:232-242`).
   Do NOT port UMP (AdMob-only).
4. **Lifecycle re-probe** (`on_app_lifecycle_state_change` RESUME/SHOW) —
   `main.py:337-355` has the toasts but no re-probe (Sherlock `main.py:1872-1907`).
5. **Crash reporter** (per-crash files + rotation + page hook) — ktv `core/crash_reporter.py:88`;
   AP only logs+snacks in `_on_page_error` (`main.py:2090-2095`).
6. **Player**: settings double-open guard (ktv `handlers.py:522-527`); snapshot **persistence**
   (MediaStore insert + filesystem fallback — button + `take_screenshot` exist, save does not);
   local subtitle FilePicker + persisted size (size/fit already persisted — picker is the only
   remainder); 1–2 auto-retries with reset-on-success before the final error card.
7. **OfflineFlow retry/skip card** (ktv `components/offline_flow.py:49`) — AP detects offline
   but grids just go empty. **Theme `SearchBarTheme` slot** + `Toggle-save` race guard for the
   theme write (`home_screen.py:501-509`). **CDN header-override map** (shape only, not ktv's
   hosts). **Desktop shortcuts** (Ctrl+K/R, ktv `use_keyboard_shortcuts.py:99-109`).
8. **PiP** (phone-gated) + **logo/poster disk cache** (ktv `logo_cache.py`) + inbound
   `ktv://` deep links (AP's `external_player.py` is outbound-only) — all optional.
### Doc items verified CLOSED (stale docs)
Sherlock P1 (theme observable+picker), P5 (terminal fixed height + copy snack), P7 (dialog typing),
P9 (clear-confirm; relative-time still open), P11 online-toast; ktv P0.1 (toast chip), P1.4
(unmount save), P1.5 (mandatory re-show), P1.6 (plain FocusScope), P1.7 (chaining), P1.8
(toggle idempotency), P2.14 (theme completeness minus search slot), Settings Appearance picker,
watchdog/speed-reapply/quality-audio pinning/VOD resume/mpv tuning/close path.

## 5. Verdicts by area
- **PERFECT (5)**: `src/__init__.py`, `src/core/__init__.py`, `src/components/player/__init__.py`,
  `src/services/__init__.py` (all empty package markers), `tests/test_focusable_cards.py`.
- **Clean-ish services**: `router.py` breaker state machine, `aes.py` cipher core,
  `external_player.py` structure, `cache.py` (unused), `update_service.py` (tiny but needs
  safelist), `ads.py` (correct lifecycle; demo ids/consent remain).
- **Needs work**: `main.py` (controller), `app_shell.py`, all six screens (each 1-5 issues),
  `core/state.py`, `store.py`, `downloads.py`, `hls_proxy.py`, `immersive_player.py`,
  `webview_solver.py`, `desktop_cf_solver.py`, all five providers.
- **Tests**: correct where they test, but systematically blind to the criticals above;
  6 files contain vacuous or fiction-locked assertions.

## 6. Root causes behind the bug classes
1. **Version drift**: dep docs frozen at 2026-10-11 (primp 1.3.1 → 2.0.1 removed `aclose`/
   `reason_phrase`; flet 0.85.3 → 1.0.4 added `OutlineInputBorder`, deprecated
   `InputBorder.OUTLINE`, auto-registers services). The aclose/reason_phrase hallucinations
   account for ~8 of the criticals — run `uv lock --upgrade-package primp` awareness or
   re-verify all primp call sites against 2.0.1.
2. **Untested new surfaces**: downloads HLS path, anikato `sources()`, real probe functions,
   kayoanime `anime()` cache — every file written in the download/provider phases has 0
   behavioral coverage of its risky paths.
3. **Flet component-tree rules**: frozen controls mutated post-return in several screens;
   dialog-registry bypass instead of `close_app_dialog`; pre-mount service method calls.

## 7. Suggested fix order (if the team wants it)
1. §1.1 primp hallucinations (5 files) — unblocks HLS proxy + clearance reuse.
2. §1.3 provider crashes (anikato :732, kayoanime cache/quality, tuple returns) — unblocks 3 of 5 providers.
3. §1.4 downloads livelock + pause/duplicate-writer + HLS limiter.
4. §1.5 player seek units + Back TypeError + Backspace collision + focus clobbering.
5. §1.6 solver hangs (window-close, TV gate, pre-mount ordering).
6. §1.2 NameError, §1.8 store lock/fsync, notifications on_tap, update safelist, mandatory-Back escape.
7. §2 fix the stale phantom test; then the §3 opportunities.

## 8. Observations
- **3 untracked test files vanished mid-run**: `tests/test_providers.py`, `tests/test_state_dataclasses.py`,
  `tests/test_theme_cycle.py` existed at audit start (stale `__pycache__` entries remain) and were
  deleted before the run finished — nothing was committed (HEAD unchanged). Most likely parallel
  editing; flagged in case it was unintended. Their prior content is recoverable only from the
  `.pyc` files.
- `src/services/providers/__init__.py` and `src/views/home.py` do not exist (imports work via
  namespace-package semantics / direct submodule paths). Add an explicit `providers/__init__.py`
  for a stable public surface.
- 2 subagents timed out and were re-dispatched; all 91 existing files were eventually audited.
