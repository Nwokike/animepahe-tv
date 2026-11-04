# SocoLive port — provider contract & router mechanics

READ-ONLY research report. Source tree: `/home/maikel/Desktop/kiri-apps/socolive-tv` (files live under `src/`, not `services/` at the repo root). Donor reference: `/home/maikel/Desktop/kiri-apps/animepahe-tv/src/services/providers/base.py` + `src/services/router.py`.

---

## 1. The provider contract as it exists

### 1.1 Protocol shape (`src/services/providers/base.py`)

`@runtime_checkable class Provider(Protocol)` — five async methods + two attributes:

| Member | Signature | Notes |
|---|---|---|
| `name` | `str` | Router/breaker/health dict key; also the session namespace |
| `capabilities` | `dict` | **Gates behavior** — "these flags GATE behavior in this app (read at the call sites), they are not documentary" |
| `probe()` | `-> bool` | Cheap liveness for the startup race (4s timeout) |
| `latest_releases(page)` | `-> tuple[list[Match], bool]` | The browse list; every provider returns `has_more=False` (window feeds, not paged) |
| `search(query, page)` | `-> tuple[list[Match], bool]` | Every provider does `"local"` search — no remote search endpoint anywhere; each filters its own catalog window and caps at 20 hits |
| `sources(match_session)` | `-> list[Source]` | Every room x quality. Empty = genuinely none — "a RESULT, not a failure, and does not fail over" |
| `close()` | `-> None` | httpx client teardown (`_owns_client` guard) |

Session namespacing (module functions): `make_session(name, id)` → `"socolive:2997205"`; `split_session` partitions on the FIRST `:` only (deliberate — damitv ids contain `/`); `owner_of` falls back to `DEFAULT_OWNER = "socolive"` for bare sessions. Favorites/recents keyed by the namespaced session are per-backend by construction.

There is **no `schedule()` method** and no `episodes()`-style per-title op — the sports analog of "episodes" is folded into `sources()` (all rooms/qualities of one match in one call). ball808 exposes an extra non-protocol `match_page(match_id)` helper.

### 1.2 Dataclasses (`src/core/state.py`)

- **`Match`** — `id, session, home_team, away_team, competition, kickoff (epoch s), status ("live"|"upcoming"|"finished"), competition_logo, home_logo, away_logo, home_score, away_score, minute, venue, provider, locale ("vi"|"en"), cover`. Locale is content language; names are never translated at runtime.
- **`Room`** — `room_num, sd_url, hd_url, language, label`. Internal to the socolive provider (fan-out accumulator), not part of the protocol.
- **`Source`** — `url, quality ("sd"|"hd"), label, referer, headers (dict), m3u8=True, mint (""|"embed")`. Docstring: headers/referer "ride the play path exactly like the anime app's Source — some sports CDNs check Referer". `mint` marks URLs needing the app's WebView minter first, then playback through the loopback HLS proxy.

Mint value drift worth noting: the `Source` docstring says `"" | "embed"` and streamedpk uses `mint="embed"`, but liveleagues, dlive and ppv use `mint="webview"` for the same mechanism (embed_mint.py serves both). Two spellings, one pipeline.

### 1.3 Capabilities flags actually used across the 10 providers

`streams` (bool), `sd_hd` (bool), `logos`, `posters`, `scores` (bools), `locale` ("vi"/"en"), `search` ("local"|"none"), `lineups` (socolive only), `language_variants` (bool), `mint` ("webview"), `capture_pending` ("loadSign" | "channel-fetch" — the documented open item), `schedule` (bool, ball808 only). Not uniform — see inventory table for who declares what.

### 1.4 How headers/referers ride

Three layers:
1. **Client defaults** — each provider builds its own `httpx.AsyncClient` with a UA + site referer/origin (e.g. socolive: referer `https://socolive.club/`, origin `https://json.vnres.co`; ppv: referer/origin `https://ppv.st`; cameltv: referer/origin `https://www.camel1.tv`).
2. **Per-request referer overrides** — damitv's extract call sends `Referer = the match's own embed URL`; cdnlivetv's player-page fetch sends the site referer; timstreams' embed fetch sends `https://timst.top/`.
3. **Play-path headers on Source** — `referer` + `headers` dict ride to the player/proxy (socolive: referer socolive.club; damitv: referer + origin damitv.st; cdnlivetv: referer + origin cdnlivetv.tv; streamedpk: referer embed.st; dlive: referer dlive.sx; ppv: referer ppv.st; timstreams: referer `https://judiaslevels.embeds.gay/`).

