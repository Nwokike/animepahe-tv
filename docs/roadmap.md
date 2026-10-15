# Roadmap — the multi-source app

AnimePahe TV is a hybrid of independent backends: five sources (AniKato,
AnimeOut, Kusonime, Kayoanime, AnimePahe), each treated like its own app —
its own catalog, artwork, playback and Cloudflare story. One source is
resolved at startup behind a splash (a stored pin, or an automatic race of
the open sources; AnimePahe is never auto-chosen — pinning it is the owner's
act and brings its Cloudflare flow with it). While the app is open the source
changes only when the owner changes it. Grid orientation is automatic: the
screen sniffs the shape of the artwork the active source serves and swaps
itself. No cross-linking: an ability only one source has appears only when
that source is selected.

**Standing rules.** Every phase starts with a full fresh read of all docs
("start afresh"), then a plan-mode presentation. Every step carries its own
regression tests; commits per step; the full suite stays green at every
commit (462 passing, warnings-as-errors, F-clean ruff gate). No new
dependencies without a study. Ads keep `demo-*-yandex` unit ids until the
owner swaps production ids.

**History.** Phases before this list — the 0.85.3-era multi-source plan, the
audit passes (7.5/7.6), the YouTube-style downloads release — live in git
history. The findings that still bind are in `docs/testing-findings.md`, the
swarm audit, and `docs/reference/`.

---

## Phase 1 — the art decides the shape (complete)

1. `core/artwork.py`: byte sniffer (JPEG SOF / PNG IHDR / WebP with every
   variant's length guard), shape classifier, data-URI path, majority vote.
2. `services/artwork_probe.py`: cache-first (30-day shape TTL in the cache
   tier), Range-reads a few KB per probe, never raises — unknown is a valid
   answer.
3. Learned defaults per (provider, surface) in the durable store; the
   `use_grid_mode` hook decides automatically (learned → vote → seeded
   default). Every screen wired.
4. `components/artwork_card.py`: one frame, two aspect ratios; mismatched art
   fills a frosted backdrop instead of letterboxing.
5. Each list stamps the provider that painted it.
6. Storage unified on the `.flet/README.md` canon (`core/storage.py`:
   data / cache / temp, one resolver); dead code swept with zero-ref
   evidence. Commits d8af1a1 → ea87eb2.

## Phase 2 — startup resolution & the independent-backend doctrine (complete)

- Pre-step (8d9bc27): AniKato's CDN doors — `is_ad_stub_playlist()` skips the
  TikTok-stub playlist and `sources()` keeps the first door serving real
  video; full cache keys; mirror-flavor collapse; solver fail-fast on plain
  nginx pages.
- Step 1 (83d9715): `startup_ready`/`startup_stage` + the CollabShell-style
  splash behind all hooks.
- Step 2 (c37f483): `resolve_startup()` — stored pin resolves directly;
  `auto` races the four open backends (health only) and never picks AnimePahe;
  every manual switch re-runs the same gate; single-flight.
- Step 3 (12f4ec3): `latest_releases`/`search` are owner-only; heal and
  cold-open resolve through the session's own owner.
- Step 4 (d6228c9): playback stops hopping backends; "Try another source"
  re-enters on the match's own session.
- Step 5 (71e3ef9): Discover and Schedule follow the pinned provider only.
- Step 6 (514958b): copy tells the truth — "What you choose is the app."
- Step 7 (740c2dc): desktop solver pins the stored UA, refuses a non-Chromium
  renderer, judges a loaded page immediately (`_done` latch).
- Step 8 (cca5aee + d941a02): exit gate — suite under `-W error`, F-clean;
  the docs caught up (README to the hybrid app, reference version stamps).

## Phase 3 — every screen × every backend (complete)

The completeness pass: each source behaves like a complete app on every
screen. Five threads, five commits — 156a044 (episode paging 24/page in
the four all-at-once providers + the `all_episodes` walk for the lookups
and checker), d00accf (count honesty: AnimeOut's excerpt count, no "0"s),
d984d97 (one rendition → one choice; kayoanime collapsed to one Source;
no "0p"), 52e67dc (the `/image` route: web CORS + guarded hosts, wrapped
at the display edge only), and the exit gate below. 491 passing under
`-W error`, F-clean; the live acceptance runbook (screen × backend matrix)
lives at the end of docs/testing-findings.md.

1. **Episode paging.** 24 per page, rendered with the existing pager
   (Prev · Page N · Next). The four providers that return everything at once
   (anikato, animeout, kusonime, kayoanime) slice their cached full list;
   animepahe keeps its server pages (its own shape). Fixes the 170-episode
   dump and kusonime's 1000+-episode lists.
2. **Count honesty.** Unknown counts render as nothing — never "0"/"0p".
   AnimeOut's `Episodes:` parses from the post excerpt (probe: 220/24/4/1;
   mega-posts empty → hidden); the series-download dialog's zero guard.
3. **One rendition, one choice.** No picker when a source offers a single
   logical rendition — play, external, and download all auto-start.
   Kayoanime is one Source (`url` = playback route, `download_url` = the
   usercontent download route); `_source_choices` dedupes logical
   renditions and stops printing "0p".
4. **The image route.** The loopback proxy's `GET /image` (b64 url +
   referer, content-type forward, 8 MB cap, mem cache, CORS header). Web
   wraps every image; native wraps only the guarded host (animeout's
   CF-challenged wp-content — probe evidence in testing-findings). Stores
   keep raw URLs.
5. **Exit gate.** Suite 0 fail/0 warn under `-W error`; F-clean; testing
   findings items 1–3 closed with evidence; the owner's matrix runbook
   documented.

## Phase 4 — player & downloads depth (pending)

- **AniKato parity**: the 9 WebVTT subtitle tracks (megaplay referer) into the
  player's track picker; `skip_data` intro/outro into the skip button.
- **Player craft**: local subtitle file picker + persisted size, snapshot
  save (MediaStore/fs), aspect-fit switcher, settings double-open guard.
- **Robustness**: offline retry/skip card where grids go empty; crash reporter
  (per-crash files + rotation); downloads manifest writes moved off-loop
  (anyio `to_thread`).

## Phase 5 — dependency close-out (pending)

- Pin the ruff lint `select` set and reconcile the ~449 non-F findings.
- Refresh every version-stale dep doc (`docs/reference/README.md` stamps the
  list); reconcile `pyproject.toml` floors with the installed versions.
- Dead-code rescan with zero-ref evidence.

## Phase 6 — v2 publication (pending)

- Version 2.0.0 + build number, changelog, final README pass.
- Notification permissions + the `flet-notifications-patch` runbook; the
  Android manifest entries for scheduled/reboot notifications.
- CI verification, tag, release; the owner's live acceptance run per phase
  above.

## Parked (owner-deferred, with evidence)

- **AniKato content side-by-side** — the app resolves the same realid the
  site's own iframe embeds and the doors now serve real video; the next lever
  is capturing the iframe's own network call (browser resource log).
  Re-observed during Phase 3's matrix run.
- **AnimeOut file wall** — after the solver's legit Cloudflare challenge, the
  file host answers a plain nginx 403; files stay unplayable until that
  changes (artwork is covered by Phase 3's image route).
- **Comments read / Watch2Gether** — out until the full surfaces exist (write
  paths are login-only).
- **Rewarded early access** — out; needs a free-line/paywall rule the app
  does not have.
- **Production ad unit ids** — the owner's swap (four `R-M-XXXXXX-Y` ids).
- **The owner's later major changes** — one provider leaves; one becomes the
  backbone for Discover; the rest hardened perfectly. Planned after the
  phases above, by the owner's direction.
