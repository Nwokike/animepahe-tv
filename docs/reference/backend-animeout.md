# Backend reference — animeout.xyz (WordPress + own DDL system)

Probed 2026-10-11 with read-only GET/HEAD (`httpx`, UA `Mozilla/5.0 Chrome/120.0`,
plus one `primp` chrome-impersonation check). Facts only; every claim has its
evidence inline or in §5.

Base URLs:

- Site/API: `https://animeout.xyz` — WP REST at `/wp-json/wp/v2/...`
- File hosts: `http(s)://<host>.animeout.com/...mkv` (hosts seen: `nimbus`,
  `typhon`, `sv1`, `sv4`, `yotsuba`, `chunchunmaru`, `chomusuke`, dead: `slaaine`)
- DDL landing: `https://ddl.animeout.com/index.php?url=<host>/<path>`
- DDL public page: `https://ddl.animeout.com/public.php?url=<host>/<path>`
- Final file: `https://public.animeout.xyz/<host>/<path>` — **Cloudflare-challenged**

---

## 1. Complete endpoint map

### 1.1 WP index (`GET /wp-json/` → 200, ~109 KB JSON)

- `name`: "AnimeOut", `description`: "Direct Download Free Encoded Animes"
- `url`/`home`: `https://www.animeout.xyz` (note: `www.` canonical; `animeout.xyz`
  works and serves the API)
- Namespaces: `oembed/1.0`, `akismet/v1`, `disqus/v1`, `wp/v2`,
  `wp-site-health/v1`. No custom/anime namespace — everything is stock WP.
- Auth surface: only `application-passwords` authorize endpoint (needs WP login;
  not usable anonymously).

### 1.2 Types (`GET /wp-json/wp/v2/types` → 200)

`post`, `page`, `attachment` (rest_base `media`), `wp_block`, `spucpt`
("Popups"). Post taxonomies: exactly `category` + `post_tag`. Pages have no
taxonomies.

### 1.3 Posts (`/wp-json/wp/v2/posts`)

- Totals (2026-10-11): **3744 posts** (`X-WP-Total: 3744`, `X-WP-TotalPages: 3744`
  at `per_page=1`).
- `per_page`: 1–100 enforced. `per_page=100` → 200 with 100 items;
  `per_page=101` → **400** `rest_invalid_param`
  (`"per_page must be between 1 (inclusive) and 100 (inclusive)"`).
- Verified working query params: `search`, `search_columns=title`,
  `categories=<id>`, `tags=<id>`, `categories+tags` combo (AND; `.hack` tag +
  cat 3 → `[]`, i.e. correctly empty), `slug=<slug>` (exact lookup works:
  `slug=naruto-2002originalcomplete` → id 139450), `include=139450,497`,
  `offset=5`, `after=2026-09-01T00:00:00`, `before=2020-01-01T00:00:00`
  (both honoured), `status=publish`, `orderby` ∈ {date, modified, title, slug,
  id} × `order` ∈ {asc, desc}, `_fields`, `_embed`, `page`.
- `sticky=true` → 200 `[]` (no sticky posts in use).
- `_embed` **works and inlines everything in one call** — but ONLY when
  `_fields` does not exclude `_embedded`. `?_embed` alone returns `_embedded`
  with `author` (e.g. "AOT Staff"), `wp:featuredmedia` (with `source_url`), and
  `wp:term` (categories + tags). `?_embed&_fields=id,title,_embedded` returns
  only `id,title` — `_embedded` silently dropped. So one
  `GET /posts?_embed&per_page=N` replaces the current posts + media-include
  two-step.
- Post object keys: `id, date, date_gmt, guid, modified, modified_gmt, slug,
  status, type, link, title, content, excerpt, author, featured_media,
  comment_status, ping_status, sticky, template, format, meta, categories,
  tags, _links`. No custom meta of value (`meta: []` on terms; posts carry no
  structured episode/file metadata — everything is inside `content.rendered`).
- `/posts/<id>/revisions` → **401** `rest_cannot_read` (auth required).
- `/?rest_route=/wp/v2/posts` → **403 Cloudflare challenge page** — only the
  pretty `/wp-json/` path works programmatically.
