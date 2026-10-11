# Backend reference — AniKato (anikototv.to)

Source: exhaustive live probe of anikototv.to on 2026-10-11. Every claim below has
live evidence in section 4. Site JS analyzed: `main.js?v=1.139` (98,406 bytes),
`comment.js?v=4.0` (30,456 bytes). Probe UA:
`Mozilla/5.0 Chrome/120.0` + `X-Requested-With: XMLHttpRequest` +
`Referer: https://anikototv.to/`.

VRF scheme (confirmed in main.js, `O(t) = btoa(RC4("simple-hash", t))`): the
episode-list VRF is `base64(RC4("simple-hash", anime_id))`. Probes show the
endpoint also answers **without** any vrf (`/ajax/episode/list/355` with no
params returns the same 200 payload), so the VRF is not enforced server-side
today — keep sending it anyway (matches site behavior, future-proof).

Key IDs: numeric anime id lives on `#watch-main[data-id]` (e.g. Dorohedoro S2 =
8679, Appare-Ranman = 355). Numeric episode id (`data-id` on episode `<a>`,
e.g. ep1 = 5765) is required for episode-scoped comment widgets. Watch slugs
look like `dorohedoro-season-2-bqfe6` (`/watch/{slug}`).

---

## 1. Complete endpoint map

### 1a. Anonymous SSR pages (all 200, ~110 KB, 26–30 `.item` cards each)

| Method | Path | Params | Response shape | Evidence |
|---|---|---|---|---|
| GET | `/home` | — | Full homepage: `#hotest`, `#schedule-block`, `#continue-watching`, `#recent-update` widget roots; Top-anime tabs `day/week/month`; recent-update tabs below | homepage nav dump; widget-root probe |
| GET | `/filter` | `keyword`, `genre`, `type`, `sort`, `ep_min`, `ep_max`, `exclude_watchlist`, `page` | SSR grid, same `.item` markup as search; GET form `action=https://anikototv.to/filter` | filter probes §4.1, §4.9 |
| GET | `/new-release` | `page` | SSR grid, 30 items | provider already uses; re-verified pattern |
| GET | `/latest-updated` | `page` | SSR grid, 30 items, maxpage≈300 | §4.1 |
| GET | `/most-viewed` | `page` | SSR grid, 30 items, maxpage≈299 | §4.1 |
| GET | `/az-list`, `/az-list/{letter}` | letter ∈ `A–Z, 0-9, other`; `page` | SSR grid, 30 items (`/az-list` maxpage 299) | §4.1; nav lists all letters |
| GET | `/genre/{slug}` | `page` | SSR grid, 30 items. 60 slugs on homepage nav (action…vampire + `award-winning, isekai, mahou-shoujo, …`). Verified `action`≠`romance` first titles; `?page=2` changes results | §4.1, §4.9 |
| GET | `/type/{t}` | t ∈ `tv, tv-short, tv-special, movie, ova, ona, special, music`; `page` | SSR grid (`movie` maxpage 44) | §4.1 |
| GET | `/status/{s}` | s ∈ `currently-airing, finished-airing, not-yet-aired`; `page` | SSR grid (`finished-airing` maxpage 292) | §4.1 |
| GET | `/schedule` | — | SSR shell only (40 KB, 0 items); real data loads via ajax below | §4.1 |
| GET | `/random` | — | 302-style redirect to a random `/watch/{slug}` (final URL `…/watch/mobile-suit-gundam-the-08th-ms-team-miller-0awca`, 200, watch-page HTML) | §4.1 |
| GET | `/watch/{slug}` | — | Watch page: `#watch-main[data-id, data-url]` + schema.org Movie; inline synopsis; `Genres:/Status:/Type:/Premiered:/Duration:/Studios:/Producers:` info block; `api/seasons/{id}` bootstrap; `#downloadModal` shell + `openDownloadModal` (base64-JSON `download-data`); `#w-report-form action=/ajax/episode/report` with `show_id/show_slug`; disqus comments; `rated` star widget | §4.6, §4.7 |
| GET | `/watch2gether` | — | 200 landing page (63 KB, title `Watch2Gether`) | §4.1 |
| GET | `/community/board`, `/community/live` | — | 200 discussion board (50 KB) — community, out of scope for a watch app | §4.1 |
| GET | `/api/seasons/{anime_id}` | — | 200 JSON `{status:200, result:"<section id=w-seasons>…"}` — season swiper cards (`Season 1` → `/watch/dorohedoro-om2ua`, bg-image posters) injected into `#ani-seasons` | §4.8 |

Filter form inputs actually present on `/filter` (radio/number/text/hidden scan):
`sort` ∈ `default, latest-updated, latest-added, score, name-az, release-date,
most-viewed, number_of_episodes`; `type` (radio, value stub `''` in SSR — real
options render client-side); `ep_min`, `ep_max` (number inputs); `keyword`;
`exclude_watchlist=1`. Verified working: `?genre=action&type=tv` → first title
`Dragon Ball Super: Beerus`; `?sort=score` → first title `Dorohedoro Season 2`.

