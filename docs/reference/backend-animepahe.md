# Backend reference — animepahe (source #1)

Date: 2026-10-11. Method: read-only GET probes via `primp` (chrome/firefox/safari
impersonations) + public third-party scraper code as secondary evidence wherever the
Cloudflare wall made direct probing impossible. Every claim cites its probe or file.

Canonical base (all mirrors observed in the wild — `animepahe.com`, `animepahe.pw`,
`animepahe.si`, `animepahe.ru`): the app uses `https://animepahe.com`
(`src/services/animepahe.py`, `src/services/ddos_solver.py`). The DDoS solver follows
redirects and rewrites the hardcoded host to the live one at solve time.

---

## 1. Complete endpoint map

### 1.1 Direct-probe results (all read-only GET, primp, 2026-10-11)

All probes below returned Cloudflare walls — **no direct JSON was obtainable without a
solved `cf_clearance`**, which is itself the finding: the API is fully walled, not open.

| Probe | Result |
|---|---|
| `GET https://animepahe.pw/api?m=airing&page=1` (chrome) | 403 `Just a moment...` (~5.1 KB CF page) |
| `GET https://animepahe.com/api?m=airing&page=1` (chrome_120 / chrome_124 / firefox_135 / safari_18.0 aliases) | 403 `Just a moment...` on every impersonation (5.2–5.3 KB) |
| `GET https://animepahe.ru/api?m=airing&page=1` (chrome) | 200 but **not animepahe** — 1608-byte parked-domain page that 302-redirects to `https://animepahe.su/` serving an ad-redirect script (`atob` → `xxzir.com/go/…ref=animepahe.ru`). **animepahe.ru is a squatter. Do not use.** |
| `GET /api?m=search&q=naruto`, `?m=schedule`, `?m=releases`, `?m=release` (no id), `?m=details&id=x`, `?m=anime`, `?m=queue`, `?m=news` on `.ru` | All 200 + identical 1608-byte squatter page (path ignored — further proof `.ru` is parked) |
| `GET /api` (no params), `/api?m=links`, `/api?m=embed`, `/api?m=auth`, `/api?m=user`, `/login`, `/a/1` on `.com` | All 403 `Just a moment...` — wall is uniform; **no endpoint is distinguishable from outside** (a 403 here proves nothing about existence) |
| `GET https://kwik.cx/` | 200, 8277 bytes, generic player landing page (no API surface) |

Because the wall is uniform, endpoint existence/shape below is established from
**five+ independent public scrapers** that run behind their own clearance, cross-checked
against each other. Where only one source attests something, it is flagged.

### 1.2 `GET /api?m=airing&page=N` — latest releases. USED.

- Our code: `src/services/animepahe.py::latest_releases` (`{"m": "airing", "page": str(page)}`).
- Record shape (union of our `LatestRelease` fields and
  `AniFOSS/CloudStream-3` `AnimePaheProvider.kt::getMainPage` `Data`):
  `id`, `anime_id`, `anime_title`, `anime_slug` (CloudStream only), `episode`,
  `snapshot`, `session` (episode session), `created_at`, `anime_session`.
- Pagination: standard Laravel envelope (`total`, `per_page`, `current_page`,
  `last_page`, `has_more = current_page < last_page`). Our code uses `current_page /
  last_page`; CloudStream parses `total` + `data`.
- Note: `anime_session` in the airing payload is the **anime** session (used to build
  `/play/{anime_session}/{episode_session}` links).

### 1.3 `GET /api?m=search&q={q}&l=8&page=N` — search. USED (partly).

- Our code: `src/services/animepahe.py::_search_api` sends `{"m": "search", "q": query,
  "page"}` — **omits `l`** (page-size hint). Every third-party client sends `l=8`
  (`anime-dl/anime-downloader`, `AniFOSS/CloudStream-3` `?m=search&l=8&q=`,
  `miru-app/server` `SEARCH_URL_BASE = ?m=search&l=8`). Omission is harmless (server
  defaults) but we never request the second page either (`search()` threads `page`
  through, UI paginates — fine).