- Title convention (used for year/type parsing):
  `Name (main)(YYYY)(TV Series|Movie|TV Special)(Ongoing|Complete)(Episode N)`
  on new posts; older mega-posts use
  `Name (Complete)(1080p-200MB|720p-100MB)` / `(Mega Post)` style.
- `comment_status: open` on posts (e.g. 139450).
- `/wp-json/wp/v2/search?search=naruto&per_page=5` → 200, entries
  `{id, title, url, type, subtype}` — good relevance out of the box
  (Naruto Shippuuden complete, Naruto 2002, Boruto, Naruto Movies…).
  Search totals header present (`search=naruto` → `X-WP-Total: 9` on
  `/posts?search=`).

### 1.4 Categories (`/wp-json/wp/v2/categories`) — 28 total, 1 page

| id | count | name | parent |
|----|-------|------|--------|
| 14432 | 94 | 1080p Anime Movies | 4 |
| 14456 | 34 | 1080p Anime OVA | 5 |
| 14433 | 249 | 1080p Complete Anime Series | 16 |
| 11713 | 242 | 1080p Ongoing Anime | 15 |
| 9 | 10 | 480p Anime Movies | 4 |
| 10 | 47 | 480p Anime OVA | 5 |
| 11 | 208 | 480p Complete Anime Series | 16 |
| 17 | 1 | 480p Ongoing Anime Series | 15 |
| 14939 | 1 | 576p Anime OVA | 5 |
| 14892 | 2 | 576p Complete Anime Series | 16 |
| 12 | 187 | 720p Anime Movies | 4 |
| 13 | 114 | 720p Anime OVA | 5 |
| 14 | 870 | 720p Complete Anime Series | 16 |
| 18 | 344 | 720p Ongoing Anime Series | 15 |
| 2043 | 517 | 720p Source | 0 |
| 4 | 410 | Anime Movies | 0 |
| 5 | 291 | Anime OVA | 0 |
| 3 | 1336 | Anime Series | 0 |
| 2386 | 13 | Announcement | 0 |
| 14886 | 118 | BD | 0 |
| 16 | 1897 | Complete Anime Series | 3 |
| 14885 | 82 | Dual Audio | 0 |
| 14893 | 2 | DVD | 0 |
| 8 | 109 | General | 0 |
| 1842 | 1 | Manga | 0 |
| 15 | 1085 | Ongoing Anime Series | 3 |
| 6 | 2 | Other Releases | 0 |
| 1 | 0 | Uncategorized | 0 |

Useful browse filters the provider does not use yet: `categories=15` (ongoing,
1086 posts per `X-WP-Total`), `categories=16` (complete), `4` (movies),
`5` (OVA), `14885` (dual audio), `14886` (BD), plus per-quality children.
`?categories=15` verified returning ongoing posts.

### 1.5 Tags (`/wp-json/wp/v2/tags`) — 5136 total, 52 pages

Per-anime tags (e.g. id 490 `.hack`, 492 `.hack direct download`, 493
`.hack Torrent`). `?tags=490` correctly returns the two `.hack` posts.
Tag counts are small; categories are the better browse axis.

### 1.6 Pages (`/wp-json/wp/v2/pages`) — 20 total

