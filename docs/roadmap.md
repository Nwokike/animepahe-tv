# Roadmap — the multi-source app, phased

Derived from the certified backend maps (docs/reference/backend-*.md), the
dependency ability studies (dep-*.md), and the house-app studies (app-*.md).
Every phase ships complete, commits separately, keeps the suite green, and
gets its own plan-mode presentation before work starts. The floor for every
source: everything animepahe-tv v1 did — search, browse, details, episodes,
streaming, downloads, continue-watching. Above the floor: each source's own
extras, used to the fullest.

## Phase 1 — AniKato to full source parity (strongest source first)
The map (backend-anikato.md) shows what our provider drops today:
1. **Subtitles**: resolve the 9 WebVTT tracks from getSources (they need
   `Referer: megaplay.buzz` — verified) and load them via
   `VideoSubtitleTrack` in the player (the flet-video map documents the API).
2. **Skip data**: per-episode `skip_data` from `/ajax/server?get=` (dropped
   today) + coarse `intro/outro` from getSources → the player's skip-intro.
3. **Details**: parse synopsis/type/status from the watch page into the
   detail screen (thin today).
4. **Episode metadata**: `data-sub/dub/timestamp/mal` flags discarded today.
5. **Discovery extras**: airing calendar (`ajax/schedule` + `/date`, real
   day tabs verified), genre/type/status browse, `/random`.
6. Corrections: `episode_stills` is poster-reuse (no thumbnails exist —
   evidence documented); VRF bare-retry fallback (not server-enforced).
Extras beyond the originals: broken-stream reporting (anonymous), comments
read, watch2gether chat read — ship if they fit the UI without clutter.