---

## 2. Router mechanics (`src/services/router.py`, 263 lines)

### 2.1 Registration & ordering

- `ProviderRouter(providers=[...])` — `src/main.py:246` wires all ten in this **editorial order**: damitv → streamedpk → cdnlivetv → cameltv → ppv → liveleagues → dlive → timstreams → ball808 → **socolive (backstop, last)**. `add_provider()` appends (creates breaker + health records).
- `set_pin(name)` — "auto"/None keeps editorial order; a name moves that provider FIRST for every operation, still with full failover. Pin is persisted in `AppState.backend_pin`; `active_backend` = pin or `last_winner`.
- Public ops: `latest_releases(page)`, `search(q, page)` (chain in editorial/pinned order); `sources(session)` / `sources_forced(session)` (chain re-ordered owner-first via `owner_of(session)`, forced variant passes `force=True`).

### 2.2 Failover — **automatic and per request**

`_run(op, *args, force, owner)` is a plain sequential loop:
1. Skip provider if breaker not `allow()`ing (unless `force`).
2. `await getattr(provider, op)(*args)`; exception → `breaker.record_failure()` + health record, continue to next.
3. Success → `breaker.record_success()` + health.
4. Empty payload (`_is_empty` inspects tuple element 0) → continue, EXCEPT on the last provider, whose empty is final and returned.
5. Exhausted with errors → `RouterError("all providers failed for {op}")`.

No racing: worst case is the SUM of the chain's timeouts (the donor animepahe router fixed this with first-try-then-race — see §4).

### 2.3 Circuit breaker (`_Breaker`, config in `core/config.py`)

3 consecutive transport/parse failures → OPEN (fail fast, no network); 30s cooldown → ONE half-open trial; only a FAILED TRIAL doubles the cooldown (×2, cap 300s). `force=True` bypasses OPEN. Config: `BREAKER_FAIL_THRESHOLD=3`, `BREAKER_OPEN_SECONDS=30`, `BREAKER_OPEN_MAX_SECONDS=300`, `STARTUP_PROBE_BUDGET=8.0`, `STARTUP_PROBE_TIMEOUT=4.0`.

### 2.4 Health & the startup probe race

`ProviderHealth(state, latency_ms, last_error, checked_at)` per provider, recorded on every routed call and probe; `health()` read by badge + Settings. `probe_all()` races all probes in parallel under the 8s budget; a failed probe records ONE breaker failure (of three). **Known divergence from the donor:** on budget timeout socolive fabricates `results = [None]*n` and records a failure for every provider; animepahe fixed this (`move_on_after` leaves un-answered providers untouched, half-open machinery retries later).

### 2.5 What the backend badge shows (`src/components/backend_badge.py`)

Badge = current backend name + **locale pill** ("VI" for the Vietnamese source) + **health dot always paired with a word** (closed→"ok", half_open→"retrying", open→"down", unknown→"…") + dropdown arrow. PopupMenuButton menu: "Automatic (recommended)" row first, then one row per provider — check icon when pinned, status dot, name, locale pill, meta token (latency `Nms` or `last_error[:40]`). `on_pick(name)` swaps (None/"auto" restores editorial order); `current` = pin or last winner. The same picker mirrors in Settings. Notably the animepahe donor has the OPPOSITE product rule — "there is no 'automatic' option anywhere, in any UI, ever" — a reconciliation point for the port.

### 2.6 Supporting services the router does not own

