# Kusonime Backend Reference (kusonime.com)

Probed 2026-10-11. All probes read-only (GET/HEAD). Facts only; inference is marked as such.

## 1. Endpoint map (evidence)

Base: `https://kusonime.com/wp-json/wp/v2`. Standard WordPress REST (112 routes indexed at `/wp-json/`).
Probe UA header used: `Mozilla/5.0 Chrome/120.0` (full Chrome UA for leecher pages).

### Posts — catalog, search, details

| Endpoint | Evidence |
|---|---|
| `GET /posts?per_page=12&page=N&orderby=date&order=desc&_fields=id,title,featured_media,link` | 200. Latest-first catalog. `X-WP-Total: 5142`, `X-WP-TotalPages: 1029` at per_page=5. Out-of-range page returns 400 `rest_post_invalid_page_number`. |
| `GET /posts?search={q}&per_page=12&page=N&_fields=...` | 200. WP substring search, NOT relevance-ranked: `search=frieren` returns Frieren S2 first but also unrelated titles (`Tongari Boushi`, `Maou no Ore…`); `search=sakamoto days` returns the Live Action post before the anime batch. Client-side re-ranking by title match is required (provider already does this). Empty result is `[]` with 200. |
| `GET /posts?categories={id}&per_page=N` | 200, works. `categories=1879` (Anime China) → `X-WP-Total: 186` matching the category count exactly. Same filter works for tags (`?tags={id}`). |
| `GET /posts/{id}` | 200. Full field inventory: `id, slug, date, modified, link, guid (?p= stub), title, content, excerpt, categories[], tags[], featured_media, author, format, status, type, comment_status, ping_status, sticky, template, meta, class_list, yoast_head, yoast_head_json, _links`. `content.rendered` is a ~1–1.3 KB synopsis STUB — contains zero download links (verified: no pixeldrain/mega/drive/acefile/hxfile/hexload substrings). The real links live only in the HTML post page. `excerpt.rendered` ~177 chars, also link-free. |
| `GET /posts?orderby=modified&order=desc` | 200, works (recently-updated feed; reflects batch updates to airing shows). |
| `per_page` max | `per_page=100` → 200; `per_page=101` → 400 `rest_invalid_param`. Max page size is 100. |
| `?_embed=1` | Works ONLY without `_fields` restriction: `?_fields=…&_embed=1` returns empty `_embedded: {}`. Without `_fields`, `_embedded` contains `author`, `replies`, `wp:featuredmedia`, `wp:term` — `wp:featuredmedia[0].source_url` is the poster URL, so one request can replace the posts+media two-step. (Provider currently does two requests; `_embed` without `_fields` is heavier per post ~60 KB vs ~2 KB, so the two-step with `_fields` is the cheaper choice.) |
| `GET /search?search={q}` | 200. Returns `{id, title, url, type, subtype}` — works (`frieren` → post 46789 with its URL). Lighter than `/posts?search=` but no `featured_media`/poster id. Useful as a fast existence check, not as a replacement. |
| `GET /posts/{id}` slug source | `link` field = canonical HTML page URL (`https://kusonime.com/{slug}/`). Slug regex `([^/]+)` on `link` is reliable. |

### Categories (ids + names + counts) — `GET /categories?per_page=100` → 200, 8 rows, single page

| id | name | slug | count |
|---|---|---|---|
| 1 | Anime | anime | 4270 |
| 367 | Anime BD | anime-bd | 1 |
| 1879 | Anime China | anime-china | 186 |
| 374 | Anime Jadul | anime-jadul | 511 |
| 3305 | Anime Korea | anime-korea | 9 |
| 1480 | J-Drama | j-drama | 37 |
| 1474 | J-Movie | j-movie | 32 |
| 1370 | Live Action | live-action | 225 |

### Tags — `GET /tags?per_page=100&orderby=count&order=desc` → 200, `X-WP-Total: 3412`, 35 pages