`download-anime`(42597), `home`(35926), `recruitment`(30104),
`complete-anime`(588), `ongoing-anime`(592), `our-friends`(71979),
`support`(69505), `my-tickets`(69481), `all-releases`(45588),
`open-ticket`(45529), `theater`(39187), `terms`(38248), `privacy-policy`(38246),
`anime-tags`(35924), `faq`(33899), `projects-list`(61), `forums`(27148),
`download-anime-ova`(597), `download-anime-movies`(595), `hotlink`(2496).
Spot-checked content: Theater page is a dead 2015 livestream embed
(`http://www.animeout.xyz/livestream/index.html`, "Streams on 11th October,
2015"); Hotlink page states the anti-hotlink policy and a "maximum 4
connections per IP per download" limit; FAQ describes the DDL offering. None
carry episode/file data.

### 1.7 Comments (`/wp-json/wp/v2/comments`) — open, readable

`GET` (no auth) works; `?post=139450` filter works (e.g. id 33591 on the Naruto
post). Live comments exist (id 35781 dated 2026-10-09). Not needed for
playback; optional for a comments feature.

### 1.8 Users / taxonomies / oEmbed / media

- `/wp/v2/users` readable without auth (id 56 `@nime Kami`, etc.). No app value.
- `/wp/v2/taxonomies` confirms only `category` + `post_tag`.
- `/wp-json/oembed/1.0/embed?url=<post-url>` → 200 with title/author
  (author e.g. "Slime"). No playback value.
- `/wp/v2/media`: **7001 items**. `?include=<ids>` batch works
  (`include=343467,1277628` → both `source_url`s in one call). Items carry
  `source_url`, `caption`, `alt_text`, `media_details.sizes` (thumbnail 150×150,
  medium 300px, medium_large 768px, large, 1536×1536, post-thumbnail).
  Posters are `wp-content/uploads/...` images, hotlinkable (an `<img>` in post
  139450 loads from `www.animeout.xyz`).

### 1.9 Date/ordering for airing-season browsing

`orderby=date&order=desc` = latest releases; `after`/`before` window correctly
(e.g. `after=2026-09-01` → Oct 2026 ongoing-episode posts;
`before=2020-01-01` → Dec 2019 posts). `orderby=modified` surfaces recently
edited posts (episodes appended to mega-posts bump `modified`). All usable for
season/airing browse without scraping.

---

## 2. Post content: episode links, quality variants, metadata

- Episode links are plain `<a href="http(s)://<host>.animeout.com/...mkv">`
  anchors in `content.rendered`. Current posts use `http://nimbus.animeout.com`;
  older mega-posts mix hosts per episode range (post 497 One Piece: eps ~574+
  on nimbus, eps ~890+ on `typhon`; post 160691 movies on `chunchunmaru`,
  `sv4`, `chomusuke`, nimbus).
- **Quote-style split (important):** new/complete posts use double quotes
  (post 139450 Naruto: 248 double-quoted, 0 single-quoted `.mkv` hrefs), but
  the giant One Piece ongoing post 497 uses **single quotes for 2067 of 2082**
  `.mkv` hrefs (15 double-quoted). A double-quote-only extractor misses ~99%
  of that page.
- **Two qualities per episode** in current ongoing posts: each episode appears
  twice — 1080p under `/series/00RAPIDBOT/<Title>/` and 720p under
  `/series/Ongoing/<Title>/` (verified on post 1269069 Tempal: 3×1080p +
  3×720p for eps 1–3). Filename convention:
  `[AnimeOut] <Title> - <EP> [<hash>][1080pp|720p][<Fansub>][x265][RapidBot].mkv`.
  Older posts use `Ep`-less `Title.001.v4.480p...` dot notation.
- Some old movie posts use **base64-encoded path segments**
  (post 160691 `chunchunmaru` links), opaque but still plain hrefs → same chain.
- **No alternate/external downloads anywhere.** Grep over posts 139450
  (250 hrefs: 248 nimbus + 2 self), 497, 1190503, 160691, 32112, 1269069,
  1271515: zero occurrences of `mega.nz`, `drive.google`, `terabox`,
  `pixeldrain`, `magnet:`, `rapidgator`, `1fichier`, `nyaa`, `gdrive`.
  `torrent` appears only as link-less `<a class="burnbit_torrent">Torrent</a>`
  text (no href — dead UI remnant). Every downloadable href host is
  `*.animeout.com`. Non-mkv hrefs are cover art (`/staff/img/*.jpg`) and one
  `.zip` (eng subs `naruto-complete-series_english-2206507.zip` on
  `www.animeout.xyz`).
- `excerpt.rendered` carries a metadata block: `Synonyms: … Type: TV Series
  Episodes: 24 Aired: 2012-03-23 Ended: 2012-09-22 Rating: 5.38` (verified on
  post 1029418 Accel World; same shape on 139450/1190503). Episode counts and
  type/status are therefore available without parsing titles — but the exact
  `Episodes:` value needs per-post validation (formats vary by era).
- Posts with no files exist (post 1190503 One Piece Novel Heroines: full
  metadata block, zero `.mkv` hrefs — files not yet uploaded). Clients must
  handle zero-episode posts.
- Post titles/headers carry size tags (`80MB – 480p`, `1080p-300MB|720p-150MB`)
  usable as approximate file sizes; no exact byte counts are exposed.

## 3. The file wall (systematic pass, 2026-10-11)

Test file (Naruto ep 1):
`http://nimbus.animeout.com/series/Ongoing/Naruto/Naruto.001.v4.480p.DVD.Dual-Audio.FLAC2.0.Hi10P.x264-AnimeOut[JySzE][x265][RapidBot].mkv`

### 3.1 Full chain trace (redirects followed)

1. `http://nimbus…mkv` → **301** → `https://nimbus…mkv`
   (`server: nginx/1.18.0 (Ubuntu)`).
2. `https://nimbus…mkv` → **302** →
   `http://ddl.animeout.com/index.php?url=nimbus.animeout.com/series/...`
   (same nginx; note downgrade to http).
3. `http://ddl…index.php?url=…` → **301** → `https://ddl.animeout.com/index.php?url=…`.
4. Landing **200** `text/html` (5701 bytes), sets **`PHPSESSID` cookie**
   (only `Set-Cookie` in the whole chain), contains the public link
   `https://ddl.animeout.com/public.php?url=nimbus.animeout.com/series/...`.
5. `public.php` — HEAD → **200 empty** (`content-length: 0`);
   GET → **200** `text/html` 15104 bytes with inline
   `var url = "https://public.animeout.xyz/nimbus.animeout.com/series/...mkv"`.
   No additional cookies set at this hop.
6. `GET https://public.animeout.xyz/...mkv` → **403** `text/html` (~6 KB)
   `Just a moment...` Cloudflare challenge. Response headers include
   `server: cloudflare`, `cf-mitigated: challenge`, `cf-ray: a490cb46cfedbccf-AMS`.

### 3.2 Bypass attempts — all failed

| attempt | result |
|---------|--------|
| GET with cookies collected from full chain (`PHPSESSID`) | 403 challenge |
| `Referer: https://ddl.animeout.com/` | 403 challenge |
| `Referer: https://animeout.xyz/` | 403 challenge |
| `Range: bytes=0-1023` | 403 challenge (no 206 path) |
| HEAD on the file URL | 403 + full challenge headers |
| `http://` variant of the file URL | 403 challenge |
| `primp` AsyncClient `impersonate="chrome"` + DDL Referer | 403 challenge (6397 bytes) |
| Skipping to `public.php` without landing first | same `var url`, same 403 |

No `Set-Cookie` is ever issued by `public.animeout.xyz` (the challenge blocks
before any app logic), so there is no cookie to harvest. No countdown/token
parameter exists on `index.php`/`public.php` — the only gate is the click/JS on
`public.php` plus the Cloudflare challenge on the file host. **Conclusion: no
keyless programmatic path to file bytes today; the wall is Cloudflare on
`public.animeout.xyz`, not the DDL pages.**

### 3.3 Old hosts probe (same file path, `follow_redirects=False`)

| host | http | https | server |
|------|------|-------|--------|
| nimbus | 301 → `https://nimbus…` | 302 → `http://ddl.animeout.com/index.php?url=nimbus…` | nginx/1.18.0 (Ubuntu) |
| typhon | 301 → https | 302 → ddl (`url=typhon…`) | nginx/1.18.0 (Ubuntu) |
| sv1 | 301 → https | 302 → ddl (`url=sv1…`) | cloudflare |
| sv4 | 301 → https | 302 → ddl with **rewritten host `url=sv2…`** | cloudflare |
| yotsuba | 301 → https | 302 → ddl (`url=yotsuba…`) | cloudflare |
| chunchunmaru | 301 → https | 302 → ddl (`url=chunchunmaru…`) | cloudflare |
| chomusuke | 301 → https | 302 → ddl (`url=chomusuke…`) | cloudflare |
| slaaine | DNS fail (`getaddrinfo failed`) both schemes | — | dead |

All live hosts funnel into the same `ddl.animeout.com` chain (same wall); none
serve bytes directly. Note the `sv4 → sv2` rewrite quirk in the redirect
`url=` param — resolvers must follow redirects, not construct DDL URLs by hand.

## 4. DDL landing page offers

`index.php` (5701 bytes, full body captured): two-column info page, **no
countdown timer, no direct file button**.

- **Private-DDL (donators):** login form (`POST username+password`, two copies —
  sidebar + modal `#openModal`; `openLogin()` is currently a no-op). Pitch:
  no ads, no connection/speed limits, login bypasses this page entirely and
  downloads "start directly and automatically as long as their session lasts".
  Donation via `patreon.com/animeout`, min $5, account created manually over
  Patreon message. → Authenticated private DDL exists but needs donor
  credentials; out of scope for anonymous source.
- **Public-DDL (free):** single `Download (Public Server)` button
  (`<a class="btn" target="_blank" href="https://ddl.animeout.com/public.php?url=…">`).
  Limits stated: 1 connection/IP, 1 MBps (8 Mbps) cap, ad-supported. Library
  claim: "900+ Anime series and 22k episodes … 60MB (480p) and 100MB (720p)".
- `public.php` (15104 bytes): "Download request loaded, click anywhere on the
  page to start your download" (`<body onclick="start()">`,
  `window.location = url`), adblock-detection scripts, ad scripts
  (`performanceadexchange.com`, `ajax.googleapis.com` jquery 1.3), donator
  upsell (`patreon.com/animeout`), cbox chat iframe on the landing page.
  The `var url` target is present in static HTML — no JS execution needed to
  extract it.
