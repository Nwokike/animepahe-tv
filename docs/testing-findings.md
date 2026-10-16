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
  `Row(scroll=AUTO)` (scroll, never clip). The theme cycle repaints its own
  icon in place (a frozen subtree cannot be relied on to re-render it).
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
