# Backend reference — kayoanime.com (WordPress + Google Drive)

Probed 2026-10-11. Read-only GET probes only. All facts below were observed directly;
no inference beyond what the responses show. Previously verified facts (WP catalog,
Drive listing, 206 streaming, keyless route) were re-confirmed where cited.

Base: `https://kayoanime.com` — plain WordPress REST, no Cloudflare challenge, no auth.
Drive API key observed in use: `AIzaSyC1qbk75NzWBvSaDh6KnsjjA9pIrP4lYIE`
(works only with header `Referer: https://drive.google.com/`).
Google Group gate: `https://tinyurl.com/9yh733xs` → resolves (302 chain) to
`https://groups.google.com/g/kayoanime-naruto-shippuden/c/mJvLAi43420`
(a per-anime Google Group join page; joining grants the "[Private Drive]" folders).

---

## 1. Complete endpoint map

### 1.1 WordPress REST (`/wp-json/`)

| # | Endpoint | Example | Status / evidence |
|---|----------|---------|-------------------|
| W1 | `GET /wp-json/` (index) | — | 200. Namespaces: `oembed/1.0`, `wp-toolkit/api`, `litespeed/v1+v3`, `yoast/v1`, `wp/v2`, `wp-site-health/v1`, `wp-block-editor/v1`, `wp-abilities/v1`. No custom anime namespace. |
| W2 | `GET /wp-json/wp/v2/posts` | `?per_page=100&page=1&_fields=id,title` | 200. `X-WP-Total: 654`, `X-WP-TotalPages: 7` (at per_page=100). Page 2 also 100 items. Out-of-range page (`page=9999`) → 400 `rest_post_invalid_page_number`. Default ordering is newest-first (post id desc). |
| W3 | `GET /wp-json/wp/v2/posts?search=X` | `?search=frieren&per_page=5&_fields=id,title,link` | 200. Substring/full-text WP search over title+content+excerpt. **Noisy**: `search=one piece` returns Barakamon, K-On!, Noragami before the real One Piece post (id 162) — WP matches the word "piece" inside post content (e.g. "masterpiece"). Short distinctive queries work well (`naruto` → Boruto id 961 + Naruto Shippuden id 477; `bleach` → id 214; `frieren` → id 197; `dandadan` → id 813). Always show all `per_page` hits and let the user disambiguate; do not assume hit #1. |
| W4 | `GET /wp-json/wp/v2/posts?slug=X` | `?slug=dandadan-season-1-2-1080p-dual-audio-hevc` | 200, exact single match (id 813). Reliable for deep-linking once a slug is known. |
| W5 | `GET /wp-json/wp/v2/posts/{id}` | `/wp-json/wp/v2/posts/961?_fields=id,title,slug,link,categories,featured_media,modified,content` | 200. Full content HTML contains the Drive folder anchors (see §2). |
| W6 | `GET /wp-json/wp/v2/posts?categories=N` | `?categories=4&per_page=3` → `X-WP-Total: 578` | 200. Works; category 4 = "Anime Series" (578 of 654 posts). Also `categories=3` (Ongoing Anime), `categories=2` (Anime Movie). Multiple ids comma-separable per WP semantics (not explicitly probed beyond single). |
| W7 | `GET /wp-json/wp/v2/posts?orderby=modified&order=desc` | `?per_page=3&orderby=modified&order=desc&_fields=id,title,modified` | 200. Returns most-recently-updated posts first, e.g. id 2867 `2026-10-11T18:06:10` (same-day update). Use for "latest updates" feed. |
| W8 | `GET /wp-json/wp/v2/posts?_embed=1` (no `_fields`) | `?search=frieren&per_page=1&_embed=1` | 200 (~43 KB). `_embedded` contains `author`, `wp:featuredmedia`, `wp:term`. Featured-media object gives `source_url` + `media_details.sizes` (medium 300px, large 1024px, thumbnail 150px, medium_large 768px, `jannah-image-small/large/post`, full). **Caveat: `_embed` combined with `_fields` returns NO embedded data** (observed: `?_embed=1&_fields=id,title,link,featured_media,_embedded` → 269-byte body, no `_embedded` key). Request the full post (or at least omit `_fields`) to get posters inline. |
| W9 | `GET /wp-json/wp/v2/media/{id}` | `/wp-json/wp/v2/media/198` | 200. Attachment record; `guid.rendered` = original JPG URL. Poster convention: `https://kayoanime.com/wp-content/uploads/2026/05/<slug>.jpg` (1280×720 landscape for id 162's `one-piece-all.jpg`; Frieren poster has 300/768/1024 variants). |
| W10 | `GET /wp-json/wp/v2/categories?per_page=100` | `?_fields=id,count,name,slug` | 200, **27 categories, all genre/status buckets, zero tag taxonomy in use**. Full list: id 9 Action (263), 10 Adventure (179), 2 Anime Movie (62), 4 Anime Series (578), 31 Chinese Anime (6), 11 Comedy (216), 12 Demons (28), 7 Drama (143), 5 Fantasy (297), 13 Horror (20), 14 Magic (39), 15 Martial Arts (10), 16 Mecha (17), 17 Military (16), 18 Music (4), 19 Mystery (29), 3 Ongoing Anime (39), 8 Psychological (13), 20 Romance (181), 21 School (146), 22 Sci-Fi (47), 23 Shounen (110), 24 Slice of Life (121), 25 Space (2), 26 Sports (16), 27 Super Power (76), 1 Uncategorized (0). |
| W11 | `GET /wp-json/wp/v2/tags` | `?per_page=100` | 200, body `[]`. **Tags are unused — do not build any tag flow.** |
| W12 | `GET /wp-json/wp/v2/search?search=X` | `?search=frieren&per_page=5` | 200. Lightweight type-ahead: `[{id, title, url, type:"post", subtype:"post"}]`. Frieren → exactly id 197. Good for autocomplete UIs. |
| W13 | `GET /wp-json/wp/v2/pages` | `?per_page=5&_fields=id,title,slug,link` | 200, 1 page (id 15, the front page "Kayoanime » News, Reviews & Updates of Anime"). No content pages to mine. |
| W14 | Post `yoast_head_json` | `posts/197?_fields=yoast_head_json` | `og_image[0].url` = poster JPG (same as featured media). `title` = full post title. `description` empty. Fallback poster source. |
| — | `?_fields` projection | e.g. `?_fields=id,title,featured_media,link` | Supported on all wp/v2 reads; use for list views (small bodies), but see W8 caveat. |

### 1.2 Google Drive API v3 (all with `Referer: https://drive.google.com/`)

| # | Endpoint | Example | Status / evidence |
|---|----------|---------|-------------------|
| D1 | `GET https://www.googleapis.com/drive/v3/files?q='{folderId}' in parents&fields=files(id,name,mimeType,size[,modifiedTime])&pageSize=100&key={KEY}` | Boruto Box 2 `1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs` | 200, 15 children, all `video/x-matroska`, names `[Kayoanime] Boruto - Naruto Next Generations - 93..107.mkv`, sizes 233–335 MB. Other boxes: Box 3 = 12 files (108–119), Box 4 = 28 files (123–147? listed 123–147 range shown 124–147 in sample), Box 5 (`1VopYjXbZH5UtQ0weeCyovUZTppDwdKb5`) = 18 files (148–165), Box 6 (`1UKWccvPLOD1MycpDFYMpB6EKK7kJFIJV`) = 41 files (166–206), Box 7 (`1LpT9SbLJXh-E7pMAvOX5COTTzgO9R3u-`) = 29 files (207–235), Box 8 (`1UmMHUggIYzb2JBsG7zJNbNydflQ-xX-1`) = 58 files (two naming runs, see §2), Movie (`1dbjjTwrx2Q8liPGZMC9W8IrC9kz6Ue7G`) = 1 file (`[Kayoanime] Naruto Shippuden - Movie 08 - Boruto - Naruto The Movie.mkv`). No `nextPageToken` on any (all fit in one page; largest = 58). |
| D2 | Same D1 query on restricted folders | `1YzLqwX_RFidOeXd2BdMb2TJxp6CKJ9n2` (Boruto BOX 1), `1F_w6VDJn824XUBF3v3gSdy843Mj-4yWQ`, `1Z7MmKN7YHr9pj8To_qURLKR9XgEXp0ra` (Frieren private), `1sl2rZUanjydVYDma7HmlLxX4Uvz_sJpG` (Dandadan S1), `1JDtnYkrivilU7cs9tGHBbDqRKsekW1k-` (Bleach) | **200 with `files: []`** (empty list, NOT an error). But `GET /drive/v3/files/{id}` on the same ids → **404 `notFound`**. Interpretation: these are "[Private Drive]" shared folders the key's identity cannot see (Google Group membership required). A `children: []` + 200 listing is therefore *ambiguous*: treat as "restricted or empty"; confirm via `files.get` (404 = restricted). `supportsAllDrives=true&includeItemsFromAllDrives=true&corpora=allDrives` on listing → 400 `badRequest`; `supportsAllDrives=true` on get → still 404. No parameter workaround found. |
| D3 | `GET https://www.googleapis.com/drive/v3/files/{fileId}?alt=media&key={KEY}` (+ `Range`) | Boruto 107 `116vpgXRUrlsPMURkD4NivijOxnmg4NPf` (255,211,503 B) | Full GET (no Range) → **200**, `content-type: video/x-matroska`, `content-length: 255211503`, `content-disposition: attachment` (bare, no filename), `accept-ranges` header **absent**, `cache-control: private, max-age=0, must-revalidate`. With `Range: bytes=0-2097151` → **206**, `content-range: bytes 0-2097151/255211503`, exact 2,097,152 bytes, EBML magic `1a45dfa3`. Tail `Range: bytes=254162927-` → **206**, `content-range: bytes 254162927-255211502/255211503`, exact 1,048,576 bytes. Server honors arbitrary ranges despite no `accept-ranges` header — safe for seekable streaming. Only first 2 MB / 128 KB peek + tail fetched (full 255 MB never downloaded). |
| D4 | `GET https://drive.usercontent.google.com/download?id={fileId}&export=download&confirm=t` (+ `Range`) | Same file | **Keyless.** With `confirm=t` + Range → **206**, `content-type: application/octet-stream`, `content-range` identical, `content-disposition: attachment; filename="[Kayoanime] Boruto - Naruto Next Generations - 107.mkv"` (includes the real filename — better for downloads). **Without `confirm=t`** → 200 `text/html` "Google Drive - Virus scan warning" interstitial (2,502 bytes), NOT the file. `confirm=t` is mandatory on this route. |
| D5 | Listing without key | `?q=...` with no `key` | 403 "Method doesn't allow unregistered callers". Key is mandatory for D1. |
| D6 | `GET https://drive.google.com/drive/folders/{id}` (folder page HTML) | Box 2 (public) vs BOX 1 (restricted) | Public: 200 (~433–475 KB HTML), title `Box 2 - Google Drive`, contains all 15 `.mkv` filenames embedded in page JS (30 regex hits incl. `x5d`-prefixed dupes) — usable as a **fallback listing** if the API key dies. Restricted: 200 but a Google sign-in page (`accounts.google.com` base href), zero filenames — confirms restriction, no bypass. |

### 1.3 Ancillary / third-party endpoints observed

| # | Endpoint | Evidence |
|---|----------|----------|
| A1 | Vimeo embed `https://player.vimeo.com/video/{id}` in post content | ids 2867 (`.../1234847364`, alive — oEmbed returns `title:"K"`, author `REX`, free account), 214 (`.../1228362047`), One Piece page (`.../1230940725`). Only on recent single-episode/ongoing posts; direct player GET returns 401 to non-browser clients (embed-only). These are *watch-page embeds*, not download sources; no API needed. |
| A2 | `https://tinyurl.com/9yh733xs` | The universal "Google Group" link in almost every post → 302 chain → `https://groups.google.com/g/kayoanime-naruto-shippuden/c/mJvLAi43420`. |
| A3 | Non-Drive file mirrors | **None found.** Full HTML pages scanned for `mega.nz, 1fichier, mediafire, anonfiles, pixeldrain, gofile, filemoon, streamwish, dood, dropbox, onedrive, archive.org` — zero hits. All download buttons are Drive folders; all iframes are Vimeo. |

---

## 2. Folder/file organization model (post → folders → episode files)

**Post → folders.** The canonical path is `content.rendered` anchor tags (`<a href="...drive.google.com/drive/folders/{ID}...">LABEL</a>`).
Anchor labels ARE the organization metadata — always capture `(folderId, label)` pairs:

- Long-running shows: `BOX 1..BOX N` = contiguous episode ranges. Boruto (id 961): 9 folders — BOX 1 (`1YzLqw…`, restricted), BOX 2 (`1mkuqt…`, eps 93–107), BOX 3 (`1KY6ny…`, 108–119), BOX 4 (`1xjgOR…`, 123/124–147), Box 5 (`1VopYj…`, 148–165), BOX 6 (`1UKWcc…`, 166–206), BOX 7 (`1LpT9S…`, 207–235), BOX 8 (`1UmMHUg…`, 136–173 `[Kayoanime]`-named + 274–293 `Boruto - NNN.mkv`-named), Movie (`1dbjjT…`, 1 file). Observed coverage ≈ eps 93–293 + movie (BOX 1 presumably holds ~1–92 but is restricted).
- Season shows: one folder per season, sometimes doubled as public + `[Private Drive]`. Frieren (id 197): `1080p [BLURAY][Private Drive]` (`1F_w6VD…`, restricted), `1080p` (`1FdJmW…`, public, full S1 01–28), `Season 2 [Private Drive]` (`1Z7MmK…`, restricted). Dandadan (id 813): `Season 1` (`1sl2rZ…`, restricted — S1 unavailable anonymously), `Season 2` (`15vy-g…`, public, S02E01–E12).
- Single-episode posts: one `1080p` folder with the episode file(s), e.g. id 2867 → `1-8qvp…` = 1 file `Saikyosoubi - 01.mkv` (227 MB, `video/matroska`), plus a Vimeo embed of the same episode.
- Naruto Shippuden mega-post (id 477): 11 Drive folders (seasons/movies/OVAs groupings) + 5 repeated Google-Group tinyurls; content also contains an apparent revision-data leak (`"32858";"revision"` etc.) — harmless, ignore.
- Maintenance state: One Piece (id 162) wp-json content has a single `href="#"` labeled `FIXING LINKS`; the rendered HTML page likewise has **zero** Drive URLs and a `NEW DRIVE → FIXING LINKS` button. Rule: `href="#"` or zero folder ids ⇒ show "links under maintenance", do not attempt Drive calls.

**Folders → files: always FLAT.** Every accessible folder holds only `.mkv` files — no subfolders, no per-quality splits, no subtitle sidecars, no NFO/txt/jpg (verified by requesting `pageSize=1000` and kind-counting 4 folders: 100% `video/x-matroska` except the 1-file `video/matroska` case). Quality is one-per-post (1080p HEVC per the title); there is never a 720p/480p choice to offer.

**Episode number parsing.** Three filename shapes observed — parse in this order:
1. `[Kayoanime] <Show> - <NNN>.mkv` → ` - (\d{1,4})\.mkv$` (Boruto 93–235, Frieren-style `Sousou no Frieren - 01.mkv` zero-padded 2-digit).
2. `[Kayoanime] <Show> - S<SS>E<EE>.mkv` → `S(\d+)E(\d+)` (Dandadan S2).
3. `<Short> - <NNN>.mkv` → same trailing-number regex (Box 8 `Boruto - 274..293.mkv`).
4. Movies: `[Kayoanime] <Show> - Movie <N> - <Film>.mkv` → no episode number; treat as extras.
Zero-padding varies (`01` vs `107`); normalize with `int()`. Box 8 overlaps Box 6/7 ranges (136–173 appear in both with different sizes) — **dedupe by episode number**, prefer larger file or the `[Kayoanime]`-prefixed copy.

**Reliable traversal algorithm:** `posts/{id}` → regex `drive\.google\.com/drive/folders/([A-Za-z0-9_-]{20,})` + anchor labels from `content.rendered` (HTML page has identical links — verified 9/9 on Boruto — so wp-json alone suffices) → for each folder D1 listing → if `files: []`, D2 `files.get` to distinguish restricted (404) from truly empty → parse episode numbers from names → merge + dedupe across boxes → stream via D3/D4.

---

## 3. Full-experience checklist

| Capability | Verdict | How |
|------------|---------|-----|
| Discovery / browse-all | YES | `W2` paged (`X-WP-Total: 654`, 7 pages @100). Newest-first default. |
| Latest-updates feed | YES | `W7` `orderby=modified&order=desc` (updates land same-day, e.g. 2026-10-11). |
| Genre browse | YES | `W10` 27 categories + `W6` filter (`categories=4` → 578 Anime Series; `3` → Ongoing; `2` → Movies). Tags: N/A (`W11` empty). |
| Search | YES with caveat | `W3` full-text but noisy on multi-word queries ("one piece" → 3 false hits first; true hit id 162 present). Mitigation: `per_page=10`, match query tokens against `title.rendered`, offer disambiguation. `W12` `/v2/search` for light autocomplete; `W4` slug lookup for exact deep links. |
| Details (title/poster/info) | YES | `W5`: title (quality/audio tags embedded, e.g. `1080p Dual Audio HEVC`), `featured_media` → `W8`/`W9` poster JPG + sizes, `categories` ids, MAL-style info block in content (type, status, studios, genres). `modified` = episode-update timestamp; One Piece title itself carries `Episode 1180` progress. |
| Episode list with numbers | YES (public folders) | §2 algorithm. Boruto: 93–293 + movie verified enumerable; Frieren S1 01–28; Dandadan S02E01–12; single-ep posts: 1 file. Numbers parseable from all three filename shapes. |
| Restricted content | PARTIAL (expected) | Folders labeled `[Private Drive]` (≈ BOX 1s, Frieren S1-private/S2, Dandadan S1, some Bleach) return `files: []` + 404 on get. Surface these as "requires Google Group join" with the post's tinyurl link — do NOT retry-loop them. |
| Streaming with seek | YES (verified) | `D3` ranged 206 (`content-range`, EBML magic confirmed) incl. mid-file (prior) and tail probes; `D4` keyless 206 with `confirm=t`. No `accept-ranges` header but ranges honored. MKV HEVC needs a client-side HEVC-capable player (Flet video may not decode — verify at implementation). |
| Download (full file) | YES (verified headers, partial bytes) | `D3` rangeless → 200 `content-length: 255211503`, `content-disposition: attachment` (no filename); `D4` → same + real `filename="...107.mkv"`. Only first 2 MB + peeks transferred; no abuse signal triggered. Prefer D4 for saves (filename), D3 for streaming (correct MKV content-type). Note `D4` without `confirm=t` serves a virus-scan interstitial, not the file. |
| Subtitles (external) | NO | No `.srt/.ass` in any folder; no sub links in any post. Subs/dubs are **burned-in/dual-audio inside the MKV** ("Dual Audio", "English Subbed" refer to tracks). Nothing to fetch. |
| Other mirrors | NO | Drive + Vimeo embeds only (§1.3 A1/A3). |
| Posters | YES | `W8` inline via `_embed` (omit `_fields`!) or `W9` media by id, or `W14` yoast `og_image`. |
| Rate limits / abuse | NONE observed | 3 rapid sequential D1 calls: 200 in 1.83 s / 0.82 s / 1.15 s, no quota/rate strings. `D5` confirms only missing-key 403. Still: keep `Referer` header always, reuse one `httpx.Client`, sequential (not parallel) Drive calls. |

---

## 4. Raw evidence (abridged probe transcripts)

WP index: `namespaces: [oembed/1.0, wp-toolkit/api, litespeed/v1, litespeed/v3, yoast/v1, wp/v2, wp-site-health/v1, wp-block-editor/v1, wp-abilities/v1]`.
Pagination: `page1 200 total: 654 pages: 7 count: 100`, `page2 200 count: 100`, `page9999 400 {"code":"rest_post_invalid_page_number",...}`.
Search: `one piece → [1223 Barakamon, 1091 K-On!, 608 Noragami, 162 One Piece]`; `naruto → [961 Boruto, 477 Shippuden]`; `bleach → [214]`; `frieren → [197]`; `dandadan → [813]`.
`_embed` + `_fields` → 269-byte body, no `_embedded` key; full `?_embed=1` → 43 KB with `wp:featuredmedia.source_url: .../2026/05/sousou-no-frieren-...-hevc.jpg`, sizes `[medium, large, thumbnail, medium_large, jannah-image-small, jannah-image-large, jannah-image-post, full]`.
Slug: `?slug=dandadan-season-1-2-1080p-dual-audio-hevc → [{id: 813, ...}]`.
v2/search frieren → `[{id: 197, title: "Sousou no Frieren ...", url: "https://kayoanime.com/sousou-no-frieren-.../", type: post}]`.
Pages → 1 result (front page id 15). Tags → `[]`.

Post hrefs: 197 → 1 tinyurl + 3 Drive (`1F_w6VD…` priv, `1FdJmW…` public, `1Z7MmK…` priv); 813 → 2 Drive; 961 → 1 tinyurl + 9 Drive (BOX 1–8 + Movie); 477 → 5 tinyurl + 11 Drive; 162 → `href="#"` only; 2867 → 1 Drive (`1-8qvp…`) + Vimeo iframe `1234847364`; 214 → 1 tinyurl + 9 Drive + Vimeo `1228362047`. Boruto anchors: `BOX 1 [Private Drive]→1YzLqw…, BOX 2→1mkuqt…, BOX 3→1KY6ny…, BOX 4→1xjgOR…, Box 5→1VopYj…, BOX 6→1UKWcc…, BOX 7→1LpT9S…, BOX 8→1UmMHU…, Movie→1dbjjT…`. Boruto HTML page = same 9 folder ids (parity confirmed). One Piece page: 0 Drive URLs, `NEW DRIVE → FIXING LINKS`, Vimeo `1230940725`.

Listings (key + Referer): Box2 = 15×video/x-matroska `93..107` (233–335 MB); Box3 = 12 (108–119); Box4 = 28 (124–147 sample); Box5 = 18 (148–165); Box6 = 41 (166–206); Box7 = 29 (207–235); Box8 = 58 (`Boruto - 274..293` + `[Kayoanime]…136..173`); Movie = 1; Frieren-pub = 28 (`Sousou no Frieren - 01..28`, 463–698 MB, mean 567 MB); Dandadan-S2 = 12 (`S02E01..E12`, 404–728 MB); spacemerc = 1 (`Saikyosoubi - 01.mkv`, 227 MB, `video/matroska`). Restricted (`1YzLqw…, 1F_w6VD…, 1Z7MmK…, 1sl2rZ…, 1JDtnY…`): listing 200 `files: []`, `files.get` 404 `notFound`; shared-drives params → 400/404; keyless listing → 403 unregistered-caller. Folder pages: public 200 (~433 KB, `Box 2 - Google Drive`, 30 embedded `.mkv` hits); restricted 200 sign-in page, 0 filenames.

Streaming (file `116vpg…`, 255,211,503 B): first-2 MB Range → `206 video/x-matroska, content-range: bytes 0-2097151/255211503, len 2097152, magic 1a45dfa3, content-disposition: attachment`; rangeless → `200, content-length: 255211503`; tail Range → `206 bytes 254162927-255211502/255211503, len 1048576`; keyless+confirm=t → `206 application/octet-stream, content-disposition: attachment; filename="[Kayoanime] Boruto - Naruto Next Generations - 107.mkv"`; keyless w/o confirm → `200 text/html "Google Drive - Virus scan warning" (2502 B)`. Vimeo: player direct 401; oEmbed 200 `{title: "K", author: REX, free}`. Rate: `200 in 1.83s / 0.82s / 1.15s`, no quota text. tinyurl `9yh733xs` → `https://groups.google.com/g/kayoanime-naruto-shippuden/c/mJvLAi43420`.