Tags are franchise labels. Top by count: Doraemon (1118, 44), Pokemon (875, 39), Mobile Suit Gundam (1382, 28), Studio Ghibli (3289, 20), BanG Dream (431, 19), Digimon Adventure (520, 18), Dragon Ball Z (1138, 18), One Piece (614, 17). Tag slugs are URL-safe franchise keys (e.g. `boku-no-hero-academia`). Usable for franchise grouping / "more like this" via `?tags={id}`.

### Media (posters) — `GET /media?include={ids}&per_page=N&_fields=id,source_url` → 200

`GET /media/{id}` example (id 46790): `source_url=https://kusonime.com/wp-content/uploads/2026/02/Sousou-no-Frieren-Season-2.webp`; `media_details.sizes` keys: `1536x1536, full, large, medium, medium_large, thumb-large, thumb-medium, thumb-small, thumbnail`. Posters are `.webp`/`.jpg` under `/wp-content/uploads/`. No episode stills exist anywhere on the platform (posts have one featured image only).

### The HTML post page — the actual file layer

`GET https://kusonime.com/{slug}/` → 200 (~74–81 KB). Download section markup:

```html
<div class='dlbodz'>…<div id="dl">
  <div class="smokeddlrh"><div class="smokettlrh">Download {Title}</div>
  <div class="smokeurlrh"><strong>360P</strong> <a href="…">Google Sharer</a> | <a href="…">Google Drive</a> | … </div>
  <div class="smokeurlrh"><strong>480P</strong> … </div>
  …one .smokeurlrh block per quality…
```

- Anchor TEXT is a generic host label (`Pixeldrain`, `Google Sharer`, `Mega.nz`, …), NOT the filename. Quality comes from the `<strong>` header of the enclosing block; the true filename lives only on the host side (pixeldrain `/info` API, acefile slug, Drive API metadata).
- No `<table>` elements. Section is wrapped in `#dl` with an adblock notice (`#dl-notif`).
- `bit.ly` `Klik Disini` links (4 per page) are NOT files — they resolve to Google Play Store pages (RAR app `com.rarlab.rar`, MPV player `is.xyz.mpv`). Ignore.
- `facebook.com` / `instagram.com` links are social/report links. Ignore.

## 2. Post-type survey: batch vs per-episode vs single-video

Latest-20-posts scan: 18/20 titles contain "Batch", 2/20 are Live Action movie posts without the word (still multi-quality single-video posts, see below). Searches for `dandadan`, `one piece episode`, `jujutsu kaisen`, `frieren`, `sakamoto days`, `One Punch Man Season 3` (currently airing): every result is a batch or single-video post. **No per-episode (episode-by-episode file) posts were found anywhere.** Airing shows (OPM S3, post 46030, modified 2026-09-15) get their batch rar re-uploaded/updated in place — pixeldrain `Manusia Satu Pukulan Musim 3 {360,480,720,1080}p.rar` uploaded 2026-01-06 with recent `date_last_view`.

Two distinct file shapes exist (extension ground truth from pixeldrain `/info` `name` + acefile URL slugs):

- **Series/season posts → one `.rar` archive per quality.** The rar holds the episode range; the range is NOT always in the site-visible text. E.g. provider's `_batch_range` parses `01-16` from the filename, but current pixeldrain names are often range-less (`[Kusonime] Frieren & Pabrik Susu S2 BD 360p.rar`, `[Zen-Kuso] Manusia Satu Pukulan Musim 3 720p.rar`). The jadul post's pixeldrain ids were reused across blocks (same `UHyvG7d6` under two blocks) — treat pixeldrain id as the dedup key, not quality order. Episode ranges per post must come from the acefile slug (`…-01-15-480p-rar`), the page's textual `Episode 01-12` title fragment, or rar NAME when present — never assume from block order alone.
- **Movie / special / single-video posts → direct `.mp4` (360p) / `.mkv` (480p/720p/1080p) per quality, streamable.** Verified via pixeldrain info: `[Kusonime] Jujutsu Kaisen Execution (2025) HDCAM [360p].mp4` (195 MB), `[480p].mkv` (424 MB), `[720p].mkv` (1.1 GB), `[1080p].mkv` (1.8 GB). Acefile slugs agree (`…-hdcam-360p-mp4`, `…-480p-mkv`, …). Same pattern on the China special post (`…-special-episode-360p-mp4`, `-480p-mkv`, `-720p-mkv`, `-1080p-mkv`).