### 1b. Anonymous AJAX (all GET, 200, no login needed)

| Method | Path | Params (per main.js) | Response shape | Evidence |
|---|---|---|---|---|
| GET | `/ajax/episode/list/{anime_id}` | `style=list\|grid`, `vrf` (both optional today) | 200 `{status:200, result:"<div class=head>…<a data-id data-num data-slug data-mal data-timestamp data-sub data-dub data-ids>…"}` — per-episode meta: MAL id, unix timestamp, sub/dub flags (`data-sub="1" data-dub="1"`), `data-ids` server token | §4.2, §4.5 |
| GET | `/ajax/server/list` | `servers={data-ids token}` | 200 `{status:200, result:"<div class=tip>You're watching Episode N…<div class=servers><div class=type data-type=sub\|dub><li data-ep-id data-cmid data-sv-id data-link-id>HD-1…"}` — 8 links observed (4 SUB + 4 DUB: `s=tcdn`, bare, `videojs/`, `s=bcdn` flavors of one realid) | §4.5 |
| GET | `/ajax/server` | `get={data-link-id}` | 200 `{status:200, result:{url:"https://megaplay.buzz/[videojs/]stream/s-2/{realid}/{sub\|dub}[?s=tcdn\|bcdn]", skip_data:{intro:[171,261], outro:[1340,1430]}}}` — skip_data is per-episode intro/outro in **seconds** | §4.5 |
| GET | `/ajax/anime/search` | `keyword` (JS sends `["data",["keyword",e]]`; plain `?keyword=` works) | 200 `{status:200, result:{html:"<div class=scaff items><a class=item href=/watch/…><img src=cdn.anipixcdn…>", linkMore}}` | §4.2 |
| GET | `/ajax/anime/tooltip/{anime_id}` | — (`data-tip` attr value) | 200 `text/html` hover card: title, JP title, rating/quality, SUB+total ep counts, synopsis, other-names, score, year, duration, status, genres | §4.2, §4.9 |
| GET | `/ajax/schedule` | `tz` (hours offset, e.g. `0`) | 200 `{status:200, result:"<section id=schedule>…"}` with 7 `data-time` day tabs (epoch days `1791158400…`) | §4.2, §4.9 |
| GET | `/ajax/schedule/date` | `tz`, `time` (= one `data-time` value) | 200 `{status:200, result:"<div class=items><a class=item href=/watch/…/ep-N?type=sub><div class=time data-tip=id>02:00…"}` — per-day airing list with times + episode links | §4.9 (empty-result shape with bad time: `<div class=items></div><div class=more></div>`) |
| GET | `/ajax/schedule/page` | `tz` | 200 `{status:200, result:"<section id=schedule class=sc-root>…Weekly Schedule…Mon 5 Oct – Sun 11 Oct…"}` | §4.2 |
| GET | `/ajax/schedule/page/date` | `tz`, `time` | Same family as `/ajax/schedule/date` (SchedulePage widget; not separately probed, same params per main.js) | main.js `SchedulePage.$i` |
| GET | `/ajax/home/widget/{name}` | `page` | 200 `{status:200, result:"<div class=ani items>…"}` for `updated-sub, updated-dub, updated-all, random, trending` (~14.5 KB each). Empty (`<div class=ani items></div>`, 68 B) for `new-release, new-added, completed, top_airing, most_viewed` — these tab names exist in home markup but the backend returns nothing for them | §4.4 |
| GET | `/ajax/user/search` | `keyword` | 200 `{status:200, result:{html:"<div class=scaff items><a class=item ak-uhit href=/user/…/profile>…avatar…"}}` — **user directory search**, not anime | §4.3 |
| GET | `/auth/ajax/user/panel` | — | 200 `{status:200, result:{html:"<a href=#sign …Sign in…", user:{id:0, settings:[]…}}}` — anonymous session state | §4.3 |
| GET | `/ajax/comment/widget/{show_id}` | `episodeId` (numeric ep id, required), `sort=top\|newest`, `type=episode\|show`, `page`, `list=1` | 200 `{status:true, nextPage, html:"<div class=cm-rules-note…rentry.co/anik…comments…"}`; without episodeId: `{status:false, msg:"episodeId is required for episode comments."}` | §4.10 |
| GET | `/ajax/comment/replies/{id}` | — | Per comment.js: `ajax/comment/replies/"+id` → `{status, html}` appended to `#replies-{id}` | comment.js (not live-probed; shape from JS) |
| GET | `/ajax/comment/gif-search` | `q` | Per comment.js → `{status, items:[{preview\|url…}]}` Tenor-style picker | comment.js (live probe returned empty/ERR — likely needs session; treat as auth-adjacent) |
| GET | `/ajax/reactions/list` | `type`, `id` | Live: `{status:false, msg:"Invalid target.", items:[]}` for `type=show&id=8679` — valid route, strict target vocabulary (scope values live in JS) | §4.10 |
| GET | `/ajax/watch2gether/chat/list/{room_id}` | `page` | **200 anonymous**: `{status:200, result:{html:"<div class=message><div class=avatar><img …>", messages…}}` — public room chat is readable without login | §4.8 |
| GET | `/check-server` | `manga_id={anime_id}` | 200 `{status:500, purged:false, message:"Failed to purge cache."}` — internal cache-purge ping fired by watch pages, not app-useful | §4.6 |

