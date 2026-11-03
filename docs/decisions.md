# Phase 0 — Verified base & architecture decisions (AnimePahe TV 2.0)

Date: 2026-10-11. All probes run from this machine, read-only. No app code was written
before these gates resolved. Master plan: the 0.85.3 multi-backend rewrite (approved).

## Gate results

| # | Gate | Result |
|---|---|---|
| 1 | flet 0.85.3 + flet-video 0.85.3 install/import | **PASS** — ephemeral venv, clean install; `flet_video` exports `Video`, `VideoMedia`, `VideoConfiguration`, `VideoSubtitleConfiguration/Track`, full controls set |
| 2 | AnimeOut file chain end-to-end | **FAIL for direct streaming** — chain fully mapped (below); final host is Cloudflare-challenged |
| 3 | AniList / TVMaze / animeout wp-json re-probe | **PASS** — all answer from this machine (Frieren: AniList id 154587; TVMaze show 69956; animeout posts with `featured_media`) |
| 4 | AnimeOut coverage, 10 mainstream titles | **PASS 9/10** — post + per-episode MKV anchors + poster; WP search is fuzzy (needs title-relevance filter) |
| 5 | flet-yandex-ads 0.85.3 build | **REMOVED per owner** — the package is the owner's own extension; it ships on 0.85.3 as instructed, no gate. Ads wire in as today (`try/except` + `_HAS_ADS`) |

## Gate 2 detail — the AnimeOut chain (mapped hop by hop)

```
WP post content.rendered
  → http://nimbus.animeout.com/series/.../[AnimeOut] Title - EP [hash][1080pp][SubsPlease][x265][RapidBot].mkv
  → 301 → https nimbus
  → 302 → http://ddl.animeout.com/index.php?url=<file url>     (200, 5.7KB, no CF)
  → 301 → https ddl index.php                                    (page has href="…/public.php?url=<file url>")
  → public.php?url=<file url>                                    (200, 15KB HTML, no CF)
  → inline JS: var url = "https://public.animeout.xyz/<path>.mkv"; window.location = url
  → public.animeout.xyz                                          → **403 Cloudflare "Just a moment"**
```

- `httpx` 403, `primp` (chrome TLS impersonation) 403 — a real JS challenge, not fingerprinting.
- **Verdict:** AnimeOut is an excellent *catalog* source (titles, posters, per-episode file names,
  encodes named SubsPlease/ERA-style) but its file host is walled. Its provider reports
  `capabilities: {files: False}`; the router treats it as catalog-only until/unless that changes.