So: **not every file is an archive.** Multi-episode series = `.rar` per quality; movies/specials/single videos = `.mp4`/`.mkv` per quality. The provider's "batch archive" model is correct for series but misclassifies movies — a movie's 720p `.mkv` on pixeldrain is directly streamable and should be surfaced as a stream, not a batch download.

## 3. Full file inventory of one post (Frieren S2, id 46789)

`https://kusonime.com/frieren-s2-batch-subtitle-indonesia/` — 5 `.smokeurlrh` blocks:

| Quality | Google Sharer (acefile) | Google Drive (usercontent) | Pixeldrain (id → verified name) | Terabox | Hxfile | Mega.nz | Megaup |
|---|---|---|---|---|---|---|---|
| 360P | `…/112193601/…-bd-360p-rar` | `id=1RQRTudoGwebDHBBH82gUFOO0YoFu4_Jv` | KdRTpxHE → `[Kusonime] Frieren & Pabrik Susu S2 BD 360p.rar` (595 MB) | same `/s/1dkwMtGy…` shared link all qualities | os8twzbbtnxq | `file/5FYynYqb#…` | `megaup.net/ec9be2e4…/` |
| 480P | `…/112193602/…-bd-480p-rar` | `id=1DUO4HdgzJpDfS25TWoHZC6d-dkwoR2j_` | JBvz5r9R → `…BD 480p.rar` (1.24 GB) | same | bqmhewi8suxu | `file/8BpW1QgK#…` | `…/5201d859…/` |
| 720P | `…/112193603/…-bd-720p-rar` | `id=1xm1bs3CbhlETVMPKSFICj6TW_x8bf7DQ` | DHsVJF9v → `…BD 720p.rar` (5.05 GB) | same | 8i5he34jp05r | `file/tZw0gZxR#…` | `…/4ff685ae…/` |
| 1080P | `…/112193604/…-bd-1080p-rar` | `id=1AOx9hW6LM4zRPYPMj-ntUbkWrsDNruRs` | eoej7F88 → `…BD 1080p.rar` (6.44 GB) | same (1080P block has NO hxfile link) | — | `file/NNIljLYS#…` | `…/71b2792601…/` |
| Subtitle | `…/112193605/…-bd-fontsubs-rar` | — | — | — | — | — | — |

Host variance across the other 6 sampled posts: old-BD adds `fileditchfiles.st` links (no megaup); dandadan-S2 uses `krakenfiles.com/view/…` (all 4 now 404 `File not found`) instead of hxfile; sakamoto-live (no pixeldrain at all) uses `akirabox.com/{id}/file` (redirects to `akirabox.to`, returns 404 page) + megaup; movie/china posts add `mir.cr/{CODE}` (→ `mirrored.to/files/{CODE}`, exact video filename in `<title>`, links JS-gated). No `hexload.com` or `drive.google.com/drive/folders/` links found on any sampled page (`search=hexload` → `[]`; zero folder-link matches on tanmoshi page). Older posts use `drive.google.com/uc?export=download&id=` form; newer posts use `drive.usercontent.google.com/download?id=…&export=download&authuser=0` — same file, both redirect/serve identically.

## 4. Host-by-host streaming capability matrix (probe evidence per host)