Episode-list entry attributes (full): `data-id` (ep id), `data-num`,
`data-slug`, `data-mal`, `data-timestamp`, `data-sub`, `data-dub`, `data-ids`.
`style=list` and `style=grid` returned **identical** HTML (9090 B) — the style
distinction is client-side CSS only.

### 1c. Authenticated AJAX (all verified to reject anonymous; app needs login/session to use)

Watchlist / favourites (per main.js `UserFavourite`, `UserWatchStatus`,
`ManageFolders`):

| Method | Path | Params | Anonymous result |
|---|---|---|---|
| GET | `/ajax/user/favourite/get/{anime_id}` | — | 200 `{status:200, result:0, message:"User not logged in."}` |
| POST | `/ajax/user/favourite/save` | `id, folder, _csrfToken` | 200 `{status:500, result:false, message:"User not logged in."}` |
| POST | `/ajax/user/favourite/status` | `id, unwatched (0/1), _csrfToken` | 401 `{status:401, result:false, message:"User not logged in."}` (watched/unwatched toggle) |
| GET | `/ajax/user/folder/list` | — | **404 HTML error page** (route only exists in authed context) |
| POST | `/ajax/user/folder/save` | `id (0=new), name` | 404 HTML (same) |
| POST | `/ajax/user/folder/sort` | `orders[id]=pos` | 404 HTML (same) |
| POST | `/ajax/user/folder/delete` | `id` | 404 HTML (same) |

Continue-watching / resume (per main.js `Visitor.xe/ke/Se`, `UserPlayingRemove`,
`UserPlayingClear`, `HomeContinueWatching`):

| Method | Path | Params | Anonymous result |
|---|---|---|---|
| POST | `/ajax/user/playing/save` | `playing` (localStorage `user.playing` blob flushed every 5 s), `_csrfToken` | `{status:500, result:false, message:"User not logged in."}` |
| GET | `/ajax/user/playing/get/{anime_id}` | — | 401 `{status:401, result:null, message:"User not logged in."}` |
| POST | `/ajax/user/playing/delete` | `id, _csrfToken` | `{status:500, result:0, message:"User not logged in."}` |
| POST | `/ajax/user/playing/clear` | `req_id (random), vrf=O(req_id), _csrfToken` | `{status:500, result:false, message:"User not logged in."}` |
| GET | `/ajax/user/playing/widget/home` | — | `{status:500, result:{html:""}, count:""}` — home Continue-Watching rail only renders when `200 && count` |

Notifications (per main.js `Notification` widget):

| Method | Path | Params | Anonymous result |
|---|---|---|---|
| GET | `/ajax/notification/panel` | — | 404 HTML |
| POST | `/ajax/notification/update` | `action=mark_as_read, ids[], _csrfToken` | 404 HTML |

Rating / skip-times (per main.js `Rating.an`, `SkipTime.B`):

| Method | Path | Params | Anonymous result |
|---|---|---|---|
| POST | `/ajax/anime/rate` | `id, score, req_id (=M()), vrf=s(id@score@req_id)`; GET → 404 | GET 404; POST shape from JS (not POSTed live — GET-only probe rule; route exists, POST-only) |
| POST | `/ajax/episode/skiptime/save` | `intro/outro name+value pairs, id, vrf=s(values)`; GET → 404 | GET 404; POST-only, moderator-oriented ("Please fill at least intro or outro.") |

Episode reports (form on every watch page; POST-only, **works without login**):

| Method | Path | Params | Anonymous result |
|---|---|---|---|
| POST | `/ajax/episode/report` | `show_id, episode_id, server_name, show_slug, issue[] ∈ {video_broken, audio_sync, sub_sync, skiptime}, note` | `{status:false, msg:"Missing show id."}` (empty) → `{status:false, msg:"Pick at least one issue or add a note."}` (with ids) — validation reachable anonymously; quota 5/day in localStorage |

Comments write path (comment.js; all need login + `_csrfToken`):
`ajax/comment/add`, `/edit`, `/update` (hide/spoil actions), `/vote`,
`/report`, `/comments/togglePin`, `ajax/reactions/toggle` (POST
`{catalog_id, type, scope, id}`). Live: `comment/add` → `{status:false,
msg:"You must be logged in to comment."}`.

Watch2Gether write path (all 401 anonymous): `room/start` (`{id,
vrf=O(id)}`), `room/end`, `room/change` (`{id, episode}`), `chat/save`
(`{room_id, content, vrf=O(room_id+content)}`, → `{status:401, result:false,
message:"Login required"}`). Read path `room/episodes/{room}/{show}` →
`{status:200, result:""}` (empty for bogus ids; real shape needs a live room).