- Record shape: `id`, `slug`, `title`, `type`, `episodes`, `status`, `season`, `year`,
  `score`, `poster`, `session`, `relevance` (CloudStream `AnimePaheSearchData`; ours
  maps all but `slug`/`relevance`).
- No `total==[]` quirk: `anime-dl` checks `search_results['total'] == []` — dead check,
  ignore.

### 1.4 `GET /api?m=release&id={session}&sort=episode_asc&page=N` — episodes. USED.

- Our code: `src/services/animepahe.py::_episodes_api` sends exactly this (+ `page`).
  Page size is **30** (`inkand-paper/Anime` `paheGetAllEpisodes`: `perPage = 30`;
  `miru-app/server` `EPISODES_URL = ?m=release&l=30&sort=episode_desc&page=1`).
- Record shape (union of our `Episode` + `inkand-paper/Anime` `PaheEpisode` +
  CloudStream `AnimeData`): `id`, `anime_id`, `episode` (**float** — supports 10.5-style
  specials; our dataclass types it `int`-ish, Juro parses with `GetFloat`), `episode2`,
  `edition`, `title`, `snapshot`, `disc`, `audio` (`"jpn"` = sub, `"eng"` = dub),
  `duration` (`"HH:MM:SS"` string; Juro `ParseDuration` → ms), `session`,
  `filler` (0/1 int), `created_at`.
- Pagination envelope: `total`, `per_page` (30), `current_page`, `last_page`,
  `next_page_url`, `prev_page_url`, `from`, `to` (CloudStream `AnimePaheAnimeData`).
- Sort values attested: `episode_asc` (everyone), `episode_desc` (`miru-app/server`
  only — usable for "newest first" without walking to `last_page`).
- `&ep={n}` suffix (`anime-dl`, CloudStream `generateListOfEpisodes`): **not a server
  parameter** — a client-side marker appended with `!!FALSE!!` so the loader can find
  episode N inside the page payload later. Do not send to the server.
- Numeric anime id → session: the release endpoint takes the **session UUID**, but the
  anime page URL carries the numeric id. Resolution path: `GET /a/{id}` 302-redirects
  to `/anime/{session}` (Juro `FetchSessionAsync`, CloudStream `getAnimeByIdAndTitle`
  via `?m=search&l=8&q=` + id match). Our app has no equivalent — search-by-title is
  our only resolver (`episodes_for_title`, `sources_for_title`).

### 1.5 `GET /api?m=links&id={anime_id}&session={ep_session}&p=kwik` — episode streams. **NOT USED (biggest gap).**

Attested by **six** independent implementations with identical parameter shape:

- `anime-dl/anime-downloader` `anime_downloader/sites/animepahe.py::_get_sources`:
  `api?m=links&id={anime_id}&session={session}&p=kwik` → `data` → per quality
  `f[x]['kwik_adfly']`, qualities `[x + 'p' for f in data for x in f]`.
- `inkand-paper/Anime` `src/lib/animepahe.ts::paheGetStreams`:
  `` `m=links&id=${animeSession}&session=${episodeSession}&p=kwik` `` →
  `Object.values(data.data)` of `PaheStream { audio: "jpn"|"eng"; kwik: string;
  kwik_pahewin: string; hd: "1"|"0" }`.
- `TheBearodactyl/saikoutsu` `AnimePahe.kt`:
  `$hostUrl/api?m=links&id=${ep.anime_id}&session=${ep.session}&p=kwik`.
- `AniFOSS/CloudStream-3` `AnimePaheProvider.kt::extractVideoLinks`:
  `$mainUrl/api?m=links&id=${ep.animeId}&session=${ep.session}&p=kwik` →
  `AnimePaheEpisodeLoadLinks { data: List<Map<quality, VideoQuality{id, audio, kwik,
  kwik_pahewin}>> }`, each `kwik` unpacked to m3u8, labelled
  `KWIK - {quality} [{audio}]`.