- Anti-hotlink note (Hotlink page 2496): downloads require clicking through the
  site; max 4 connections/IP.

## 5. Full-experience checklist (today)

| ability | status | evidence |
|---------|--------|----------|
| Discovery / latest releases (`orderby=date`) | ✅ works | `ORDERBY date` → newest posts incl. 2026-10-12 episodes |
| Airing-season browse (`after`/`before`, `categories=15`) | ✅ works, unused | `AFTER`/`CAT15 totals: 1086` |
| Search (incl. `search_columns=title`, `/v2/search`) | ✅ works (fuzzy; re-rank client-side) | `SEARCH totals: 9` for naruto; `/v2/search` good order |
| Details: title/year/type | ✅ works | title conventions + excerpt `Type:` |
| Details: episode count / status / aired / rating | ✅ available via excerpt, unused | Accel World excerpt block |
| Posters (featured media, incl. `_embed` one-call) | ✅ works | `_embedded.wp:featuredmedia.source_url`; media 7001 items |
| Episode list with names (`- N [hash][1080pp][Fansub]…`) | ✅ works | 248 links post 139450; 72 (36×1080p + 24×720p…) post 1029418 |
| Episode counts from titles | ✅ works | `(Episode N)` / `- N [` / `S01E12` patterns |
| Approx sizes from title/header tags | ⚠️ approximate only | `80MB – 480p`, `1080p-300MB\|720p-150MB` |
| Dual quality (1080p + 720p) per episode | ✅ available, unused (first-seen wins) | Tempal post: `00RAPIDBOT` 1080p + `Ongoing` 720p |
| Comments | ✅ available, unused | `?post=` filter works |
| File bytes / streaming / download | ❌ **walled** | §3.2: 403 `cf-mitigated: challenge` on every variant |
| Private-DDL (donor login) | ❌ needs donor credentials | login form POST; Patreon $5 flow |
| External mirrors (mega/drive/…) | ❌ do not exist | §2 grep: zero hits across 7 posts |