### 1d. Stream backend (megaplay.buzz) — full `getSources` shape

`GET https://megaplay.buzz/stream/getSources?id={realid}&type={sub|dub}[&s=tcdn|bcdn]`
(headers `X-Requested-With: XMLHttpRequest`, `Referer: megaplay.buzz/`). The
`videojs/stream/getSources` variant answers identically. `s=tcdn`, bare, and
`s=bcdn` return the **same** payload for id 24855 — `s` is a CDN-preference
hint, not a different source.

Response keys: `tracks, t, intro, outro, server, enc`. Observed (id 24855):

- `t: 1` — opaque; constant `1` across sub/dub and all `s` values. Most likely
  a provider/type flag (not a token — too small, never varies). Do not send it
  anywhere; nothing in main.js reads it as input.
- `intro: {start:0, end:89}`, `outro: {start:0, end:0}` — skip windows in
  **seconds**, coarser than the site-level `skip_data` (`intro:[171,261],
  outro:[1340,1430]`, same units). Prefer `skip_data` when present; fall back
  to these.
- `server: 4` — numeric mirror/pool id.
- `enc` — AES-256-CBC token → `{"file": master.m3u8}` (existing decrypt path).
- `tracks` — **9 subtitle tracks**, each `{file, label, kind:"captions",
  [default:true]}`: Arabic, English (default), French, German, Italian,
  Portuguese, Portuguese(Brazil), Russian, Spanish, Spanish(Latin America).
  `file` pattern:
  `https://{mirror}.broforgotsave.online/anime/{hash1}/{hash2}/subtitles/{lang}-{n}.vtt`
  — **WebVTT**, verified `WEBVTT` header bytes. Direct GET without Referer →
  403 Cloudflare page; **with `Referer: https://megaplay.buzz/` → 200
  `application/octet-stream`, 5,029 bytes of valid cues**. App must attach the
  megaplay Referer to subtitle fetches (same as stream).

### 1e. Explicitly absent / negative findings

- **Episode thumbnails: NO.** Episode-list HTML (`list` and `grid`) contains
  zero `<img>` elements — entries are number links with metadata only. No
  `thumb/snapshot/poster` strings anywhere in the payload. (Provider's
  `capabilities["episode_stills"] = True` is satisfied only by reusing the
  show poster — see §3.)
- **Trailer/characters/related DOM blocks: NO** on watch pages (only JS
  residue: sequel/prequel coloring via `api/seasons`, `Sequel/Prequel` label
  logic). No trailer video endpoint exists.
- **Download links: modal shell only.** `#downloadModal`/`#downloadModalBody`
  exist but no `download-data=` attribute is rendered for anonymous SSR, and
  no trigger element calls `openDownloadModal` in SSR HTML — the payload
  (base64 JSON `[{name, url}]`) is injected at runtime after episode/server
  selection. No direct-download endpoint to map; downloads = the m3u8 itself.
- `ajax/user/panel` (non-auth path in main.js) is superseded by
  `auth/ajax/user/panel`; `ajax/user/folder/*` and `ajax/notification/*`
  404 for anonymous (routes exist only behind login).

---

## 2. Abilities our app should ship for this source

The full-experience checklist — each item names the endpoint(s) that power it:

**Discovery / browse**
- [ ] Search with live suggestions — `ajax/anime/search?keyword=` (html +
  `linkMore`) instead of only SSR `/filter?keyword=` (faster, prefix-friendly)
- [ ] New releases — `/new-release?page=` (already have)
- [ ] Recently updated rail — `ajax/home/widget/updated-{sub,dub,all}?page=`
  (SUB/DUB split the site itself offers; SSR `/latest-updated` as fallback)
- [ ] Trending / random rails — `ajax/home/widget/trending`, `…/random`
- [ ] Most viewed — SSR `/most-viewed?page=` (widget name exists but returns
  empty — do NOT use the widget)
- [ ] A–Z browser — `/az-list/{letter}?page=` (30/page, ~299 pages deep)
- [ ] Airing calendar — `ajax/schedule?tz=` (7 day tabs) +
  `ajax/schedule/date?tz=&time=` (per-day times + direct `/watch/…/ep-N` links)
- [ ] Full weekly schedule page — `ajax/schedule/page` + `/page/date`
- [ ] Surprise-me — `/random` (follows redirect to `/watch/{slug}`)

**Filter / genres**
- [ ] Genre grid — `/genre/{slug}?page=` (60 genres; multi-genre via
  `/filter?genre=` is verified working)
- [ ] Type filter — `/type/{tv,movie,ova,ona,special,music,…}?page=`
- [ ] Status filter — `/status/{currently-airing,finished-airing,not-yet-aired}?page=`
- [ ] Advanced filter — `/filter?genre=&type=&sort=&ep_min=&ep_max=&page=`
  with all 8 sorts (`default, latest-updated, latest-added, score, name-az,
  release-date, most-viewed, number_of_episodes`)