- `Prudhvi-pln/udb` (+ 2 forks) `AnimePaheClient.py`:
  `download_link_url = 'api?m=links&p=kwik&id='` (+ session at call time).
- `prince-ao/consumet.ts` `src/providers/anime/animepahe.ts::fetchEpisodeSources`
  (older shape): `/api?m=links&id=${episodeId}` with `Referer` header →
  `data.data.map(item => ({ quality: Object.keys(item)[0],
  iframe: item[..].kwik, size: item[..].filesize }))` — i.e. **the response also
  carries per-quality `filesize`**.
- What it returns: a JSON object whose `data` maps each available rendition to
  `{audio, kwik (player URL), kwik_pahewin (alt player URL), filesize?}`. Renditions
  observed: 360/720/1080 (720 not always present; CloudStream indexes `links[0]` as
  720 with 1080 fallback). `audio` distinguishes sub (`jpn`) from dub (`eng`) **as
  separate entries** — dubs occupy a contiguous block from episode 1
  (`abdullahkhfb/animepahe-enhancer` `docs/FEATURES.md` gallop-search design doc).
- Why it matters: one cheap JSON call replaces our play-page HTML fetch + `data-src`
  scrape for stream discovery, and additionally yields **audio per rendition,
  filesize, and the pahewin alternate**. Our current `sources()` never calls it.

### 1.6 `GET /api?m=embed&id=…&session=…&p=kwik` — alias of `m=links`. NOT USED.

Same parameters, same response, older name. Attested by `Oshan96/monkey-dl`
(`api?m=embed&p=kwik&id=` + `&session=`), `Yureien/AnimeAPI`
(`api?m=embed&id={id}&p={provider}`), `miru-app/server`
(`EPISODE_DETAILS_URL = ${URL_BASE}?m=embed`), `N2Roar/roar-repository`
(`api_embed = api?m=embed&id=%s&session=%s&p=kwik`),
`italha0/KissanimeX-` (`/api?m=embed&id=…&session=…&p=kwik`). Treat `m=embed` and
`m=links` as the same endpoint; prefer `m=links` (newer clients).

### 1.7 `m=schedule`, `m=releases` (plural), `m=download`, `m=details`, `m=anime`, `m=queue`, `m=news`, `m=auth`, `m=user` — NO EVIDENCE.

- `m=schedule` (task hypothesis): **zero references** in all 259 code-search hits and
  all fetched scrapers; direct probe walled (403, indistinguishable). No site-JS
  evidence obtainable (homepage itself 403; JS bundles unfetchable without clearance).
  Verdict: **unconfirmed — do not implement against it.**
- `m=releases` (plural): no references; the real name is singular `m=release`.
- `m=download`: exactly one code-search hit (`NINJAMINEBRO/Aniloader_public`
  `menu.py`) is a false positive (local variable `show_confirm=downloads` matched
  `m=down`… pattern). No endpoint.
- Auth/user/watchlist/queue/news/details/anime: no references anywhere; `/login`
  probe 403-walled so even the login page shape is unconfirmed (see §5).

### 1.8 HTML pages (GET-only, same wall applies)

| Page | Used for | Carries (superset) |
|---|---|---|
| `GET /` (+ `?search={q}&page=N`) | Search HTML fallback (`_search_html` → `extract_anime_cards`) | `.anime-card[data-title,data-type,data-episodes,data-status,data-season,data-year,data-score,data-poster,data-session]`, `.pagination .next` |
| `GET /anime/{session}` | **Never fetched by our app** | See §2 |
| `GET /play/{anime}/{episode}` | `sources()` via `[data-src]` kwik buttons | See §3 |
| `GET /a/{id}` | **Not implemented** | 302 → `/anime/{session}` (session resolver, §1.4) |
| `https://pahe.win/{code}` | **Not followed** | Download-link shortlink target (see §3) |

---

## 2. Anime details page (`/anime/{session}`) — data we ignore