- **`services/rotation.py`** — generic rotating-domain resolver for the Score808/808ball family. Ordered candidate list (12 hosts; `score808.online` redirector leads as "the cheapest signal of where the operator moved"). 4-pass certify gate: (1) GET / → 200 with body > 30 KB (SSR, not shell); (2) title matches `/808Ball|Score808/i`; (3) Nuxt marker (`__NUXT__` / `/_nuxt/`); (4) a probe match page on the SAME host returns 200 with `matchId:2997205` in SSR state — "brand clones 200 on / but 404 on every /football/ URL; that gate is what kills them". Immediate rejects: "THIS DOMAIN HAS BEEN SEIZED", parked redirect to `qemow.com`, 52x. Winner cached with `certified_at`, re-validated hourly via cheap GET /; any failed match-page fetch → `invalidate()` → full re-run from the top. (In ball808.py the resolver is instantiated but `load_cached()` store-wiring is not invoked — cache is in-memory per provider instance.)
- **`services/embed_mint.py`** — `mint_m3u8(page, embed_url, timeout=25)`: opens a `flet_webview` WebView in a modal dialog, polls `performance.getEntriesByType('resource')` for a `.m3u8` name, also scrapes console messages for m3u8 URLs, pokes `video.play()`/click after ~8s for gesture-gated players. Returns None on budget expiry ("a RESULT, not a crash"). Used for embed.st (streamedpk), dembed (dlive), taifood-blog.asia (ppv), liveleagues sub-pages; minted streams then play through the loopback HLS proxy (`hls_proxy.py`: primp pulls + WEBP unwrap). Explicitly "a one-shot ~seconds capture at play time for this one backend, never a standing gate on browse/search".

---

## 3. Per-provider inventory

Editorial order (main.py): 1 damitv · 2 streamedpk · 3 cdnlivetv · 4 cameltv · 5 ppv · 6 liveleagues · 7 dlive · 8 timstreams · 9 ball808 · 10 socolive.

