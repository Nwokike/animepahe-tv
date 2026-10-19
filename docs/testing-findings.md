# Testing findings — from the user's web run (2026-10-13)

Recorded during Phase 8 development. NOT fixed yet — the owner's instruction
was to finish Phase 8 first, then focus on testing and fixing. Each item
below is a real observation from `flet run -w`, with the log evidence.

## 1. No images render at all (series banners AND episode thumbnails)

Log evidence — every image the home/search grid asks for:

```
[ERROR] __main__: unhandled page error: HTTP request failed, statusCode: 0,
  https://cdn.anipixcdn.co/thumbnail/7083cb21e7257ca11b805a9bf4f70be4.jpg
```

**Cause (confirmed by the log shape):** the app runs on the **web**
renderer, and Flutter's `Image` fetches cross-origin URLs directly. The
image hosts send no CORS headers, so the browser refuses every one. This
is a web-platform limitation, not a provider bug: the URLs themselves are
correct (a later direct primp fetch of the same URL returned 200), and on
Android the same URLs load in the native HTTP stack.

**What the app must do (owner's rule):**
- A provider that serves a **series banner** uses it (nkiri-style: one
  banner per series, used everywhere — recent episodes, search results,
  the detail header).
- A provider that serves **per-episode thumbnails** uses them where an
  episode needs one.
- A provider with neither falls back to the series banner. **Every
  provider must show at least one image.**
- On web, the images need a CORS-capable path (the app already runs an
  HLS proxy on localhost; a same-origin image route through it would fix
  web without touching providers). That is a decision for the testing
  phase — do not hack it into providers.

## 2. Search results show "0" episodes

Black Clover's search row showed 0 episodes. The owner's rule: **show what
the provider gives you, hide what it doesn't — never print 0.** Providers
that publish a count (anikato's `ep-status sub`, WP's post metadata, the
pahe `Episodes:` row) must be mapped through; a missing count renders
nothing at all. Suspect: the count is parsed but never carried into the
search-result row, or the provider's row leaves it 0 and the UI formats
it unconditionally.

## 3. 170 episodes rendered at once

Opening Black Clover rendered all 170 episode cards in one grid, with a
pager underneath. The owner's rule: **cap a page (≈24) with Next/Previous,
and never render the whole series at once** — performance, not just
convention. The old apps (in the default workspace: the original
animepahe app and nkiri-tv) are the reference for the exact cap and the
pager shape; study them before changing this.

## Also observed (already fixed during this session — for the record)

- The home screen crashed on first paint: `'Anime' object has no attribute
  'anime_session'` — anikato's `latest_releases` returned `Anime` where
  the provider protocol promises `LatestRelease`.
- Startup blocked ~20s on the web renderer: flet-notifications has no Dart
  half under plain `flet run`, so every invoke waited its full 10s
  timeout. The adapter now remembers the failure once per session.
- The startup probe opened a Cloudflare verification window: AnimePahe's
  `probe()` went *through* the DDoS solver. Probes are now raw (any HTTP
  answer = alive), and the solver can only run on a deliberate user
  action.
- `outfit.css` 404'd because the font path was addressed as
  `assets/outfit.css` while the assets dir already maps to `src/assets`.

## Noted after the Phase 8 Step 2 boot (dev-mode only, benign)

`[ERROR] unhandled page error: Exception: Unknown service: LocalNotifications`
appears ONCE on the web renderer, before the adapter's session-level
detection remembers the failure. The home screen renders correctly after
it. A built app (which ships the Dart half) doesn't hit it; if it still
annoys during testing, the fix is to construct the service lazily inside
the first guarded call rather than at detect() time.

## 2026-10-15 — AniKato CDN "doors" (ad-stub playlists, fixed) + AnimeOut's current wall

### AniKato: one realid, several CDN doors — and one serves decoys
Verified live against `black-clover-g7tjy` (ep 3, `anikato:black-clover-g7tjy|3`):

- The episode resolves (site chain, byte-faithful, `27376 + N`) to MegaPlay realid
  27379; the site's own watch page embeds the same realid in its player iframe.
- That realid has several "doors" (the site's HD-1 / Vidstream-2 / Vidstream-1
  buttons collapse to one realid, different flavors):
  - `s=tcdn` -> `megap.shiora.top` -> media playlist = **66/66 TikTok ad-stub
    segments** (`p19/p16-ad-site-sign-sg.tiktokcdn.com/...image`); each one is a
    1x1 transparent PNG — zero video.
  - `s=` (bare) / `bcdn` -> `fetch.nexabloom.top` -> **66/66
    `phantomharbor.space` segments** — real video bytes.
- Without a Referer the CDN answers 403; with `Referer: https://megaplay.buzz/`
  both doors answer 200.
- **Fix shipped**: `is_ad_stub_playlist()` classifies a media playlist and
  `sources()` tries the doors in site order, keeping the first that serves real
  video; all-stub -> honest "no stream" (a stub is never handed to the player).
  Adjacent: the `mbedtls_ssl_handshake returned -0x7280` in the player log was
  mpv's TLS against the shiora door.

Open item: owner side-by-side for ep 3 (app vs the in-app browser). If the
nexabloom/phantomharbor content differs from the site's own player, the next
lever is capturing the iframe's real network call (performance resource log).

### AnimeOut: episodes list works; art and files are walled
- Search + episode lists work.
- **No banners anywhere**: every `wp-content/uploads/...` image 403s (its host
  hotlink-blocks the renderer); the Phase 3 image-route decision covers it.
- Playback: the solver opens a **legit Cloudflare challenge**; after it is
  cleared the file host answers a plain **nginx 403** — files are unplayable
  today. The desktop solver now fails fast with
  `Verification not-a-challenge (403 Forbidden)` instead of sitting 120 s.

## 2026-10-15 — Phase 3 closes the three items above

### 1. Images: closed by the loopback `/image` route
The HLS proxy gained `GET /image?url=<b64>&referer=<b64>`: primp-chrome
upstream fetch, content-type forward (non-image → octet-stream), 8 MB cap,
900 s / 128-entry memory cache, and `Access-Control-Allow-Origin: *` — the
header the web renderer needs. The display decision (`image_url()`) lives at
the display edge: **web wraps every image** (CORS); native wraps only
guarded hosts; `data:` URIs (animepahe's) pass through. Provider data and
everything persisted stay raw, so no store row can ever carry a loopback
port.

Host probe (live, 2026-10-15, primp chrome): `cdn.anipixcdn.co` and
`kayoanime.com/wp-content` all answer **200 both
bare and with their referer**; `www.animeout.xyz/wp-content` answers a
Cloudflare **"Just a moment" 403 either way** — same wall family as its
files, which is why its host is the first member of `GUARDED_IMAGE_HOSTS`.
AnimeOut's artwork therefore improves only when that wall does; the route is
the one place its clearance (or a future solve) can be attached.

### 2. "0 episodes": closed — absent counts stay absent
No card ever printed `0` in the current UI (the search row shows no count at
all); the honest-counts sweep found and fixed the two real leaks:
- AnimeOut's `Episodes: N` now parses from `excerpt.rendered` (probe: 220 /
  24 / 4 / 1 on regular and ongoing posts; empty/absent on mega-posts → stays
  0 and renders nothing).
- The quality/choice labels no longer print `0p` (AniKato's master-only
  sources are 0 by design), and the series-download dialog says "No episodes
  in this range" instead of "0 episodes".

### 3. 170 episodes at once: closed — 24 per page
The protocol's `episodes(session, page)` is honored by all five providers
now: anikato/animeout/kayoanime slice their cached full list at
`EPISODES_PER_PAGE = 24` (ktv-player's documented `PAGE_SIZE`; nkiri-tv
renders everything and its pager is vestigial — studied on disk), animepahe
keeps its server pages. The existing pager (Prev · Page N · Next) drives it.
The lookups that need the whole list (title failover, the new-episode
checker) walk pages via `base.all_episodes` — page 1 would otherwise cap
them at 24 and misreport the newest episode.

### The owner's matrix run (the live acceptance sweep)
Run it per backend after this lands; each row is a different app:

| Screen | What to check |
|---|---|
| Home / latest | Grid matches the art shape (landscape/portrait); artwork loads; no "Episode 0" |
| Search | Results grid + art; suggestions; pager |
| Detail | Backdrop/poster load; metadata row shows a count only when the source publishes one; episodes page 24 with Prev/Next (Next disabled on the last page); no "0p" in any label |
| Play | One rendition → straight into the player (no dialog); 2+ → the dialog shows distinct rows only; subtitles/quality chips appear when the stream has them |
| Downloads | Single rendition starts without a dialog; the kayoanime download saves the real filename (usercontent route) |
| Discover | Only on sources that browse (Phase 2 rule); art + pager |
| Specials | Schedule appears only on anikato (Phase 2 rule) |

Parked during this sweep: re-observe the AniKato content question (app vs
the site's own iframe) — the next lever if it still differs is capturing the
iframe's own network call (browser resource log).

## 2026-10-16 — the owner's live run: pahe's wall, AnimeOut's real posters, Discover, keyboard

### AnimeOut artwork: /staff/img IS the poster (closed)
The wallet of `featured_media` posters lives on `wp-content/uploads`,
which Cloudflare challenges for every programmatic client (403
`cf-mitigated: challenge`; Jetpack's i0.wp.com proxy cannot fetch it
either). The same cover is embedded in every post body as
`http://www.animeout.xyz/staff/img/{id}.jpg` — **served 200 with no
challenge** (primp chrome, no cookies needed; 71/72 posts across four
catalogue pages carry one, all tested URLs 200, image/jpeg). The provider
now extracts that first `<img src>` from `content.rendered` (https-
normalized) and asks the media library only for the rare post whose body
has none — whose URL is the walled one, honestly dark.

### AnimePahe's Cloudflare: why the solve "succeeded" and still 403'd
Diagnosis with the desktop stack (2026-10-16):
- A fresh WebView2 (ephemeral profile) navigating `animepahe.pw` **or**
  `/api` sits on "Performing security verification" past 30 s — the
  interstitial never redirects; only `cf_clearance` appears in the jar.
- The old solver's completion test required the site's own cookies
  (`animepahe_session`/`serverid`/`xsrf-token`/`latest`) or a title that
  names the site. The 2026-10-15 generalization dropped both, so an EMPTY
  title (read racing a navigation) counted as success — the app persisted
  a clearance from an unfinished challenge, and every retry 403'd. The
  log signature: `Cookie jar has 1 entries … Returning verified
  cf_clearance` immediately followed by the same "Just a moment…" 403.
- primp cannot replay even a valid clearance on this host (all
  impersonations, with the solving UA and without): the site's rule
  rejects programmatic clients beyond the cookie. The browser itself is
  the only client that passes today, and on Android's long-lived WebView
  profile it does (the owner's phone) while a throwaway desktop profile
  loops.
Fixes shipped: positive completion signals restored (target cookies /
site title / plain nginx landing), empty title is NEVER complete, the
`get_cookies() -> None` poll race guarded, and the desktop solver now
keeps a **persistent WebView2 profile** under `FLET_APP_STORAGE_DATA`
(trust accumulates instead of resetting every run). The solver gate
(`solve_allowed`) opens for a resolved/pinned AnimePahe, Verify, and
play — the 1.0.9 behavior — and switching away closes it.

### Discover was empty until a chip was tapped (closed)
`load_discover_filters()` reset the grid and left it empty; the first
page now loads immediately with no selections.

### AniKato's Discover filters never filtered (closed)
The site's filter form posts `genre[]=<id>`, `term_type[]=<Type>`,
`status[]=<slug>`, `season[]=<season>`; the provider sent
`genre=action&type=tv`, which the endpoint ignores — every filter tap
returned the unfiltered grid. Options are now parsed from the `/filter`
form itself (53 genres with numeric ids, 8 types, 3 statuses, 4 seasons,
plus sort and ep_min), and browse encodes the real form names.

### Player keyboard controls (closed)
Parity with the house player: Space/k/MediaPlayPause toggles play-pause,
Left/Right (and j/l) seek ±10 s, Up/Down adjust volume, m mutes,
f toggles fullscreen, [ ]/p/n change episodes, < > cycle speed, 0–9 jump
to 0–90 %, s skips the active intro/outro window. focus_scope forwards
every non-Back key to the player's handler.

## 2026-10-16 (later) — one header everywhere, downloads UX, artwork fill, About

- **Shared header** (`components/app_header.py`, Sherlock's pattern): the
  source pill, badge, version pill, screen actions and theme cycle render
  on Home, Search, Discover, Downloads and Settings; the action group is a
  `Row(scroll=AUTO)` (scroll, never clip).
- **Downloads**: series cards collapse (most recently updated open by
  default); the header shows a live aggregate ("3/11 done · 42%") over the
  per-episode bars; only the open series renders its rows.
- **Search**: a Type chip row refines the page the source just returned
  (client-side; only types actually present; hidden when the source's rows
  carry none).
- **Artwork fill**: the probe's real ratio is now authoritative in
  `card_media` — within 25% of the cell COVER fills it (no empty space);
  a genuinely different shape keeps the frosted fill.
- **About this release**: AniKato/AnimePahe synopses now reach the header
  on every open (one-shot off-path enrichment from the provider's own
  detail record when the fast path left it empty); AnimeOut/KayoAnime
  descriptions come from the post body via `core.html_extract.plain_summary`
  (the HTML episodes() already downloads). Four-line clamp + Read more.
  Comment threads stay out (AniKato's is per-episode and read-only).
- Verified live: `m=links` is a retired endpoint (the play page never calls
  it; every parameter shape answers "not enough arguments") — the play page
  is primary, the JSON route a debug-level last resort. A 30-image burst
  tripped Cloudflare's load detector ("too_many_data_frames") and surfaced
  as unhandled page errors — now capped at 4 concurrent, failures fall back
  to the card's own artwork panel.

## 2026-10-16 (the owner's follow-up run) — the CF condition, the header back, the theme

### The solver condition (the owner's exact report, closed)
"I selected an animepahe recent. It swapped in the header nicely but no
Cloudflare solver and no episode found." The log showed the episodes API
answering 403 "Just a moment…" with `solve suppressed: no user action
requested it` on every call, and the screen reading "No episodes found".

- **A challenge is now a SIGNAL, not an empty catalogue**:
  `services/providers/base.CloudflareBlocked`, raised by the pahe provider
  on a 403/503 non-JSON answer, passed through the router WITHOUT tripping
  its breaker (counting it turned the next retry into "no provider
  available (all circuits open)") and without failing over (another
  provider cannot answer for pahe's sessions).
- **User-driven loads open the verification window for their duration**:
  `AppController._user_action()` — ref-counted so the detail screen's
  resolve and episode fetch cannot close the gate on each other — wraps
  home/switching, opening an anime, search, Verify and play. Background
  work (probes, the episode checker) still cannot pop a window.
- **A blocked episodes load raises the gate**: `cf_blocked` + the SHARED
  SHIELD card (Verify · Change source — `offline_state.cf_gate_card`,
  one builder for Home's scrim and the detail screen's inline card, so
  the two cannot drift); switching away clears the gate.
- **Live evidence**: with the solver allowed, the same session's fetch
  reaches `solve()` (it used to be suppressed); with `state.page` absent
  in a headless probe the solve itself cannot run by design.
- **Known external wall (unchanged)**: the WebView2 clearance cannot be
  replayed by primp on this host ("Sorry, you have been blocked" after
  repeated automated attempts — the owner's IP was VPN-blocked mid-run,
  then restored). The next lever is a real interactive solve from a clean
  client, not more retries; the app now fails honestly (Verify card)
  instead of pretending the catalogue is empty.

### Header: the back button lives IN the header
"the back button with title anime is ahead of the header… integrate the
back button in the header, the header should always be top. Remove 'Anime'."
The shell's separate `_detail_appbar` (back + "Anime") is deleted;
`app_header(on_back=…)` renders a round tinted disc as the leading control
of the shared header, and the detail screen passes `controller.back()`.
The "Episodes" subtitle duplicates the page's own title and is dropped.

### The theme cycle (the "change color mode" error, closed)
`RuntimeError: Frozen controls cannot be updated.` at
`theme_action.content.icon = icon` — the cycle mutated a control inside a
frozen `@ft.component` subtree (the old `suppress(Exception)` around it hid
the same bug in one build and crashed loudly in another). The icon now
lands through the observable `state.theme_mode` (set by the cycle, read by
`theme_icon_for`), so a normal re-render paints it — verified in a real
Flet render context (dark → light → system, icon follows).

## 2026-10-16 (night) — the download engine, reproduced locally per backend

Owner's evidence: finished episodes read ~500 KB on disk; the downloads
screen sat at "0/2 done · 0%" over finished files. Reproduction harness:
`tools/download_matrix.py` runs the app's OWN pipeline (router → provider →
sources → DownloadManager) per backend into a scratch store.

### The corruption bug (root cause of every 500 KB "download")
`_download_file` opened the part file with mode `"wb"` — TRUNCATE — on
EVERY chunk, dispatching each write through `anyio.to_thread.run_sync`,
which is a THREAD POOL: concurrent writers truncated one another. Proven
in isolation: 273 chunks / 950,904 bytes streamed, 632 garbage bytes on
disk (`f13efffe…`), while the same URL fetched 950,904 correct bytes
through the plain client in the same process. Fixed: ONE handle per file,
writes serialized on it, closed synchronously in `finally` (a thread-pool
close can be cancelled away and leaves a Windows file lock).

### An error page is never a segment
An expired signed URL answers an HTML error page with a 200 body; the old
engine saved those pages as `.jpg` segments and reported "complete". The
first chunk is now rejected (`html`/`doctype`/`head`) and raises into the
worker's retry-with-cap path, so a dead source FAILS honestly.

### The UI never saw progress (three leaks)
- HLS jobs published `state="queued"` for the whole run (only the direct
  path declared `"downloading"`), so the row showed "Waiting…" and no bar.
- `_on_download_finished` only notified the tray; `state.downloads` kept
  the stale `"partial"` rows, so the card counted 0/2 over finished files.
- The flusher could resurrect a finished job's row from a late callback.

### The live matrix (post-fix, from this machine)
| Backend | Discovery | Sources | Result on disk | Verdict |
|---|---|---|---|---|
| AniKato | Black Clover, 170 eps | fetch.nexabloom master → index | 325 segments, **253.9 MB, MPEG-TS** | REAL |
| KayoAnime | Black Clover S2 | Drive usercontent | **847.2 MB, Matroska (.mkv)** | REAL |
| AnimeOut | catalogue OK | none | — | parked: file host is Cloudflare-walled |
| AnimePahe | Cloudflare wall | — | — | walled this run; fails through the new gate |

### AnimePahe's wall (state as of this run)
Its catalogue answered 403 "Just a moment…" to every programmatic client;
the stored clearance was expired, and a VPN detour got the address
hard-blocked ("Sorry, you have been blocked") mid-session. The desktop
solver now ASKS THE API whether the captured clearance works (`/api?m=airing`)
before emitting success — a stale cookie can no longer be persisted and
looped. The Android WebView path (the owner's phone) remains the place its
clearance works; desktop retries must be earned by that verification.

## 2026-10-17 — Independent Tri-Audit & Discover Crash Resolution

### 1. Discover Screen Crash (`on_change` vs `on_select`)
Owner report: Discover screen would not open after recent changes; app session terminated.
- **Root cause:** Flet 1.0.4 replaced the old 0.x `on_change` callback on `ft.Dropdown` with `on_select` (and `on_text_change`). Passing `on_change` raised `TypeError: Dropdown.__init__() got an unexpected keyword argument 'on_change'`, crashing the session.
- **Fix:** Switched callback to `on_select=lambda e, k=key: on_pick(k, e.control.value or "")`. Verified via headless Renderer execution across AnimeOut, AniKato, and KayoAnime filter sets.

### 2. Tri-Audit Results
Three independent agents were dispatched to review all code from this session:

- **Agent 1: API Truth (Installed `.venv` as sole source of truth)**
  - Examined all Flet 1.0.4, primp 2.0.1, anyio 4.15, and flet-yandex-ads 0.1.0 usage.
  - 1 flagged item: primp `headers.get(...)` casing suspicion. Refuted by live probe: primp 2.0.1 normalizes all incoming header keys to lowercase (`content-disposition`, `content-length`, etc.). Code lookups are already lowercase and verified correct.

- **Agent 2: Requirements Compliance (13 Requirements Checklist)**
  - All 13 core requirements passed (nav bar on detail, SafeArea, Discover card sizing, dropdown filters, ad breaks every 12, KTV home order, 3 settings banners, phone detail banner-first, header back button, honest download progress, interstitial interval, production ad IDs, clean tests).
  - 5 defects identified and resolved:
    1. Duplicate synopsis on compact detail layout (rendered both inside `compact_body` and after hero). Fixed: rendered exactly once after hero.
    2. Negative offset on compact poster (`bottom=-32`). Fixed: replaced with honest Stack height padding.
    3. Offline banner stacked above header on Home. Fixed: positioned beneath header.
    4. Fragile forward reference in Settings (`controller_ref` read before assignment). Fixed: hoisted assignment.
    5. Dead `"__none__"` check in Search filter chips. Fixed: removed dead condition.

- **Agent 3: House Pattern Alignment**
  - Banner glass styling updated to `adaptive_glass_bg(page)` / `adaptive_glass_border(page)` with `BORDER_RADIUS_LG` tokens (eliminating white-tint box in dark mode).
  - Settings screen headers and rows aligned with Sherlock standards (`core.tokens` spacing, uppercase section headers, subtle inter-row dividers, and centered version footer).
  - Card focus interaction: dropped imperative `animate_scale` and `attach_focus_zoom` mutations (preventing `RuntimeError: Frozen controls cannot be updated` on frozen component subtrees), relying on declarative `card_button_style` FOCUSED borders.

### 3. Build Workflow Optimization
- Solved the 37-minute build time by introducing caching (`~/.cache/uv`, `~/flutter`, `~/.flet/cache`, `~/.gradle`).
- Replaced second `flet build` pass with direct `./gradlew assembleRelease -Psplit-per-abi=true` (plus universal assemble).
- Unified split and universal builds into one job; removed redundant 45-minute retry loops.
- Added concurrency cancel-in-progress to avoid superseded queue backups.





## 2026-10-19 — the nav dead-end, the DVD filter, one grid contract

Three reports from a live run, all reproduced and closed with evidence.

### 1. The nav bar dead-end (only this app had it)
"I can be in a screen and click something in navigation and I can't leave...
if I'm in an anime detail screen and I press downloads, I can't go to
downloads unless I use the back button."

**Root cause:** in `app_shell.py` the body is gated on `active_view` FIRST
(`if active_view == "anime": body = AnimeDetailScreen()`), and `_on_tab`
only called `set_active_tab(name)`. A tab tap therefore set the tab but
left the view on "anime" — the body never changed. Nothing in the house
apps has this shape (KTV/Sherlock/DDGS all put tab state above view state
or reset the view on pick).
**Fix:** `_on_tab` also calls `set_active_view("tabs")`; test
`test_picking_a_tab_leaves_the_detail_view` pins both halves.

### 2. The Discover filters (the "numbering is false" report)
"I'm currently seeing DVD 2, but then I open DVD and there are more than
that... Maybe they're not updating."

**Verified live** (AnimeOut WP categories, 2026-10-19): the counts ARE the
site's own — DVD=2, Manga=1, Announcement=13, Uncategorized=0 — so the
labels are honest, never hallucinated.
**The real bug:** `_pick` sent the dropdown's value as a STRING, and
`animeout.browse` does `",".join(str(c) for c in categories)` — which
iterates a string's CHARACTERS. Picking DVD (14893) requested
`categories=1,4,8,9,3`: five unrelated categories, hence "more than that".
**Fixed on both sides:** the screen shapes multi-valued keys into the
protocol's list (`_LIST_VALUED_KEYS`), and the provider coerces either
shape. Live proof: `browse({"categories": "14893"})` now returns exactly
the site's two DVD titles, and the regression tests cover both layers.

### 3. One grid contract (Home was the last outlier)
"Why are you even hardcoding them individually? I expected it to be
something that you fix once and it's solved everywhere."

`core/tokens.py` now owns `GRID_COL` (`{"xs": 6, "sm": 4, "md": 3, "lg": 2,
"xl": 2}`) plus `GRID_SPACING`/`GRID_RUN_SPACING`; `ad_breaks` defaults to
those tokens, and Home/Discover/Search/detail all read `col=GRID_COL`.
Home's old `xs:12` (one giant card per row on a phone) is gone.
`test_no_screen_owns_its_own_grid_spans` fails if any screen hardcodes a
span again.

### 4. Detail title scales with the viewport
A fixed 22px title read oversized on a narrow phone. The hero title now
steps 16 → 18 → 24 with the measured width (FONT_LG/XL/XXL).

## 2026-10-19 (later) — the tri-audit, and the AniKato "kwik" download chain

### 5. The tri-audit (three independent agents, the plan's Part 2)

Three read-only agents audited this session's change set against the
installed `.venv` (the install wins over every doc), the owner's
requirement list, and the house apps' own source. Their findings, and what
was done with each:

| # | Finding | Fixed |
|---|---|---|
| 1 | **AniKato's genre/type/status/season filters were DEAD** — the screen wrapped them in a list the site's form never wants, so the request became `genre[]=%5B%271%27%5D` and the grid came back empty. A regression introduced the same day. | The multi-valued keys now come from the PROVIDER's spec (`"multi": True`), and AniKato's `browse` accepts a list or a string and encodes lists as REPEATED array params (`genre[]=1&genre[]=2`). |
| 2 | The Sort dropdown SHOWED "Recently updated" while the request carried no `orderby` at all — WordPress fell back to publish date. The owner's "the numbering… does not update". | The screen sends the spec's own first option (`_effective_selections`), and the provider defaults `orderby` to the same value. |
| 3 | The sort-direction arrow flipped on AniKato, whose form has NO order parameter — a control that changed nothing. | The spec declares `"direction": True` where the source has one (the WordPress sources); AniKato declares none, so no arrow is drawn. |
| 4 | Every header control (back disc, theme cycle, version pill, badge) was an `ft.Container` — and flet 1.0.4 gives a Container **no focus state** (28 control classes expose `on_focus`/`on_blur`; Container is not one), so a TV remote could never reach them. | All of them are Button-family controls now (`IconButton`/`TextButton`) with the house chip look and a PRIMARY focus ring. This is BETTER than the house apps, which use Containers (they are phone-first; this app is not). |
| 5 | The up-to-date dialog clipped ~60 % of the bundled changelog (1128 characters of plain `ft.Text` in a FIXED 340x220 box, painting over the buttons). | The house shape (Sherlock/DDGS/KTV all build it this way): the notes are `ft.Markdown` in a SCROLLABLE column. |
| 6 | The up-to-date dialog popped the topmost dialog UNCONDITIONALLY — it ate a SnackBar standing above it and orphaned the dialog itself. | The dismissal goes through the app's own registry (`close_app_dialog`, which pops only if that dialog is topmost), and the double-pop on `on_dismiss` is gone. |
| 7 | A category count the site never published was printed as "(0)". | `label_with_count` in `providers/base.py`: a missing count prints nothing. |
| 8 | One failing segment could be retried **18 times** (the cap was per worker; a requeued segment lands on any worker) and the backoff slept while holding a GLOBAL cross-job permit. | The attempt counter is shared by the job's workers, and the permit is taken per FETCH. |
| 9 | The compact detail poster sat at the TOP of the cover (only `right` was set, so Flutter aligned it topStart) instead of the bottom band. | Both insets (`right` + `bottom`), so it is a fully positioned Stack child. |
| 10 | The layout read the window WIDTH at render time and never re-evaluated — flet exposes `page.on_resize`, and the app never registered it. | `page.on_resize` bumps `state.viewport_version`, which the header and the detail screen read. |
| 11 | Dead code (`_ORDER_OPTIONS`, `on_theme`, `_launch`), stale `tokens.__all__`, `Anime.score` typed `float` while Kayoanime assigns `None`, an empty star slot left in the card, "Discover" printed twice, the new `changelog.py` untracked while shipped code imports it. | All closed; `changelog.py` is tracked. |
| 12 | Two dep docs contradicted the installed packages (`ft.Icons` is 8825 members, not 95; primp 2.0.1 RAISES `BuilderError` on an invalid impersonation instead of warning). | Both docs corrected. |

**Suite: 606 passing under `-W error`, ruff clean.** The audit's own
"no API-signature crash in the diff" verdict stands: the one crash-class
risk it found was the untracked `core/changelog.py` (fixed by tracking
it).

### 6. AniKato's download part IS animepahe's — the kwik chain, proven

The owner's question: *check if you can see the download part kwik, and
whether it is the same with animepahe, to know if it is something we can
wire.* Reproduced with the app's own anime (Black Clover, `anime_id`
2121, `black-clover-g7tjy`, 170 episodes) and the site's own endpoints.

**The chain, hop by hop (every hop fetched and read):**

```
1. GET /ajax/episode/list/2121            -> data-mal=34572, data-slug=1,
                                               data-timestamp=1778012242
2. GET https://mapper.nekostream.site/api/mal/34572/1/1778012242
   (the site's OWN script, anikoto/js/mapper.js — not ours) ->
   {"Kiwi":{"sub":{"download":{
        "360p":"https://pahe.nekostream.site/yRVMl",
        "720p":"https://pahe.nekostream.site/BfqIe",
        "1080p":"https://pahe.nekostream.site/WjUUW"}}}}}
3. GET pahe.nekostream.site/{code}          -> 200, an HTML page whose JS
                                               hands over to testpahe...
4. GET testpahe.nekostream.site/{code}      -> 302 Location: https://kwik.cx/f/{token}
                                               (needs Referer: pahe.nekostream.site)
5. GET https://kwik.cx/f/{token}            -> Cloudflare managed challenge
                                               (cf-mitigated: challenge) —
                                               CLEARED in a real browser
6. the kwik file page                       -> "AnimePahe_Black_Clover_-_001_360p_SubsPlease.mp4"
                                               MIME video/mp4, 52.82 MB, 636x360,
                                               23.976 fps, MD5 fb46aa5dfc8bc1ea0ed7aa984c1ed86b,
                                               uploaded 2021-04-12
7. the download itself                      -> a CSRF'd POST to https://kwik.cx/d/{token}
```

**"Kiwi" IS animepahe.** The mapper's own normalizer is the proof:
`kiwi-stream` -> `animepahe` -> the display label `Kiwi-Stream`. The file
it returns is an AnimePahe file (SubsPlease, 2021). **AniKato's download
part is not AniKato's at all** — the site borrows AnimePahe's files
through a third-party mapper, exactly as the owner suspected.

**The mapper is MAL-keyed and source-agnostic** (verified live):
`mal=34572` (Black Clover) -> 3 links; `mal=21` (One Piece — a series
AniKato does not even list) -> 2 links; the timestamp is not validated;
`mal=154587` (Frieren) -> `400 Failed to get the list` (not in its
database). So it is a **universal AnimePahe download resolver** keyed by
MAL id, and any provider that exposes a MAL id can use it.

**The kwik host family today** (2026-10-19, live): `kwik.cx` is the only
live one ("Kwik: Just Another Video Hosting Service"); **`kwik.si` is a
parked domain** (a microloan spam page — it 200s every path, so a stale
`kwik.si` reference would silently "succeed" with a parking page);
`kwik.pw`, `kwik.to`, `kwik.la`, `kwik.icu` are DNS-dead; `kwik.link`
and `kwik.one` are unrelated sites (404 on `/f/`).

**What it means for the app — wireable, with one caveat.**
- The mapper API is open: no auth, no Cloudflare, no token. Per-quality
  download links for ANY series in its database come from one GET.
- The last hop needs a Cloudflare clearance on `kwik.cx`. The clearance
  cookie is HttpOnly, so it cannot be lifted out of the browser — it has
  to be EARNED by a real browser. That is the mechanism the app already
  ships (the WebView solver) for AnimePahe; here it is a different HOST,
  not a different mechanism. On the owner's phone (Android WebView) that
  is where it would work; on desktop it needs a solve.
- Our existing `services/kwik_resolver.py` resolves the kwik PAGE to an
  m3u8 (streaming). The `/f/` file route is a DIFFERENT path (a CSRF'd
  POST to `/d/{token}`), so wiring it is a small new step — not a
  rewrite — and it would give AniKato a DIRECT, per-quality file
  download (360/720/1080) instead of the HLS segments it assembles today.
- **Not decided here.** This is a report; the wiring is a phase. The
  open questions for that phase: whether the app may borrow a third
  party's mapper API at all (it is AnimePahe's files reached through a
  third party, and the owner asked whether the kwik shortlinks are the
  same as AnimePahe's own — they are, but the mapper is nekostream's),
  and whether the per-quality direct file is worth the extra Cloudflare
  surface when the HLS download already produces a verified file on disk
  (AniKato 253.9 MB MPEG-TS, Kayoanime 847.2 MB MKV).