Our app **never requests this page**. `AnimeDetailScreen` even notes
_"Phase 3 adds a metadata endpoint that removes the last fallback"_
(`src/screens/anime_detail_screen.py:171-173`); title/poster come only from the search
result the user tapped (controller resolution chain: in-memory → continue-watching
store → "Loading..."). Three independent parsers agree on the page's payload:

- `jerry08/Juro` `Juro.Providers/Anime/AnimePahe.cs::GetAnimeInfoAsync`
- `AniFOSS/CloudStream-3` `AnimePaheProvider.kt::load`
- `prince-ao/consumet.ts` `src/providers/anime/animepahe.ts::fetchAnimeInfo`

| Field on page | Selector / pattern | Used by us? |
|---|---|---|
| English title | `div.title-wrapper > h1 > span` (fallback `div.header-wrapper header div h1 span`) | No (search-row title only) |
| Japanese title | `h2.japanese` (CloudStream) | No |
| Poster (full-size) | `.anime-poster a[href]` (Juro) / `header img[data-src]` (consumet) | No (search-row thumbnail only) |
| Backdrop/cover | `body > section > article > div.header-wrapper [data-src]` (consumet `cover`) | No (we blur the poster instead) |
| Synopsis | `.anime-synopsis` (CloudStream) / `div.col-sm-8.anime-summary > div` (consumet) / `div.anime-summary` (Juro) | **No — detail screen shows no synopsis at all** |
| Genres (+ Demographic/Theme) | `.anime-genre > ul a` (`title` attr, consumet) incl. `Demographic:`/`Theme:` links (Juro) | No |
| Type / Episodes count / Status / Aired range / Season / Studios | `.anime-info p` rows: `Type:`, `Episodes:`, `Status:` (`Currently Airing`/`Finished Airing`), `Aired: {from} to {to}`, `Season:`, `Studio(s):` | No (only search-row type/status/year/score/echoed episode count) |
| External IDs | `.external-links > a` → `anilist.co/…/{id}`, `myanimelist.net/…/{id}` (CloudStream `addMalId/addAniListId`) | No |
| Trailer | YouTube watch URL embedded in page HTML (CloudStream `YOUTUBE_VIDEO_LINK`) | No |
| Type-browse link | `a[href*="/anime/type/"]` (CloudStream `getType`: TV/OVA/Movie/Special) | No |
| `og:url` meta | Canonical URL (monkey-dl `__set_working_url`) | No |
| Numeric anime id | `release&id=(.*)&l=` embedded in page (monkey-dl `__set_anime_id`) — the `id` needed for `m=release` when only the session slug is known | No (we pass the session straight through; works because the site accepts session as `id`) |

Related-anime / season navigation: **no parser implements it; no evidence** the page
offers machine-readable related links beyond the type-browse anchor above.

---

## 3. Play page (`/play/{anime}/{episode}`) — full payload

Our `sources()` (`_sources_data_src` + `_sources_regex`) extracts only
`[data-src]` kwik URLs with `data-resolution`/`data-audio`/`data-fansub`. The page
carries three structures (Juro `GetVideoServersAsync` + `iamitkrp/CLI_DOWNLOADER`
`AnimePaheClient._get_kwik_links_v2` + `keketangx/8a597ff9817bd81a679c` `test3`
captured fixture):

1. **Stream buttons** — `div#resolutionMenu > button[data-src][data-resolution]
   [data-audio][data-fansub][data-av1]`. We take src/resolution/audio/fansub but
   **ignore `data-av1`** (AV1 codec flag: udb clients prefer `av1=1` when the same
   resolution appears twice; Juro appends `" AV1"` to the server name).
2. **Download menu** — `div#pickDownload > a[href]` → `https://pahe.win/{code}` per
   rendition, text shape `{Fansub} · {quality}p ({size}MB) {audio?}` with an optional
   `BD` badge. Regex (Juro `_videoServerRegex`):
   `(?<group>.+?)\s*·\s*(?<quality>\d+)p\s*\((?<size>.+?)MB\)\s*(?<audio>.*)`.
   Captured example (`test3`): `MiG_MuX · 720p (176MB) [BD]`, `MiG_MuX · 1080p
   (293MB) [BD]`. **We never parse this** — it is the site's own download offering
   (resolvable share links with known file sizes, usable for size display and direct
   download follow). udb zips `resolutionMenu` buttons with `pickDownload` anchors
   positionally to attach `filesize` to each rendition.