**Details**
- [ ] Rich detail screen — watch-page SSR (synopsis, Genres/Status/Type/
  Premiered/Duration/Studios/Producers info block, MAL score) — provider
  currently takes only poster/title/synopsis
- [ ] Hover/quick-view cards — `ajax/anime/tooltip/{id}` (title, JP title,
  scores, ep counts, genres — cheap, cacheable)
- [ ] Seasons / franchise navigation — `api/seasons/{anime_id}` (swiper cards
  with posters + slugs; also carries Sequel/Prequel/Parent-story relations)
- [ ] Community rating display — `rated` star widget state on watch page
  (read-only without login)

**Episodes**
- [ ] Episode list with SUB/DUB availability badges — `data-sub/data-dub`
  flags per entry (already fetched, currently discarded)
- [ ] Episode air dates — `data-timestamp` per entry (already fetched,
  currently discarded)
- [ ] MAL cross-link — `data-mal` per entry
- [ ] NO per-episode thumbnails exist — show poster is the only artwork;
  do not build UI expecting thumbs from this source

**Playback**
- [x] SUB + DUB streams — 8 server links → megaplay (already have)
- [ ] Multi-mirror fallback — `s=tcdn` vs bare vs `s=bcdn` vs `videojs/`
  flavors (same content today, different infra — rotate on failure)
- [ ] Subtitles — `tracks[]` WebVTT (9 langs, English default); fetch with
  `Referer: https://megaplay.buzz/` or expect 403
- [ ] Skip intro/outro — `skip_data.intro/outro` (seconds, per-episode, from
  `/ajax/server?get=`) with `getSources.intro/outro` as fallback