## 6. Provider coverage vs misses

File: `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\src\services\providers\animeout.py`

**Covered:** catalog (`/posts` + `/media?include=`), search + client-side
relevance re-rank, episode extraction from `content.rendered`, two-hop resolve
(`index.php` → `public.php` → `var url`), graceful `[]` when the final host is
`public.animeout.xyz`, filename → resolution/audio/fansub parsing.

**Misses / gaps (ordered by impact):**

1. **Single-quoted hrefs ignored — biggest recall bug.** `_parse_episode_links`
   matches only `href="…mkv"`. Post 497 (One Piece ongoing): 2067
   single-quoted vs 15 double-quoted `.mkv` hrefs — the provider would return
   ~15 episodes instead of ~1000+. Fix: match `href=["']…` (verified both
   styles in the wild; 139450 is double-only, 497 is ~99% single).
2. **Second quality dropped.** Posts carry 1080p + 720p links per episode;
   `seen`-by-episode-number keeps the first only. Could yield two `Source`s
   (quality choice) once the wall clears.
3. **Two HTTP calls where one suffices.** `_embed` on the posts call inlines
   poster + author + terms; `_fields` must then be dropped (it strips
   `_embedded` — verified). Optional optimisation.
4. **`per_page=12` fixed; 100 allowed.** Fewer round-trips for search/latest.
5. **No category/genre/quality browse** (`categories=15/16/4/5/14885/14886`
   all verified) and **no date-window browse** (`after`/`before` verified) —
   cheap discovery upgrades.