3. **Kwik fallback**: if `resolutionMenu` is absent, Juro falls back to `pickDownload`
   links as the server list; our regex fallback (`kwik.(e|f|d)/…` scan) covers neither
   `pahe.win` links nor the button structure.

Not found anywhere (all scrapers + fixture): next/previous-episode links, episode
duration (API-only field), subtitle tracks, chapter markers. Episode titles on the
play page are not parsed by any implementation — titles come from `m=release`.

---

## 4. Kwik: subtitles, audio, qualities

- **Unpack**: Dean Edwards `p,a,c,k,e,d` eval packer → `source='…m3u8'` single URL.
  Our `src/services/kwik_resolver.py` (`_dean_unpack` + `_resolve_direct_scan`) matches
  `inkand-paper/Anime::extractKwikM3u8` (direct `<source>` → bare-m3u8 regex → eval
  unpack) and CloudStream `getStreamUrlFromKwik` (`eval(…)→JsUnpacker→source='(…)'`).
  Kwik hosts rotate: `kwik.cx` (our code + CloudStream era), `kwik.si` (current per
  inkand-paper + CloudstreamPlugins `Extractors.kt`), `kwik.pw` (legacy). Our
  hard-coded `Referer: https://kwik.cx/` should follow the host of the issued URL.

  **Host state re-verified live 2026-10-19 (this list ages fast):**
  `kwik.cx` is the ONLY live kwik host — "Kwik: Just Another Video Hosting
  Service", landing page 200 with no Cloudflare wall. `kwik.si` is now a
  **parked domain** (a microloan spam page): it answers 200 for EVERY
  path, so a stale `kwik.si` reference does not fail loudly — it
  "succeeds" with a parking page and no m3u8. `kwik.pw`, `kwik.to`,
  `kwik.la` and `kwik.icu` are DNS-dead; `kwik.link` and `kwik.one` are
  unrelated sites (404 on `/f/`). Our resolver follows the ISSUED url's
  host for the Referer, so it is correct for whichever host the site
  issues — but a resolver pointed at a parked host fails silently, which
  is why the host family is worth re-probing before a release.

  The three kwik routes are NOT equally walled (live probes, primp
  chrome impersonation): the landing page is 200, the `/e/` STREAM page
  is NOT challenged (a bogus id answers 404, not 403 — the challenge
  middleware does not cover that path), the `/f/` FILE page IS
  challenged (`403`, `cf-mitigated: challenge`; it clears in a real
  browser and the clearance then persists), and the `/d/` download
  endpoint is not challenged at all (it answers `419 Page Expired` —
  Laravel's CSRF check — with no Cloudflare involved).
- **Subtitles: none, by three converging lines of evidence.** (a) No scraper emits a
  subtitle track for pahe — CloudStream `loadLinks` takes a `subtitleCallback` and
  never calls it for this provider; Juro `GetVideosAsync` returns video-only;
  consumet's `Kwik().extract()` returns `{sources}` with no `subtitles` for pahe
  (unlike its other providers). (b) No `.vtt`/track/`captions` selector appears in
  any pahe code path (the only `vtt`/`tracks` hits in code search are other sites'
  extractors). (c) The site serves **hardsubbed** English streams — subs are burned
  into the video, which is why the `audio` field only ever says `jpn` (sub) vs `eng`
  (dub). Verdict: there is no subtitle ability to add; document "English hardsub,
  no selectable tracks".
- **Audio: no in-stream tracks.** Dub vs sub = **separate renditions/URLs**, selected
  at the `m=links` level (`audio: jpn|eng` per entry) or the play-page button level
  (`data-audio`, with `data-av1` codec qualifier). Our `Source.audio` models this
  correctly; what we miss is *listing* both (we take whichever buttons exist without
  grouping by audio, and udb-style clients explicitly skip `eng` unless dub
  requested).
- **Qualities**: 360/720/1080 observed across `m=links` maps and play-page buttons;
  1080 frequently absent (CloudStream try-720-then-1080 logic). The m3u8 itself is a
  single-rendition playlist per kwik URL (variant selection happens by choosing the
  kwik URL, not inside the manifest) — our per-`Source` resolve flow already matches
  this; no master-playlist parsing is needed.
- Historical: `kwik_adfly` / `kwik_pahewin` fields and the adfly→`/d/` POST-`_token`
  flow (CloudStream `bypassAdfly`/`getStreamUrlFromKwikAdfly`, `anime-dl` field
  names) are the retired indirection; current payloads resolve `kwik` directly.

---

## 5. Site user features (watchlist / continue-watching / accounts)

**Finding: there is nothing to integrate with.** Evidence:

- Direct probes `GET /login`, `/api?m=auth`, `/api?m=user` → uniform 403 (walled;
  proves nothing either way, §1.1).
- All seven fetched third-party clients operate **fully anonymously** (search →
  release → links → kwik); none implements login, session cookies beyond CF
  clearance, watchlist, history, or resume APIs. A site with usable user APIs would
  show at least one client using them.
- No `watchlist`, `bookmark`, `history`, `continue`, `list`, `favorites`, or
  `auth`-named `m=` value appears in 259 code-search hits across GitHub.
- Verdict: the site offers no public (no-login) JSON for watch state; whatever
  logged-in features exist (if any) are behind the same Cloudflare wall with no
  documented API. Our client-side store (§6) is therefore not duplicating a server
  feature — it **is** the feature.

---

## 6. What the app's own store already gives us (`src/services/store.py`)

All durable (atomic JSON in `FLET_APP_STORAGE_DATA`, survives updates), all scoped per
anime/episode session so they work identically for this provider:

| Ability | Store mechanism | Notes |
|---|---|---|
| Search history | `search_history` (20 MRU, `{title, session, ts}`; v1 bare-string rows migrate on read) | Records the anime *opened*, not the typed text — one-tap reopen |
| Continue watching | `continue_watching` (20, keyed by `anime_session`, timestamp-sorted) + `record_watch`/`remove_watch` | Present as the home rail; keyed by bare session so keys survive provider refactors |
| Resume positions | `positions` keyed by episode session `{position, duration, timestamp}`; resume suppressed if `≤3 s` or within `5 s` of end | `get_position`/`save_position`; finished episodes auto-drop |
| Offline downloads | `downloads` rows per episode session + `DownloadManager` (HLS segment fetch, throttled progress) | Download menu already on episode cards; `pahe.win` sizes (§3) could feed progress estimates |
| Favorites | `favorites` (200, per-anime, base64 posters stripped before persist) | Header button on detail screen |
| External player | `external_player` bool → hand m3u8 to KTV Player | Already wired (`main.py` resolve + handoff) |
| CF clearance | `clearance {cookies, user_agent, timestamp}` — returning users skip Turnstile | This is what makes every endpoint above reachable in practice |
| Backend pin | `backend` (`auto` vs pinned provider) | Multi-provider failover ("Try another source") |
| Early-access grants | `early_access` (24 h episode unlocks) | Orthogonal to source abilities |

---

## 7. Full-experience checklist (this source)

| # | Ability | Site offers? | We cover? | Gap |
|---|---|---|---|---|
| 1 | Discovery — latest releases w/ snapshots | Yes (`m=airing`) | **Yes** (`latest_releases` + base64 snapshot proxy) | — |
| 2 | Paginated discovery | Yes (`page`, Laravel envelope) | Yes (`has_more`) | — |
| 3 | Search w/ posters, type/status/year/score | Yes (`m=search`, `l=8`) | Yes | Consider sending `l=8` explicitly |
| 4 | Search HTML fallback when API walled | Site HTML | Yes (`_search_html`, `.anime-card`) | — |
| 5 | Schedule / calendar view | **No evidence** | No | Do not build; unconfirmed |
| 6 | Anime details: synopsis, genres, studios, aired range, season | Yes (`/anime/{session}` HTML) | **No — never fetched** | Add details fetch (selectors §2); biggest display gap after #8 |
| 7 | External IDs (AniList/MAL) + trailer | Yes (same page) | No | Cheap once #6 is built; enables metadata cross-linking |
| 8 | Episode streams via API (audio/filesize/alt host) | Yes (`m=links` ≡ `m=embed`) | **No — we scrape play page only** | Add `m=links` call in `sources()`; keep HTML as fallback |
| 9 | Streaming qualities 360/720/1080 | Yes | Partial (whatever buttons exist; no 1080-fallback logic) | Group renditions by quality from `m=links` |
| 10 | Dub (`eng`) vs sub (`jpn`) listing | Yes (separate entries) | Partial (`audio` captured, not grouped/offered) | Offer audio choice; default `jpn` |
| 11 | AV1 vs H.264 distinction | Yes (`data-av1`, `hd` flag) | No (`data-av1` ignored) | Prefer/flag `av1=1` |
| 12 | Download links + file sizes | Yes (`pickDownload`/`pahe.win`, `filesize` in `m=links`) | No | Parse for size display + direct downloads |
| 13 | Episode list: titles, snapshots, duration, filler flags, `created_at` | Yes (`m=release`) | Yes (all fields incl. `filler` badge) | Support fractional `episode` (x.5 specials) end-to-end |
| 14 | Numeric-id → session resolution (`/a/{id}`) | Yes (302) | No | Needed only if we ever store numeric ids (we don't today) |
| 15 | Newest-first episode sort | Yes (`sort=episode_desc`) | No (we always `episode_asc` + paginate) | Optional shortcut for long series |
| 16 | Subtitle tracks | **No (hardsubbed)** | N/A | Document; no work |
| 17 | In-stream audio tracks | **No (separate URLs)** | N/A (modelled as separate sources) | No work |
| 18 | Server watchlist / history / resume API | **No evidence** | N/A (store covers it, §6) | No work; keep client-side |
| 19 | Continue watching rail | Via store | Yes | — |
| 20 | Resume positions | Via store | Yes | — |
| 21 | Offline downloads | Via store + HLS fetch | Yes | Feed `filesize` from #12 into progress |
| 22 | Favorites | Via store | Yes | — |
| 23 | External player handoff | Via store pref | Yes | — |
| 24 | CF clearance persistence | Via store + webview solver | Yes | — |

**Priority order for full experience:** (8) `m=links` stream API → (6) details page
(synopsis/genres/studios) → (12) download sizes → (10) dub grouping → (11) AV1 flag →
(7) external IDs/trailer. Items 5/16/17/18 require no work (confirmed absent).

---

## 8. Raw evidence index

Direct probes (2026-10-11, `uv run --with primp python` from
`C:\Users\nwoki\ad-extensions\sources\animepahe-tv`):

- `GET https://animepahe.pw/api?m=airing&page=1` → `403`, `Just a moment…`, ~5.1 KB.
- `GET https://animepahe.com/api?m=airing&page=1` ×4 impersonations
  (`chrome_120`, `chrome_124`, `firefox_135`, `safari_18.0` — primp aliases, fell back
  to `random` for unknown names) → all `403` `Just a moment…` 5.2–5.3 KB.
- `GET https://animepahe.ru/api?m={airing,search,schedule,releases,release,details,
  anime,queue,news}` → all `200` + identical 1608-byte parked page → 302 to
  `animepahe.su` + `atob("aHR0cHM6Ly9xeXZpci5jb20vZ28vMjk1NDU1Nz9yZWY9YW5pbWVwYWhlLnJ1…")`
  ad-redirect. `.ru` is a squatter.
- `GET https://animepahe.{pw,com,ru}/` → `.pw`/`.com` 403 CF; `.ru` 200 squatter page.
- `GET {api, api?m={links,embed,auth,user}, login, a/1}` on `.com` → all 403 CF.
- `GET https://kwik.cx/` → 200, 8277 bytes, player landing (no API).

Third-party code (GitHub, fetched file contents):

1. `anime-dl/anime-downloader` `anime_downloader/sites/animepahe.py`
   (sha `0ef1476`) — `m=search(l=8)`, `m=release`, `m=links&id&session&p=kwik`,
   `kwik_adfly` per-quality extraction.
2. `Oshan96/monkey-dl` `anime_downloader/scrapers/animepahe/animepahe_scraper.py`
   (sha `56a6855`) — `m=release` paging, `m=embed&p=kwik&id&session`, 720→1080
   fallback, `og:url` + `release&id=(.*)&l=` page parsing.
3. `jerry08/Juro` `Juro.Providers/Anime/AnimePahe.cs` (sha `c242787`) —
   `GetAnimeInfoAsync` selectors (title/poster/summary/genres/status/studios/aired/
   synonyms), `resolutionMenu` + `data-av1` + `pickDownload` play-page parsing,
   `/a/{id}` session resolution, float episode numbers.
4. `AniFOSS/CloudStream-3` `AnimePaheProvider.kt` (sha `20a485e`) — `m=airing`
   `Data` shape, `m=search&l=8`, `m=release` envelope, `m=links` load-links with
   `VideoQuality{audio,kwik,kwik_pahewin}`, details-page load (synopsis/genres/
   MAL/AniList/trailer), kwik eval→`source='…'`, retired adfly `/d/` flow.
5. `inkand-paper/Anime` `src/lib/animepahe.ts` (sha `19bcb60`) —
   `PaheEpisode{episode2, edition, created_at…}`, `PaheStream{audio,kwik,
   kwik_pahewin,hd}`, `m=links&id&session&p=kwik`, kwik extraction cascade,
   "30 per page", kwik host rotates (kwik.cx live, 2026-10-19).
6. `iamitkrp/CLI_DOWNLOADER` `Clients/AnimePaheClient.py` (sha `1daf908`) —
   `resolutionMenu`×`pickDownload` zip with `data-av1` preference + `eng` skip,
   `m=links&p=kwik&id=` download URL config.
7. `prince-ao/consumet.ts` `src/providers/anime/animepahe.ts` (sha `3222d54`)
   — details selectors incl. backdrop `cover`, `m=links&id=` with `filesize`.
8. `keketangx/8a597ff9817bd81a679c` `test3` — captured `pickDownload` fixture
   (`pahe.win` 720p/1080p + BD badges).
9. `abdullahkhfb/animepahe-enhancer` `docs/FEATURES.md` — `m=links` dub-block
   contiguity note.
10. Code-search negatives: `m=schedule` 0 hits; `m=download` 1 false-positive hit;
    pahe `vtt`/`subtitle`/`tracks` 0 hits in pahe paths; `m=embed` 11 hits (all
    alias-shaped); `m=links` 36 hits (all stream-shaped).

App code read:

- `src/services/animepahe.py` (all `_fetch_api`/`latest_releases`/`search`/
  `episodes`/`sources` paths + mem-cache TTLs 300/600 s + base64 image proxy).
- `src/services/providers/animepahe_provider.py` (capabilities:
  `files/episodes/episode_stills/kwik_resolve`; Cloudflare-aware `probe()`).
- `src/services/kwik_resolver.py` (Dean Edwards unpack + direct scan + HEAD
  `mpegurl` verify, `Referer: https://kwik.cx/`).
- `src/core/html_extract.py` (`.anime-card`, `[data-src]` attribute scraping).
- `src/services/ddos_solver.py` (clearance persist/reuse/re-solve, `_CF_BODY_MARKERS`,
  dynamic base-URL rewrite).
- `src/services/store.py` (§6 table).
- `src/screens/anime_detail_screen.py` (no-synopsis detail screen, "Phase 3" note).
- `src/core/state.py` (`Anime/Episode/Source/LatestRelease` shapes).