- [ ] Downloads — direct m3u8 persists (no separate download endpoint; the
  site's own modal just links stream URLs)
- [ ] Report-broken-stream — `POST /ajax/episode/report` (works anonymously,
  5/day quota) — optional day-one differentiator

**Cloud / social (require user login — post-MVP, needs session + CSRF)**
- [ ] Cloud resume sync — `user/playing/save + get/{id}` (5 s flush loop)
- [ ] Continue-watching rail — `user/playing/widget/home`
- [ ] Watchlist folders — `favourite/{get,save,status}` + `folder/{list,save,sort,delete}`
- [ ] Notifications — `notification/{panel,update(mark_as_read)}`
- [ ] Star rating submit — `anime/rate` (VRF `s(id@score@req_id)`)
- [ ] Skip-time contribution — `episode/skiptime/save`
- [ ] Comments read — `comment/widget/{show}?episodeId=&sort=&type=` (anonymous OK);
  write/vote/react/pin — login
- [ ] Watch2Gether — public chat readable anonymously (`chat/list/{room}`),
  everything else (start/end/change/chat-save) needs login
- [ ] User search — `ajax/user/search` (people, not anime)

---

## 3. What our current provider covers vs misses

Read: `sources/animepahe-tv/src/services/providers/anikato.py` (428 lines).

**Covered (working, verified patterns re-confirmed live):**
- Catalog via SSR `/filter?keyword=` + `/new-release?page=` (`_parse_items`,
  `#list-items > .item`) — still valid markup.
- Watch page id/poster/title/synopsis (`_parse_watch`) — selectors still match
  (`#watch-main[data-id]`, `itemprop=image/name`, synopsis content div).
- Episode list via `/ajax/episode/list/{id}?style=list&vrf=` (`_parse_episode_list`).
- Server groups SUB/DUB (`_parse_servers`), link resolve (`/ajax/server?get=`),
  megaplay params, AES decrypt → master m3u8 (`_manifest_for`,
  `_decrypt_manifest`).
- Skip data is fetched (`t.result.skip_data` read in site JS) but **dropped**
  in `_resolve_link` — only `(realid, kind, s)` is kept.

**Misses / gaps (ordered by value):**
1. **Subtitles dropped** — `_manifest_for` reads only `enc`; the same
   `getSources` JSON carries 9 WebVTT `tracks` (English default). Biggest
   playback gap.
2. **Skip-intro dropped** — `skip_data` (`intro:[171,261],
   outro:[1340,1430]`) discarded; `getSources.intro/outro` fallback also
   unread. Both skipped in favor of returning bare manifests.
3. **Source model lossy** — 8 server links (tcdn/bare/videojs/bcdn × sub/dub)
   collapse to one `Source` per link with `resolution=0`; no mirror/fallback
   ordering, no `tracks`/`skip` attached to `Source`.
4. **Episode metadata discarded** — `data-sub/data-dub` (dub-availability
   badge), `data-timestamp` (air date), `data-mal` parsed nowhere; `Episode`
   gets `title="Episode N"`, `snapshot=poster` (no thumbs exist — that part is
   fine, but the flags/dates are free).
5. **Details thin** — only poster/title/synopsis; the info block
   (Genres/Status/Type/Premiered/Duration/Studios/Producers/MAL score),
   tooltip cards, and `api/seasons/{id}` franchise nav are unparsed.
6. **Discovery surface unused** — no az-list/genre/type/status/most-viewed/
   latest-updated/schedule/widget/random entry points; search is SSR-only
   (no `ajax/anime/search` suggestions); no `sort=` support.
7. **VRF unnecessarily strict-looking** — code treats vrf as required; live
   probes show the endpoint answers with no vrf at all. Keep sending it, but
   a vrf failure should fall back to a bare retry rather than hard-fail.
8. **Cloud features absent** — expected (need login), but the route map (§1c)
   means resume/watchlist/notifications can be layered later without
   re-mapping; `playing/save` flush loop and `widget/home` shapes are known.
9. **`capabilities["episode_stills"] = True`** is misleading — no stills
   exist; it reuses the poster. Rename or document so UI doesn't expect thumbs.

---

## 4. Raw evidence

All probes: `httpx.Client(timeout=30, follow_redirects=True)`, headers
`UA=Mozilla/5.0 Chrome/120.0`, `X-Requested-With: XMLHttpRequest`,
`Referer: https://anikototv.to/`. Truncation marker `::` = first ~200–300 chars
of body with newlines flattened.

### 4.1 SSR pages

```
/az-list                 -> 200 text/html len=114451 items=30 maxpage=299 title='AZ-List - Anikoto'
/genre/action             -> 200 text/html len=117325 items=30 maxpage=117 title='Action Anime - Watch Online with SUB, DUB - Anikoto'
/type/movie               -> 200 text/html len=115245 items=30 maxpage=44  title='Movies - Anikoto'
/status/finished-airing   -> 200 text/html len=116531 items=30 maxpage=292 title='Finished airing Anime - Anikoto'
/most-viewed              -> 200 text/html len=117528 items=30 maxpage=299 title='Most Viewed - Anikoto'
/latest-updated           -> 200 text/html len=112254 items=30 maxpage=300 title='Recently Updated - Anikoto'
/schedule                 -> 200 text/html len=40523  items=0  maxpage=0   title='Weekly Schedule - Anikoto'
/filter?keyword=naruto    -> 200 text/html len=112158 items=26
/filter?type=movie&genre=action&page=1 -> 200 items=30
/az-list/0-9, /status/currently-airing, /type/ova -> 200, 30 items each
/random                   -> 200 final=https://anikototv.to/watch/mobile-suit-gundam-the-08th-ms-team-miller-0awca (watch HTML)
/watch2gether             -> 200 len=63405 title='Watch2Gether'
/community/board           -> 200 len=50111 title='Discussion Board - Anikoto'
```

### 4.2 Core AJAX (anime_id 355 = Appare-Ranman)

```
GET /ajax/episode/list/355?style=list&vrf=JNGt -> 200 application/json len=9835
  {"status":200,"result":"\n <div class=\"head\">…dropdown…"}
GET /ajax/episode/list/355 (no params)        -> 200 identical payload (vrf NOT enforced)
GET /ajax/anime/tooltip/355                   -> 200 text/html len=1581
  <div class="title d-title" data-jp="Appare-Ranman!"> APPARE-RANMAN! </div> <div class="meta d-flex">…<i class="rating">PG-13</i>…
GET /ajax/anime/search?keyword=naruto         -> 200 application/json len=3456
  {"status":200,"result":{"html":"<div class=\"scaff items\"> <a class=\"item\" href=\"https://anikototv.to/watch/naruto-eybxz\">…<img src=\"https://cdn.anipixcd…
GET /ajax/schedule?tz=0                       -> 200 application/json len=12997
  {"status":200,"result":"<section id=\"schedule\">\n <div class=\"head\">\n <div class=\"title\">Estimated Schedule…
GET /ajax/schedule/page?tz=0                  -> 200 len=25193 …"Weekly Schedule</div><div class=\"sc-sub\">Mon 5 Oct – Sun 11 Oct · your timezone</div>…
```

### 4.3 Identity / user-search (anonymous)

```
GET /ajax/user/search?keyword=test -> 200 {"status":200,"result":{"html":"<div class=\"scaff items\"><a class=\"item ak-uhit\" href=\"https://anikototv.to/user/009ppe/profile\"><span class=\"ak-uhit-ava\"><img src=\"https://static.anipixcdn.co/anikoto/images/ava…
GET /auth/ajax/user/panel          -> 200 {"status":200,"result":{"html":"<a href=\"#sign\" data-toggle=\"modal\" class=\"sign-in…","user":{"id":0,"settings":[],…
GET /ajax/user/favourite/get/355   -> 200 {"status":200,"result":0,"message":"User not logged in.","messages":["User not logged in."]}
GET /ajax/user/playing/widget/home -> 200 {"status":500,"result":{"html":""},"count":""}
```

### 4.4 Home widgets (`GET /ajax/home/widget/{name}?page=1` → 200 each)

```
updated-sub  len=14589 {"status":200,"result":"<div class=\"ani items\">\n <div class=\"item\">\r\n <div class=\"ani poster\" data-tip=\"9040\">…
updated-dub  len=14723 (same shape, data-tip="8800")
updated-all  len=14589 | random len=14458 | trending len=14782 (all populated)
new-release, new-added, completed, top_airing, most_viewed -> len=68 {"status":200,"result":"<div class=\"ani items\">\n </div>"} (EMPTY)
```

Home tabs present in markup: `completed, day, month, new-added, new-release,
random, trending, updated-all, updated-dub, updated-sub, week`.

### 4.5 Episode → server → megaplay chain (anime 355, ep1)

```
style=list vs style=grid -> identical (len=9090, 0 <img>, 13 data-num entries)
ep1 entry: <a href="#" data-id="5765" data-num="1" data-slug="1" data-mal="40532" data-timestamp="1729192521" data-sub="1" data-dub="1" data-ids="N2VnV3NSQ1…" class="active">
GET /ajax/server/list?servers={ids} -> 200 len=3333 …You're watching <b>Episode 1</b>…<div class="type" data-type="sub">…<li data-ep-id="5765" data-cmid="animixplay-fqsqfvdf4u" data-sv-id="323" data-link-id="MTF1…">HD-1</li> (8 links: types [sub, dub])
GET /ajax/server?get={link} x8 -> all status=200:
  megaplay.buzz/stream/s-2/24855/sub?s=tcdn | …/sub (bare) | …/videojs/stream/s-2/24855/sub | …/sub?s=bcdn
  …/dub?s=tcdn | …/dub (bare) | …/videojs/…/dub | …/dub?s=bcdn
  each skip="{'intro': [171, 261], 'outro': [1340, 1430]}"
```

### 4.6 getSources + subtitles + check-server

```
GET megaplay.buzz/stream/getSources?id=24855&type={sub,dub}&s={tcdn,'',bcdn} -> 200 ×6, keys=[tracks,t,intro,outro,server,enc], enc_len=171
  t='1', server=4, intro={'start':0,'end':89}, outro={'start':0,'end':0}, autoplay=None
  tracks = 9 × {file, label, kind:"captions"}: Arabic, English(+default), French, German, Italian, Portuguese, Portuguese(Brazil), Russian, Spanish, Spanish(Latin America)
  file e.g. https://6a8y6.broforgotsave.online/anime/25da78139c03b69098a5fa566a61b115/9c61491607b307195177424f30376f45/subtitles/eng-2.vtt
GET subtitle (UA only)            -> 403 text/html (Cloudflare, len=4555)
GET subtitle + Referer megaplay  -> 200 application/octet-stream len=5029 :: WEBVTT 00:00:00.000 --> 00:00:06.190 Productivity 00:00:23.120 --> 00:00:33.720 It's Me, Kawashiri Kodama…
GET videojs/stream/getSources?id=24855&type=sub -> 200, same tracks shape
GET /check-server?manga_id=355   -> 200 {"status":500,"purged":false,"message":"Failed to purge cache."}
```

### 4.7 Watch page (slug `dorohedoro-season-2-bqfe6`, anime_id 8679)

```
GET /watch/dorohedoro-season-2-bqfe6 -> 200 len=81475
<div id="watch-main" … data-id="8679" data-url="https://anikototv.to/watch/dorohedoro-season-2-bqfe6" … itemscope itemtype="https://schema.org/Movie">
PRESENT: Genres: Status: Type: Premiered: Duration: Studios: Producers: detail-seasons(js) Sequel Prequel comments disqus rated data-tip
ABSENT: trailer Trailer Characters Related MAL Score Synopsis(#-anchor) seasons-HTML-class
SYN-ctx: mb-3"> The second season of Dorohedoro. … [more] Type: ONA Premiered: SPRING 2026 Aired: Apr 1, 2026 to ? Status: Finished Airing Genres: Action, Adventure, Fantasy, Comedy, Seinen, Mystery, Horror MAL: 9.75 Duration: 23 min Episodes: 11 Studio…
META title: 'Dorohedoro Season 2'; poster: https://cdn.anipixcdn.co/thumbnail/2fca89aef2c792cb67c316a669ffe591.jpg
Report form: <form id="w-report-form" action="/ajax/episode/report" method="POST"> + hidden show_id=8679, show_slug, episode_id, server_name + issue[] ∈ {video_broken, audio_sync, sub_sync, skiptime}
Download: modal shell #downloadModal/#downloadModalBody only; openDownloadModal(a) reads base64-JSON download-data attr; NO trigger element in anonymous SSR
```

### 4.8 Seasons API, chat, misc

```
GET /api/seasons/8679 -> 200 application/json len=1630
  {"status":200,"result":"…<section id=\"w-seasons\"…<div class=\"swiper-slide season \"> <a href=\"https://anikototv.to/watch/dorohedoro-om2ua\" style=\"background-image: url(https://cdn.anipixcdn.co/thumbnail/dc912a….jpg);\"> <div class=\"name\">Season 1</div></a>…"}
GET /ajax/watch2gether/chat/list/1?page=1 -> 200 {"status":200,"result":{"html":"<div class=\"message\">\n <div class=\"avatar\">\n <img src=\"https://static.anipixcdn.co/anikoto/images/avatar/dragon_ball/av-db-01.jpeg\" alt=\"Ebenus\">…
GET /ajax/watch2gether/room/episodes/1/355  -> 200 {"status":200,"result":""}
```

### 4.9 Filter / tooltip / schedule-date

```
GET /filter (form scan): sort ∈ {default, latest-updated, latest-added, score, name-az, release-date, most-viewed, number_of_episodes}; inputs ep_min, ep_max, keyword, exclude_watchlist=1; <form method="get" action="https://anikototv.to/filter">
GET /filter?genre=action&type=tv -> 200 first title 'Dragon Ball Super: Beerus'; ?sort=score -> first 'Dorohedoro Season 2'
GET /genre/action?page=2 -> 200 first 'High School DxD BorN' (pagination works)
GET /ajax/anime/tooltip/8679 -> 200 text/html len=2125: title+data-jp, rating R, HD, sub 11/total 11, synopsis, Other names, Scores 9.75, Year 2026, Duration 23 min, Status Finished Airing, Genre links /genre/…
GET /ajax/schedule?tz=0 data-times: [1791158400, 1791244800, 1791331200, 1791417600, 1791504000, 1791590400, 1791676800]
GET /ajax/schedule/date?tz=0&time=1791158400 -> 200 {"status":200,"result":"<div class=\"items\"><a class=\"item\" href=\"https://anikototv.to/watch/renegade-immortal-ogxqp\/ep-161?type=sub\">\n <div class=\"time\" data-tip=\"6398\">02:00</div>…"}
```

### 4.10 Comments / reactions

```
GET /ajax/comment/widget/8679?episodeId=5765&sort=top&type=episode -> 200 len=9326 {"status":true,"nextPage":null,"html":"<div class=\"cm-rules-note alert…Note:</strong> Please take a moment to read the <a href=\"https://rentry.co/anik…"}
…?episodeId=0… -> 200 {"status":false,"msg":"episodeId is required for episode comments.","errors":[…]}
POST /ajax/comment/add -> 200 {"status":false,"msg":"You must be logged in to comment.","errors":[…]}
GET /ajax/reactions/list?type=show&id=8679 -> 200 {"status":false,"msg":"Invalid target.","items":[]}
comment.js ajax surface: comment/{add, edit, replies/, report, update, vote, gif-search, widget/}, comments/togglePin, reactions/{list, toggle}
```

### 4.11 Auth-gated POSTs (all unauthenticated → clean auth errors, JSON unless noted)

```
POST /ajax/user/playing/save       -> 200 {status:500,result:false,message:"User not logged in."}
GET  /ajax/user/playing/get/8679   -> 401 {status:401,result:null,message:"User not logged in."}
POST /ajax/user/playing/delete     -> 200 {status:500,result:0,message:"User not logged in."}
POST /ajax/user/playing/clear      -> 200 {status:500,result:false,message:"User not logged in."}
POST /ajax/user/favourite/save     -> 200 {status:500,result:false,message:"User not logged in."}
POST /ajax/user/favourite/status   -> 401 {status:401,result:false,message:"User not logged in."}
POST /ajax/episode/report (empty)  -> 200 {"status":false,"msg":"Missing show id."}
POST /ajax/episode/report (ids)    -> 200 {"status":false,"msg":"Pick at least one issue or add a note."}
GET  /ajax/episode/report          -> 405 Error page (POST-only)
POST /ajax/watch2gether/{room/start,room/end,room/change,chat/save} -> 401 {status:401,result:false} (+ "Login required" on chat/save)
POST /ajax/notification/update, GET /ajax/notification/panel, */user/folder/* (anon) -> 404 Error HTML (authed-only routes)
GET  /ajax/anime/rate, GET /ajax/episode/skiptime/save -> 404 Error HTML (POST-only; rate needs id,score,req_id,vrf=s(id@score@req_id); skiptime needs intro/outro pairs + vrf)
```

main.js call shapes (exact params for future authed work):
`favourite/save{ id, folder, _csrfToken }`, `favourite/status{ id, unwatched,
_csrfToken }`, `playing/save{ playing, _csrfToken }` (POST),
`playing/delete{ id, _csrfToken }`, `playing/clear{ req_id: 100*random(),
vrf: O(req_id), _csrfToken }`, `room/start{ id, vrf: O(id) }`,
`room/change{ id, episode }`, `chat/save{ room_id, content, vrf:
O(room_id+content) }`, `folder/save{ id|0, name }`, `folder/sort{ orders{} }`
(`method:"POST"`), `notification/update{ action:"mark_as_read", ids[],
_csrfToken }`, `comment/*` all carry `_csrfToken`.