| # | name | site / API base | catalog source | stream resolution | mint? | CF / walls | quality | scores | logos | locale |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | damitv | damitv.st `/papi/api/*` | keyless JSON (grouped, football filter) | signed m3u8 pair on messi.damitv.st (`?tk=&e=`, ~2h expiry, never cached) | no | none (its selling point) | HD + SD + per-language `sdStreams[]` | no | yes | en |
| 2 | streamedpk | streamed.pk official free API (`/api/matches/*`, `/api/stream/{src}/{id}`) | JSON, no auth | embed.st player page | `mint="embed"` (WebView) | none on catalog; playback needs WebView mint + loopback proxy | hd flag per server row; tier labels alpha→intel | no | yes (badge proxy tokens) | en |
| 3 | cdnlivetv | api.cdnlivetv.is (events) + api.cdnlivetv.tv (channels), `?user=…&plan=…` | keyless JSON | player-page base64+concat decode → tokenized playlist URL (token = `id:expiry:domain:…`, cached to expiry−60s, max 3h) | no — pure Python | none; player endpoint "occasionally flaky" (4 retries, 5s) | all labeled "hd", channel_name label | no | yes (+flagcdn) | en |
| 4 | cameltv | api.cameltv.live `/camel-service/ee/sports_live/*` (site camel1.tv) | JSON (living_group_match + home_match; ~70 routes documented) | **GATED** — `sources()` returns `[]`; `football/stream?matchId=` has real liveplay URLs but CDN needs signed `loadSign` params from a browser DevTools capture | — | no CF, but token capture pending | — | **yes** (status_id 2/4/5 + score arrays) | yes (sports.com CDN) | en |
| 5 | ppv | api.ppv.st `/api/streams` | keyless JSON (DamiTV's catalog twin, shared `uri_name` slugs) | item `iframe` (taifood-blog.asia embed) | `mint="webview"` | none on catalog | all "hd"; main + substreams[] with locale labels | no | yes (posters + blurhash placeholder art) | per-item locale |
| 6 | liveleagues | www.liveleagues.me (vipleague successor) | plain HTML: hub → tag pages (cap 60) → `-live-streaming` sub-pages | sub-page URLs; player is JS-injected ("Please stand by" overlay, no iframe) | `mint="webview"` | "no challenge, no auth" | all "hd", "Broadcast N" | no | no | en |
| 7 | dlive | dlive.sx (DaddyLive) | HTML home page (24/7 hub + match listing, regex-parsed) | `/stream/stream-{N}.php` page's dembed.st iframe | `mint="webview"` | dembed **blocks datacenter egress 403** — residential + WebView passes | single "Main feed", "hd" | no | no | en |
| 8 | timstreams | timst.top (hub); embeds at ehgembxe.cfd | **none** — listing pages rotate; "single live channel right now" | XOR-obfuscated embed JS: `chr(((arr[i]^k1)−k2+256)%256)`; decoder re-parses the loop's var names + constants every call (they rotate: 51/23 today, 83/63 when mapped); decoded jwplayer config carries the signed m3u8 | no — "the decrypt IS the mint" | rotating embed domain; rotating obfuscation constants | single "Main feed", "hd" | no | no | en |
| 9 | ball808 | Score808/808ball family (12 candidate domains) | **GATED** — SSR ships schedule empty (`fetchHotMatchList` route + params pending capture) | **GATED** — player channel fetch pending; will ride the generic WebView mint | planned | domain rotation (seizures); 4-pass certify in rotation.py | — | no (in obfuscated Nuxt payload) | yes (titan007 on match page) | en |
| 10 | socolive | json.vnres.co (referer socolive.club) | JSONP: `/match/matches_{YYYYMMDD}.json` (5-day window, parallel day fetches) + `all_live_rooms.json` single live feed | `/room/{roomNum}/detail.json` JSONP → `stream.m3u8` + `stream.hdM3u8`, **server-signed, direct play** | no | **Cloudflare 1009 (banned ASN) from datacenter egress**; works from residential — "an egress property, not a provider defect" | per-room SD + HD m3u8 | **yes** | yes | **vi** |

Reliability notes from the code/docstrings, verbatim-ish:
- **damitv** "leads the editorial order: the only backend with BOTH a keyless JSON catalog AND zero-JS signed-HLS minting, in English."
- **socolive** is "the app's most reliable source, demoted to the backstop" (Vietnamese). Port fixes carried: bounded room fan-out (anyio CapacityLimiter 4 — "the old code's unbounded gather had an exception-unpack bug"), anchored JSONP regex, `\u003d`/`\u0026` unescaping, uid fallback when an anchor carries no roomNum. Live heuristic: kickoff ≤ now ≤ kickoff+2h.
- **cdnlivetv**: "the biggest catalog in the bench" (160 soccer events / 417 channels); "No WebView, no JS engine — the obfuscation is base64 + concat only."
- **timstreams**: `latest_releases`/`search` return empty by design; "the provider's value is the verified decrypt ladder."
- **ball808**: probe IS `rotation.resolve()`; `match_page()` invalidates the certified host on any non-200.
- **streamedpk**: `date == 0 or negative` rows are 24/7 channels (status live); capabilities comment: "Streams play through the app's own WebView mint + loopback proxy (no hosted resolver) — honest at runtime."
- Catalog TTLs: 60s (streamedpk, cameltv, ppv), 90s (liveleagues, timstreams-declared-unused), 120s (socolive day files, cdnlivetv, dlive, damitv); socolive live feed 60s.

---

## 4. Compare against the animepahe donor contract

Donor: `animepahe-tv/src/services/providers/base.py` (247 lines) + `src/services/router.py` (543 lines).

### 4.1 Protocol

Same skeleton (name, capabilities, probe, latest_releases, search, sources, close, `make_session`/`split_session`/`owner_of` — socolive's base.py is visibly a port of this file), with these differences:

| Aspect | animepahe-tv | socolive-tv |
|---|---|---|
| Per-title ops | `episodes(session, page)` in the Protocol; PLUS `episodes_for_title(title)` and `sources_for_title(title, episode)` ("the router's title-keyed failover calls these on every provider") | None — `sources(match_session)` is the only per-item op |
| Wall signal | `CloudflareBlocked` exception, raised deliberately; router propagates it instead of counting a failure, controller turns it into the verification gate | No equivalent — walls read as empty results (cameltv, ball808) or transport failures that trip the breaker (socolive CF 1009, dlive 403) |
| Row type | `LatestRelease` (anime_id/anime_title/anime_session/episode/snapshot/session/created_at) + `releases_from_anime()` mapper; `Anime`/`Episode` shapes | `Match` |
| Ordering | `PROVIDER_ORDER` fixed tuple `(anikato, kayoanime, animepahe, animeout)` — "there is no 'automatic' option anywhere, in any UI, ever" | Construction order in main.py; pin system WITH an "Automatic (recommended)" UI option |
| Extras | `BrowserProvider` protocol (optional `filters()`/`browse()` discovery), `page_slice`, `all_episodes`, `close_client` (primp quirk), `EPISODES_PER_PAGE` | Nothing — smaller surface |
| Source fields | `url, resolution (int), audio, fansub, headers, subtitles, skip, size, download_url, bd` | `url, quality ("sd"/"hd"), label, referer, headers, m3u8, mint` — no subtitles/skip/size/download/bd; quality is a string not a resolution int; `referer` explicit rather than inside headers |

### 4.2 Router

The socolive router is an earlier snapshot of the same design (identical `_Breaker`, `ProviderHealth`, `_is_empty`, probe constants), but the donor has evolved past it in five ways:

1. **`_attempt` wrapper + `CloudflareBlocked` passthrough** — the donor never counts a wall as a breaker failure and never lets another provider stand in for a challenging owner's sessions; socolive has no wall concept at all.
2. **First-try-then-race failover** — donor tries the first eligible provider alone, then races the rest in an anyio task group (first non-empty answer cancels the rest): worst case `max(fastest, deadline)` instead of the sum of timeouts. Socolive is purely sequential.
3. **`session_owned` semantics** — donor catalog/search/episode/source ops ask ONLY the named owner once a backend is chosen (a race let an unvalidated provider win with another's session string); socolive always chains all ten for catalog ops.
4. **Title-keyed cross-provider paths** — `episodes_for_title_any` / `sources_for_title_any(skip=…)` for "Try another source", breaker-aware with a `force` override. Socolive has only `sources_forced`.
5. **Probe deadline honesty** — donor no longer fabricates failures for providers that didn't answer within the probe budget; socolive still does (`results = [None]*n` on timeout).
6. (Donor also has a Discover/browse section with `discover_provider` fallback-to-backbone, and the empty-then-raise fix in the race path — both sports-irrelevant or minor.)

Shared by both: per-provider breaker dicts, health records surfaced to UI, namespaced session owner-first routing, `last_winner` tracking, `close()` fan-out.

---

## 5. Gap list — what each provider would need for the animepahe-style "each backend exposes everything" contract

The donor contract means: every backend implements the FULL protocol including the per-title ops (`episodes_for_title`, `sources_for_title`), raises wall signals deliberately, and honest row types — so any screen can ask any backend anything and failover stays coherent.

### 5.1 Per provider

- **damitv** — Closest to complete for its catalog. Needs: title-keyed ops (map home/away names → catalog id); nothing else structural. Note: ~2h signed URLs never cached by design → repeated `sources()` calls re-mint; a title-keyed op would multiply that.
- **streamedpk** — Needs: title-keyed ops; a capability the play leg actually checks for WebView availability (mint pipeline is assumed); scores absent (catalog doesn't carry them).
- **cdnlivetv** — Needs: title-keyed ops; `scores` (catalog lacks them); the 417-channel list is catalogued but unused by the Match model. Player-page flakiness (4×5s retries) should surface as a wall-ish signal rather than silent `None` after 20s.
- **cameltv** — Catalog/scores/logos are done. Needs: the `loadSign` browser capture to implement `sources()` (the one open item, `capture_pending: "loadSign"`); until then it violates "each backend exposes everything" by construction.
- **ppv** — Needs: title-keyed ops; scores; the `"Home vs. Away"` / `" vs "` name partition is fragile (three fallback tiers, final one puts the whole name in home_team).
- **liveleagues** — Needs: title-keyed ops; logos (none exist); kickoff is often 0 (siteConfig missing) → status falls back to "upcoming"/"finished" guesses; sub-page mint depends on WebView availability.
- **dlive** — Needs: title-keyed ops; real kickoff (always 0, everything "live"); competition hardcoded "DaddyLive"; more than one feed per match (single first-iframe); search is bare substring (others use word scoring).
- **timstreams** — Biggest gap: NO catalog at all (`latest_releases`/`search` return empty by design). Needs a listing surface (hub listing pages "rotate") before it can be a complete backend; the decrypt ladder is done and verified.
- **ball808** — Everything except match-page parsing and rotation is gated (`capture_pending: "channel-fetch"`): schedule, scores/status/kickoff, streams. Also needs the resolver's `load_cached()` store wiring (currently in-memory only, so a restart re-runs the full 12-host certify walk).
- **socolive** — Content-complete but: Vietnamese locale (by design, backstop); CF 1009 from datacenter egress is indistinguishable from a dead host to the router — needs the wall signal; `sources()` depends on `_anchors_cache` populated during catalog fetch (repopulation via `_match_by_id` works but costs a full 5-day window re-fetch per cold session).

### 5.2 What the shared router must add (donor features missing in socolive)

1. **`CloudflareBlocked` discipline** — a deliberate exception per provider + router passthrough + verification-gate hook; today socolive CF 1009 / dlive 403 / cameltv token walls all masquerade as empty-or-failed providers and silently trip breakers.
2. **Per-provider clearance stores** — WebView-minted clearances / CF cookies / certified hosts persisted per provider (the animepahe app keeps CF clearance; socolive keeps nothing across restarts — even the rotation winner is instance-local).
3. **First-try-then-race failover** — replace the pure sequential chain (sum-of-timeouts worst case) with the donor's first-then-anyio-race.
4. **`session_owned` owner-only catalog ops** — once a backend is pinned, its catalog/search should come only from it (donor's fixed race hazard), instead of always chaining ten providers.
5. **Title-keyed cross-provider ops** — `episodes_for_title_any`/`sources_for_title_any` equivalents (for sports: team-name → match → streams "try another source") — requires the per-provider title-keyed methods from 5.1.
6. **Honest probe deadline** — stop fabricating breaker failures on probe-budget timeout (donor fix).
7. **Health coverage of the play leg** — the mint step (embed_mint) and rotation certify run OUTSIDE the router, so their failures never touch breaker/health; the badge can show "ok" while every play attempt fails.
8. **Pin/auto product decision** — reconcile socolive's "Automatic (recommended)" badge with the donor's hard rule that ordering is fixed and no auto option exists anywhere.

---

## Summary (8 bullets)

1. **Contract**: one `Provider` Protocol (name, capabilities dict, probe/latest_releases/search/sources/close) over namespaced sessions (`"damitv:seriea/…"` — split on the first `:` only, so damitv's slash-bearing ids route); capabilities flags genuinely gate app behavior; `sources()` empty is a RESULT that never fails over.
2. **Data shapes**: `Match` (16 fields incl. per-backend `provider` + content `locale`) and `Source` (url, quality "sd"/"hd", label, referer, headers, mint "") — headers/referers ride at three layers: client defaults, per-request overrides, and on-Source play-path headers.
3. **Router**: ten providers wired in editorial order (damitv leads, socolive is the Vietnamese backstop last); failover is automatic and per request — sequential chain, breaker-gated skipping, empty-payload continuation until the last provider; `set_pin` moves one provider first; `sources()` re-orders owner-first from the session namespace.
4. **Breaker/health**: 3 failures → OPEN, 30s cooldown, one half-open trial, failed trial doubles cooldown to a 300s cap; every call records `ProviderHealth` (state/latency/last_error) that feeds the badge and Settings; `probe_all` races 4s probes under an 8s budget but still fabricates failures on deadline (the donor fixed this).
5. **Badge**: current backend name + locale pill ("VI") + health dot paired with a word (ok/retrying/down/…); menu lists "Automatic (recommended)" plus every provider with check-on-pin, status dot, and latency-or-error meta — the exact control the anime app never built.
6. **Stream resolution spans four ladders**: direct server-signed m3u8 (socolive, damitv), pure-Python page de-obfuscation (cdnlivetv base64-concat, timstreams XOR with rotating constants), WebView-minted manifests (streamedpk embed.st, ppv, dlive dembed, liveleagues — via embed_mint.py resource-timing harvest + loopback HLS proxy), and nothing-yet (cameltv loadSign, ball808 channel-fetch, both `capture_pending`).
7. **Walls are egress/rotation, not CF challenges**: socolive answers CF 1009 to datacenter ASNs but works residential; dlive's dembed 403s datacenter IPs; ball808's family rotates domains through a 12-host certified-host resolver (4-pass gate incl. a same-host match-page probe that kills brand clones) — none of these are Cloudflare challenge flows, and none of them raise a deliberate wall signal today.
8. **Port gaps**: every provider lacks the donor's title-keyed ops (`episodes_for_title`/`sources_for_title` analogs) and the `CloudflareBlocked` discipline; cameltv/timstreams/ball808 are incomplete backends by their own docstrings; the router needs first-then-race failover, owner-only catalog ops, per-provider clearance/host persistence, and health coverage of the mint/play leg it currently can't see.