## Phase 2 — AnimePahe to full source parity
1. **`m=links`** in `sources()` (the map's biggest find): per-rendition
   `{audio, kwik, filesize, hd}` for 360/720/1080 — our provider only scrapes
   the play page today. Implement + verify through the app's own CF machinery.
2. **Details**: fetch `/anime/{session}` (synopsis, genres, studios, aired,
   backdrop, AniList/MAL ids) → the detail screen.
3. **Downloads**: `div#pickDownload` pahe.win menu (quality + MB size + BD).
4. **Dub grouping** (separate jpn/eng URLs exist) + AV1 codec flag.
5. Documented limits: no subtitles (hardsubbed), no schedule API, no
   watchlist API — the store IS that feature.

## Phase 3 — Kayoanime provider (new, complete from day one)
The map gives everything needed: WP catalog (search + title-relevance
ranking — its search is noisy; categories browse (27, ids mapped);
`orderby=modified` latest feed; `_embed` posters WITHOUT `_fields`),
Drive folder→file model (BOX ranges, per-season folders, dedupe by episode
number, three filename shapes), streaming via `alt=media` (206 + tail
verified) and keyless `usercontent?confirm=t` for downloads (real filename),
restricted folders surfaced as Group-gated (never retried), `href="#"` as a
maintenance skip signal.

## Phase 4 — Kusonime fixes + streaming
1. Two verified bugs: quality now lives in the block `<strong>` header
   (anchor text is host labels); range parsing from acefile slugs + dedupe
   by pixeldrain id (names are often range-less).
2. **Movies/specials stream today** (direct .mp4/.mkv via pixeldrain,
   verified 206) — wire them into the player path, not just downloads.
3. Google Drive as the second streamable host (confirm-GET → 206, verified).

## Phase 5 — AnimeOut corrections + discovery
1. Quality variants (1080p + 720p per episode) through the sources flow.
2. Categories/date filters for season browse; `_embed` posters (without
   `_fields`).
3. The file wall stays documented as a genuine limitation (full bypass
   evidence in the map) — catalog + episodes remain live.

## Phase 6 — App improvements from the dependency studies
Ranked by impact (each with evidence in dep-*.md):
1. **Player**: external subtitles (AniKato's tracks), watch-state
   persistence (`on_position_change`/`on_complete`), rate persistence,
   `mpv_properties` CDN tuning, controls dict for fullscreen chrome.
2. **Router/tasks**: deadline-scoped probes, `TaskHandle.cancel()` for
   superseded loads, parallel failover, bounded download concurrency,
   off-loop chunk writes (anyio §9; pin anyio via uv add).
3. **Notifications**: the follows → new-episode checker with
   `show(payload)` deep-link into the anime, `new_episodes` channel HIGH,
   BigPicture via a local thumbnail cache, permission flow (dep-flet-notifications §7).
4. **Ads**: production unit ids, destroy-before-dismiss fix, banner reload
   strategy, rewarded teardown (dep-flet-yandex-ads §7).
5. **Flet surface**: SearchBar, GridView, SharedPreferences, use_memo
   (dep-flet §8) — where they genuinely fit.

## Phase 7 — House-app ports (complete: app-ktv-player.md, app-sherlock.md, app-ddgs.md)
From the three app studies, ranked and evidence-backed:
1. **Player P0 (KTV)**: in-player fullscreen toast chip + dual dispatch
   (snackbars are invisible in fullscreen), local subtitle picker +
   persisted size + aspect fit, snapshot button — all verified absent.
2. **Player P1 (KTV)**: unmount safety-net position save, mandatory-modal
   re-show discipline, plain-function FocusScope (the @ft.component form
   is a known crash class per our own shell comment), FocusManager
   chaining, favorite-toggle idempotency.
3. **House craft**: Settings theme picker + observable `theme_mode`
   (Sherlock), `get_*` theme accessors, banner pool + interstitial
   interval (Sherlock), history clear-confirm + relative time,
   snackbar backstop + offline-first search branch (DDGS), storage
   debounce/exit-flush.
4. The theme-cycle premise corrected: it's OUR win (KTV is 2-way) —
   parity confirmed, placement gaps only (shared-header toggle).
Excluded with reasons: UMP consent, Sherlock-domain features, TLS
exemptions, the playlist extension heuristic, preloaded interstitials.

## Phase 8 — Test hardening + release
pyproject pytest ini block, F821 triage, ruff pass (29 errors, 36 files
unformatted — dep-test-stack), nightly canary CI, then the release ritual.

Standing rules: every capability runtime-discovered (no hardcoding/limits),
deps only via `uv add`, plan mode before each phase, commit per step,
suite green at every commit, boots clean with INFO lines.

## Phase 7.5 — Audit debt (complete)
The Phase 7 audit found work that was claimed but dead, so Phases 1–6 got
the same check (one agent per phase + a cross-cutting one). Findings and
resolutions:

- Live bugs found and fixed: AnimePahe details read a nonexistent
  `self.scraper.BASE`; the 1.0.4 favorites→follows migration called a
  nonexistent `self._touch()`; the notifications adapter called
  flet-notifications APIs that do not exist in 0.1.3 (`create_channel`, a
  `details=` kwarg, `BigPictureStyle(image_file_path=…)`).
- Wired what had no consumer: the new-episode checker (`start_episode_checker`),
  the notification tap deep-link, `request_permissions`, the startup probe
  (`probe_all`), and `sources_for_title_any` (playback now fails over by
  title, not just browsing).
- Displayed what was already parsed: synopsis, genres, MAL/AniList ids,
  studios, aired range.
- Quality correctness: AnimeOut keeps every quality of an episode (the
  dedupe dropped the second one); downloads ask instead of taking
  `sources[0]`; `m=links` reads `hd`.
- Deleted (dead, no gate to attach to): the rewarded-ad / early-access
  path, `cache.set_json/get_json/invalidate`, `store.remove_watch`,
  `app_shell._placeholder`, `BREAKER_HALF_OPEN_TRIALS`.

**Owner decision still open:** the rewarded "early access" format was
removed rather than wired, because it needs a free-line/paywall rule the
app does not have and inventing one is a product call. `flet_yandex_ads`
0.1.0 is installed and its test unit ids are used by the interstitial,
app-open and banner formats.

## Phase 7.5 addendum — the audit's own catches
Two independent audit passes over this phase's work found four defects in
it (all fixed) and, more importantly, three more of the same bug family
the phase was opened for — code calling an API that does not exist:

- `ft.OutlineInputBorder` (2 sites, search screen) and
  `ft.Dropdown(on_change=)` (settings) do not exist in the pinned 0.85.3;
  both raised at CONSTRUCTION, so the screen crashed on open. The comment
  next to the TextField border claimed the map form was the 1.0.4 API —
  the opposite of the truth.
- `webview.run_javascript_returning_result` does not exist in flet-webview
  (the package has `get_title()` / `get_user_agent()`), so the mobile CF
  solver silently never read the title or the device UA.

Plus: the dialog portal's Cancel/Back never dismissed the flag-driven
dialogs (it only cleared the imperative sheet); `choose_quality`'s
re-resolve dropped the serving provider, so a failover source was
re-resolved with the owner's capability gate; the single-rendition
download start had no try/finally, so an I/O error pinned the row's
spinner forever; and rows written before the platform-safe path mapping
leaked their files on delete.

`tests/test_surface_api.py` now guards the existence class (a plain
`ft.X` reference where X is not on the module), and the keyword-level
walk is deliberately NOT part of it: Flet accepts many kwargs through its
own machinery, so a signature check reports false positives.

### Step 4 addendum — the two extras that do NOT fit (verdicts, not silence)
- **Comments read**: the map documents the write path as login-only
  (`ajax/comment/add` → "You must be logged in to comment"), and no
  anonymous read endpoint is documented for it. A comments UI with nothing
  to read is clutter, so it is out until the site exposes a read route.
- **Watch2Gether chat**: `GET /ajax/watch2gether/chat/list/{room_id}` is
  anonymously readable, but a chat fragment without a room picker and
  without synchronized playback is half a feature. The write path (start /
  end / change / chat-save) is 401 anonymous, so it can't be built out
  either. Out until the whole watch-together surface is in scope.

**Shipped**: broken-stream reporting — the watch page's own form,
  POST-only and verified to work anonymously, offered on every episode's
  menu with the site's own issue vocabulary and its validation message
  surfaced verbatim.

## Phase 8 — Downloads, YouTube-style (complete)
Research first (sourced): Android Media3's seven-state machine — pause is a
persisted stop reason that keeps the partials, resume is clearing it; a
queue caps concurrency (default 3) in start order; progress is bytes +
a percent that is explicitly unknown when the length isn't; progress
updates do NOT fire the listener, the UI polls. YouTube documents no
per-item pause (auto-resume on reconnect, "Retry download" the only
manual action); Netflix is where "Download Season" comes from (one button
+ per-episode buttons, quality as a global setting); no app remuxes —
they store bytes as served. flet-notifications 0.1.3 already advances one
row by re-showing its id.

1. **State machine**: queued / downloading / stopped / completed / failed
   / removing / restarting in the manifest; pause = a persisted stop
   reason keeping the partials; resume and retry from the job's own
   manifest; ONE queue with a cap across both paths (the limiter used to
   cover direct files only, so an HLS batch ran unbounded); one progress
   contract — which fixed a live bug where the direct path's 3-arg
   callback raised TypeError into a swallow, so a file download's
   progress never reached the UI at all.
2. **The row**: the bar lives INSIDE the name row; per-state actions
   (Pause/Cancel, Resume/Delete, Retry/Delete, Play/Delete); unknown
   length renders indeterminate rather than 0%.
3. **The tray**: one row per download, advanced by re-showing its id in
   the throttled flush; downloads live in their own id band so a
   finished download can never replace a series' alert; the tap
   deep-links to the anime.
4+5. **Whole folder**: "Download the series" with a From/To range
   (defaulting to everything not yet downloaded) + Highest/Lowest/As
   served; each episode is an INDEPENDENT job, so a dead host, a walled
   link or an I/O failure costs that episode only; the queue absorbs the
   batch. The dialog is hook-free (built in an event handler) — the
   report dialog had the same violation and is fixed the same way.
6. **The badge**: the serving backend + a state colour; tapping opens a
   picker with every provider's live health (breaker state, latency,
   last error) and one-tap pinning.

Also fixed along the way (found by the owner's live run): the home screen
crash on first paint; the ~20s startup stall on web; the startup probe
opening a Cloudflare window; the font 404. All recorded in
docs/testing-findings.md along with the three open items (web image CORS,
search showing 0 episodes, 170 episodes unpaged).