6. **Details screen thin:** `episodes=0, status="", season=""` hardcoded, yet
   the excerpt block carries `Type/Episodes/Aired/Ended/Rating`. Parse it
   (validate per-era formats first).
7. **Sizes missing:** only title/header tags (`80MB – 480p`) — approximate;
   acceptable to surface as estimates, never exact bytes.
8. **DDL URL construction risk:** `_resolve_direct_url` regex requires
   `https://ddl…public.php`; the chain itself uses `http://` mid-hops and
   `sv4` rewrites to `sv2` — following redirects (current behaviour) is
   correct; never hand-build the `url=` param.
9. Correctly out of scope: donor login, comments, Theater/livestream (dead
   since 2015), `revisions` (401), `?rest_route=` (CF 403).

## 7. Raw evidence (abridged)

- `GET /wp-json/` → 200 `application/json` 109054 B, namespaces
  `oembed/1.0, akismet/v1, disqus/v1, wp/v2, wp-site-health/v1`.
- `GET /wp/v2/types` → post(+category,post_tag), page, attachment, wp_block, spucpt.
- `X-WP-Total`: posts **3744**, media **7001**, tags **5136** (52 pp),
  categories **28**, pages **20**.
- `per_page=101` → 400 `rest_invalid_param`.
- `_embed` alone → `_embedded: [author, wp:featuredmedia, wp:term]`,
  `source_url: https://www.animeout.xyz/wp-content/uploads/2026/10/29806_…-1024x584-1.png`;
  with `_fields=id,title,_embedded` → `_embedded` dropped.
- Chain: `301 nginx → 302 nginx → 301 → 200 (5701 B, PHPSESSID=…) →
  public.php 200 (15104 B, var url) → file 403 cf-mitigated: challenge
  (cf-ray a490cb46cfedbccf-AMS)`.
- HEAD `public.php` → 200, 0 bytes. primp-chrome file GET → 403, 6397 B.
- Hosts: nimbus/typhon = `nginx/1.18.0 (Ubuntu)`; sv1/sv4/yotsuba/
  chunchunmaru/chomusuke = `cloudflare`; slaaine = DNS fail.
- `sv4` 302 location contains `url=sv2.animeout.com/…` (host rewrite).
- Keyword grep (posts 139450/497/1190503/160691/32112/1269069/1271515):
  mega/drive/terabox/pixeldrain/magnet/rapidgator/1fichier/nyaa = 0;
  only dead `<a class="burnbit_torrent">Torrent</a>` (no href).
- Landing page: `Donator's Login` POST form ×2, `Download (Public Server)` btn,
  cbox iframe `www4.cbox.ws/box/?boxid=4315531`, no timer.
- `public.php`: `onclick="start()"`, `window.location = url`, adblock detect,
  ext hosts `performanceadexchange.com + ajax.googleapis.com` only.
- Zero-file post exists: 1190503 (metadata, 0 mkv hrefs).
- Quote counts: 139450 `dq=248 sq=0`; 497 `dq=15 sq=2067`.
- Quality split: 1269069 → 3×`00RAPIDBOT…[1080pp]` + 3×`Ongoing…[720p]`;
  1029418 → 72 mkv (36×1080p + 24×720p sampled).
- Excerpt sample (1029418): `Accel World (main) (150MB – 720p) Synonyms: …
  Type: TV Series Episodes: 24 Aired: 2012-03-23 Ended: 2012-09-22 Rating: 5.38 …`.
- `?rest_route=/wp/v2/posts` → 403 challenge; `/posts/<id>/revisions` → 401.
- Hotlink page: 4-connections/IP limit, click-through required.
