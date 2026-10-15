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