| Host | Page/flow | Direct file? | Range/stream? | Verdict |
|---|---|---|---|---|
| **pixeldrain.com** `/u/{id}` → `/api/file/{id}` | None (direct). Read-only `GET /api/file/{id}/info` returns exact `name`, `size`, `mime_type`, `sha256`. | Yes | **206** `accept-ranges: bytes`, `content-range: bytes 0-1023/5045202435` on the 5 GB 720p rar; `content-disposition: inline; filename="…720p.rar"`. | Direct download AND range-streaming verified. `.mkv`/`.mp4` singles are streamable as-is; `.rar` is byte-servable but not playable. |
| **Google Drive** (`drive.usercontent…/download?id=&export=download`, `drive.google.com/uc?…` form) | Virus-scan interstitial for files >~100 MB (`Google Drive can't scan this file`, 2.5 KB HTML). Confirm form: `GET /download` with `id + export=download + confirm=t + uuid` (uuid scraped from form). | Yes, after confirm | **206** `accept-ranges: bytes` after `confirm=t` (full 530,143,710-byte rar served `application/octet-stream` with `attachment` disposition; Range → 206 + `content-range: bytes 0-1023/530143710`). Drive API v3 metadata also works read-only (`files/{id}?key=…` → 200 with `name, mimeType: application/rar, size`). | Direct + range-capable behind one confirm GET. Same byte-servability caveat: rar content isn't playable, but movie `.mkv` Drive links would stream. |
| **acefile.co** `/f/{id}/{slug}` | **404 → /e404 for all 6 URL variants tested** (with slug, bare id, trailing slash, old + new file ids, two UAs) from this network. | Unknown | Unknown | UNVERIFIED — likely geo/host-blocking of this probe network (hxfile on similar infra loads fine) or dead links. Slug always ends `-{quality}p-{rar,mp4,mkv}` so extension is at least inferable without fetching. (INFERENCE: XFS-style `op=download2` leecher; not probed further — GET-only constraint plus 404.) |
| **hxfile.co** `/{id}` (→ `/{id}.html`) | 200, XFS-style: `<form name="F1" method="POST">` with `op=download2`, `id`, `rand` token + countdown + g-recaptcha. | No (POST + captcha gate; not traversed — read-only constraint) | Unknown | Leecher gate. Direct URL not obtainable with GET-only probes; no range evidence. |
| **hexload.com** | Root `/` → 200 (domain alive, ~102 KB). Zero kusonime links reference it. | N/A | N/A | Not in use on sampled posts. No evidence either way. |
| **mega.nz** `/file/{id}#{key}` | Landing page 200 (`567.41 MB file on MEGA` in `<title>`, key stays in fragment, never sent to server). Public API `g.api.mega.co.nz/cs` with `{"a":"f","p":id}` (no key) → `[-15]` (blocked/expired — needs the `#key` handled client-side per MEGA API). | No (without key handling + MEGA's encrypted-chunk protocol) | No | NOT streamable via plain HTTP ranges. Requires MEGA-protocol client (fetch nodes with key, download AES-CTR chunks, decrypt). Out of scope for a range-based streamer. |
| **1024terabox.com** `/s/{share}` | Share URL redirects to `1024tera.com/sharing/link`; API returns `{"errno":400141,"errmsg":"need verify"}`. | No | No | Login/captcha-walled. Not usable. (Same single share link reused for all qualities on a post — it's a folder share, not per-file.) |
| **megaup.net** `/{hash}/` | Tested hash → **404 `Error - MegaUp`** page (745 KB). Other hashes untested. | Unknown | Unknown | Appears expired/dead for the tested file; host may rotate. No range evidence. |
| **krakenfiles.com** `/view/{id}/file.html` | All 4 dandadan links → **404 `File not found`**. | No (dead) | No | Dead on sampled post. Ignore. |
| **fileditchfiles.st** `/beta…/{hash}/{name}` | 200 but serves a **browser-verification challenge** (`Verifying your browser…` + obfuscated POST form, no anchors/video/sources). | No (challenge gate) | No | Challenge-walled. Not usable with plain HTTP. |
| **akirabox.com** `/{id}/file` | Redirects to `akirabox.to`, returns 404 page (26 KB Next.js shell). | No (dead) | No | Dead on sampled post. Ignore. |
| **mir.cr** `/{CODE}` → `mirrored.to/files/{CODE}` | 200, correct video filename in `<title>` (`[Kusonime]_Jujutsu_Kaisen_Execution_(2025)_HDCAM_[360p].mp4`), but all outbound host links are JS-rendered (19 static links are all site nav). | No (via GET) | Unknown | Mirror index only; real links need JS or mirrored.to API. Not usable read-only. |

Streamability summary: only **pixeldrain** (direct, no gate) and **Google Drive** (one confirm GET) serve bytes with `206` + `accept-ranges`. Everything else is captcha/JS/login/challenge-gated, MEGA-protocol, or dead. And ranges only matter for playable containers: movie/special `.mp4`/`.mkv` singles can stream; series `.rar` batches cannot (they must be downloaded whole and extracted — the episode inside a batch is fetched by the downloader, as the provider docstring states).

## 5. Full-experience checklist

### Delivers today (current provider)

- Discovery: latest catalog (`orderby=date`), full-text search with client-side title re-ranking, details (`anime()`), posters via `/media`.
- Episodes: synthesized episode list from batch-rar ranges (works where the range is in the filename; fragile where pixeldrain names are range-less — see gap 1).
- Files: download URLs via pixeldrain `/u/ → /api/file/` mapping, per quality, for posts that carry pixeldrain links.
- Metadata: year from `(YYYY)` in title, Movie-vs-TV heuristic from title words.

### Possible but unimplemented (ranked by value/effort)

1. **Movie/special direct streaming via pixeldrain** (high value, tiny effort). Detect non-`.rar` pixeldrain targets (via `/info` `name`/`mime_type`, one cached GET per file) and surface `.mp4`/`.mkv` as stream sources instead of batch downloads. Same for Drive movie links after confirm.
2. **Google Drive as second file backend** (medium value, small effort). Same per-quality files as pixeldrain on most posts; flow is `GET uc/usercontent URL → scrape confirm form → GET with confirm=t+uuid → range-capable direct URL`. Covers posts where pixeldrain links are missing (e.g. sakamoto-live has Drive but no pixeldrain).
3. **Per-quality episode-range parsing from acefile slugs + title text** (robustness, tiny effort). Acefile slugs always end `-01-15-{q}p-rar` style; parse ranges from the slug/title instead of only the pixeldrain filename.
4. **Category/tag browsing** (low-medium value, tiny effort). `?categories=` / `?tags=` filters + the 8-category / franchise-tag maps above enable genre/franchise shelves.
5. **`_embed` / `/search` optimizations** (low value). Skip — current two-step is cheaper than `_embed`, and `/search` drops poster ids.
6. **NOT recommended**: acefile/hxfile POST+captcha resolvers, MEGA-protocol client, terabox/fileditch challenge bypass, krakenfiles/akirabox/megaup/mir.cr (dead or JS-gated on samples). Fragile, high-maintenance, low marginal coverage given pixeldrain+Drive carry the same files.

## 6. Provider coverage vs gaps (`kusonime.py`)

| Covers | Gap |
|---|---|
| Catalog/search/details/posters (`/posts`, `/media`, relevance re-rank) | Search ranking is client-side heuristic — acceptable, WP gives no relevance order. |
| Page fetch + pixeldrain-only link extraction | Misses Drive entirely (same files, second backend, one confirm GET away). Misses nothing else of value — other hosts are gated/dead (see matrix). |
| `_batch_range` from filename `01-16` | **Fragile on current data**: pixeldrain names are frequently range-less (`…Musim 3 720p.rar`); same pixeldrain id reused across blocks on the jadul post. Should parse range from acefile slug + title `Episode 01-12` fragment with pixeldrain-id dedup. |
| `_quality` from anchor text `(\d{3,4})p` | Broken on current markup: anchor text is now the host label (`Pixeldrain`), quality lives in the block `<strong>` header. Must associate links with their enclosing `.smokeurlrh` block's header. Filename-based quality (acefile slug, pixeldrain `/info` name) is the fallback. |
| Movies treated as batches (`Episode` list synthesized, rar assumed) | Movie posts serve direct `.mp4`/`.mkv` — should be detected (extension via `/info` or slug) and surfaced as playable stream sources, not batch episodes. |
| `sources()` returns pixeldrain direct URLs | Correct for series downloads; for movies these same URLs are streams. No change needed except labeling. |
| No category/tag filters | Endpoints verified working; optional enhancement. |

Evidence notes: pixeldrain `/info` responses include `views/downloads/bandwidth_used` — view counts confirm these files are actively used (e.g. Dandadan 720p rar: 1496 views, 1663 downloads). All 12 pixeldrain ids tested returned 200 with exact names; sizes 195 MB–6.4 GB.