- The link-page → resolve → direct-file SHAPE is the nkiri `downloadwella` pattern exactly
  (regex the `<a href>`, regex the JS `var url`) — the implementation is worth keeping for any
  source with the same shape (kusonime's page, future WP sources).

## The "many ways" inventory (every mechanism the app acquires)

The app never relies on one thing. Each provider handles its source's quirks its own way;
the router absorbs failure at any layer.

1. **nkiri way — WP REST + link-page resolve** (`services/nkiri.py`, proven in production):
   `posts?search` → `media?include=` posters → post `content.rendered` anchors → POST
   downloadwella `op=download2` → regex direct `.mkv`. Layered episode parsing
   (SxxExx → Season x Episode y → Episode N → single-movie fallback).
2. **socolive way — static JSONP + referer** (`services/football.py`, proven in production):
   pre-baked `matches_YYYYMMDD.json` / `room/{n}/detail.json`, `prefix(...)` unwrap, referer
   spoof, `asyncio.gather(return_exceptions=True)` so one bad room never kills the batch.
   m3u8 URLs directly — no resolve step.
3. **animepahe way (old app, c0d1b3a)** — `api?m=` JSON → play page → Kwik unpack → CDN
   m3u8 → **loopback HLS proxy (primp, Chrome TLS impersonation — the CDN fingerprints TLS;
   httpx gets 403 there, primp gets 200)** → ktv:// with `&title=`. The front half is
   Cloudflare-walled; the proxy machinery is worth porting for any HLS source whose CDN
   fingerprints TLS.
4. **modern JSON API way — KAA (proved today)**: MALSync maps AniList/MAL id → KAA slug →
   `GET kaa.lt/api/show/{slug}` (locales, genres, poster) → `/episodes?lang=ja-JP&page=N`
   (100 per page: per-episode **titles, durations, thumbnails**) → `/episode/{ep-N-hash}`
   (synopsis, poster, banner, `servers[]`) → server `src` player page → embedded `.m3u8`.
   Everything up to the player page answered clean with zero challenge. The player page's
   manifest call is a Vidstack/Astro client fetch — the last hop to finish mapping in Phase 1.
5. **metadata APIs — AniList GraphQL + TVMaze + MALSync** (all clean, keyless): catalog,
   covers, per-episode stills (TVMaze `/shows/{id}/episodes` → `image` for every episode),
   and AniList/MAL id → provider-slug mapping (the glue between metadata and file sources).
6. **Telegram way — `t.me/s/{channel}` public previews** (clean HTML, no login, in-channel
   `?q=` search, `?before=` backfill): discovery layer only — the web preview exposes **no
   file URLs**; actual files need MTProto (Telethon) or a bot. Catalog: per-message filenames
   (`[SubsPlease][Title][01][1080p].mkv`) — parseable. Decision deferred to a later phase
   (heavy dependency, user-account grey area).

## Architecture decisions (locked)

- **Base: flet 0.85.3** (the owner's decision — the old app's exact line, nkiri/socolive family).
  Deps: `flet==0.85.3`, `httpx`, `flet-video==0.85.3`, `flet-yandex-ads` (owner's package).
  HTML parsing: stdlib `html.parser` (nkiri's bs4 is the one extra we don't add). No primp in the
  base stack — it returns only if an HLS CDN proves to fingerprint TLS.
- **Playback: the in-app player is PRIMARY; ktv:// external is the FALLBACK.** This is the
  continuation of the current 1.0.4 app (immersive player + HLS proxy + quality/audio picker +
  position save + tap-to-close errors), **not** a return to the old app's external-only model.
  The 0.85.3 `flet-video` exposes the same shape the current player was built against
  (`VideoMedia(resource, http_headers)`, subtitle configuration, controls), so the player ports.
  flet-video 0.85.3 has no production track record in our apps (the old app declared it, never
  used it) → device verification happens before the external fallback is demoted to backup.
- **Provider protocol + router + circuit breaker**: static editorial priority, health-gated
  skip, per-provider breaker (3 fails → OPEN 30s → 1 half-open trial → exp to 5min), negative
  cache, startup parallel probe race (3–5s each, ~8–12s budget, non-blocking). Static order
  first, latency only as tie-breaker; providers never "lock" — failover is per request, because
  backends differ in coverage, not just health.
- **AnimePahe: not planned on via a Cloudflare Worker** (rejected as untested — CF-to-CF
  egress is what gets challenged; the old app's `cloudflare-worker.js` was only config/
  redirects, never an API proxy). It re-enters as one provider file only if a tested no-friction
  solver appears.
- **Store migration**: the rewrite reads the same `app-state.json` (positions, continue
  watching, downloads, search history, favorites→follows).
- **No hardcoding, no limiting**: every capability is discovered per provider at runtime;
  quality/audio lists, episode counts, and sources come from the provider payloads unmodified.

## Phase 1 (next) — what must be true when it ships

A complete 0.85.3 app: shell/views, 3-way theme with persistence, D-pad focus chain, migrated
store, provider protocol + router + breaker + startup race, first providers (KAA + AnimeOut
catalog + AniList + TVMaze), **in-app player ported (flet-video 0.85.3) with ktv:// fallback**,
Home/Search/Detail/Downloads/Settings wired to the router, and the first real tests (router
table, store migration, player spec round-trip, provider fixtures). Commits separately per
phase; boots clean with `[INFO]` at every commit.

---

# Update — the multi-backend phase (2026-10-11, later)

The 0.85.3 swap landed ON TOP of the untouched app (no rewrite); the
provider router now sits between the controller and the sources. Final
bench, each certified by live probes from this machine:

| Provider | Legs | Verdict |
|---|---|---|
| anikato (anikototv.to) | catalog + episodes + **streaming files** | COMPLETE — RC4 VRF unlocks the episode list; MegaPlay decrypts to DIRECT playable master.m3u8 with subtitle tracks + skip data. Sub + dub. |
| animeout (WordPress) | catalog + episodes + files | DDL landing chain resolves to public.animeout.xyz; solver captures clearance and sends DDL referer. |
| animepahe | catalog + episodes + streaming files | untouched; CF-walled catalog → breaker trips, files still attempted; safety net |
| kayoanime (WordPress) | catalog + episodes + streaming files | COMPLETE — WordPress catalog, Drive folders (BOX ranges / season folders), 206 ranged streaming via alt=media, keyless download route via usercontent. |

REJECTED / REMOVED as providers: kusonime (Indonesian-subbed, removed per owner), Telegram (web previews carry no file
bytes; MTProto-only), AniList/TVMaze/MALSync (metadata glue — the
owner's rule: every provider must be a whole app in its own way).

Architecture in the app: provider protocol mirroring the scraper's real
shapes; router with per-provider circuit breakers (3 fails → 30s →
half-open trial; failed trials double to a 5min cap), empty-answer
fallthrough, `force` bypass, startup probe race, pin support
(Settings → Content source), title-based cross-provider lookup
("Try another source"), per-source headers through the play path
(Source.headers), capability-gated Kwik resolve, m3u8-only proxy wrap.
