# Ads Audit: animepahe-tv vs KTV Player

**Date:** 2026-11-01  
**Scope:** Map every ad placement in animepahe-tv, compare to KTV Player's ad architecture, list gaps with exact fixes.  
**Env:** flet==0.85.3, flet-yandex-ads==0.1.0, PYTHONPATH=src

---

## 1. KTV Player Ad Placements (Reference Architecture)

| # | Placement | Trigger | File:Line | Gating | Notes |
|---|-----------|---------|-----------|--------|-------|
| K1 | **Pre-roll interstitial** | Before **every** playback starts (P23) | `immersive_player.py:618-628` | mobile + non-premium + consent | 20s timeout; if user closes ad → cancels playback; skipped on premium/non-mobile |
| K2 | **Interstitial preload** | App startup (after UMP consent) | `main.py:649-653` | mobile + non-premium + consent | `ad_service.preload_interstitial()` called once at init |
| K3 | **Interstitial re-preload** | Immediately after each interstitial closes | `ad_service.py:288-292` | — | `preload_interstitial(on_close=...)` fires in `_handle_close` |
| K4 | **App-open ad** | (Implied) cold start | — | mobile + non-premium + consent | Not directly grepped; standard AdMob pattern |
| K5 | **Banner: native 300×250** | In content grids, every 24 rows | `channel_grid.py:213`, `ad_service.py:138-157` | mobile + non-premium + consent | `AD_ROW_INTERVAL = 24` (`core/constants.py:192`) |
| K6 | **Banner: standard 320×100** | Labeled support container | `ad_service.py:159-178` | mobile + non-premium + consent | — |
| K7 | **Banner: anchor 320×50** | Labeled support container | `ad_service.py:180-199` | mobile + non-premium + consent | — |
| K8 | **Consent (UMP)** | First run / regulated regions | `ad_service.py:53-112` | mobile only | Sherlock pattern: open-by-default, failure ≠ denial, honest status strings |

**Key KTV Discipline:**
- **Preload → Show → Wait for dismiss → Re-preload** — never show without a loaded ad; always have the next one ready.
- **Consent is honest** — `can_request_ads()` returns explicit boolean; failed UMP defaults to *allow* with warning.
- **All banners gated** by `mobile + non-premium + consent` (three-shape strategy).

---

## 2. animepahe-tv Ad Placements (Current Implementation)

| # | Placement | Trigger | File:Line | Gating | Notes |
|---|-----------|---------|-----------|--------|-------|
| A1 | **App-open ad** | Cold start, after SDK `on_initialized` | `main.py:2777-2783` | mobile / Android TV | `build_ad_service()` → `on_initialized=lambda e: spawn(show_app_open(page))` |
| A2 | **Interstitial between episodes** | After episode playback completes, before next resolve | `main.py:932-938` | mobile / Android TV + 30s interval guard | Inside `_play_episode_resolve()`; fires on **every** episode change including next-episode press |
| A3 | **Banner (sticky 320×50)** | Home screen — latest releases grid | `home_screen.py:415` | mobile / Android TV | `*grid_with_ads(release_cards, page)` |
| A4 | **Banner (inline)** | Home screen — continuing row | `home_screen.py:430` | mobile / Android TV | `build_banner_ad(page, inline=True)` |
| A5 | **Banner (inline)** | Discover screen — top promo | `discover_screen.py:505` | mobile / Android TV | — |
| A6 | **Banner (grid breaks)** | Discover screen — main grid | `discover_screen.py:511` | mobile / Android TV | `grid_with_ads(cards, page)` — every 12 cards (`AD_EVERY=12`) |
| A7 | **Banner (grid breaks)** | Search screen — results grid | `search_screen.py:409` | mobile / Android TV | `grid_with_ads(search_cards, page)` |
| A8 | **Banner (grid breaks)** | Anime detail — episode grid | `anime_detail_screen.py:563` | mobile / Android TV | `grid_with_ads(_render_ep_cards(), page)` — every 12 episodes |
| A9 | **Banner (sticky)** | Downloads screen | `downloads_screen.py:374` | mobile / Android TV | Single banner at bottom |
| A10 | **Banner (inline ×3)** | Settings screen | `settings_screen.py:532,536,543` | mobile / Android TV | Three inline banners between sections |
| A11 | **Banner builder** | Canonical `build_banner_ad(page, inline=False)` | `banner_ad.py:56-138` | mobile / Android TV | Sticky=320×50, Inline=max 100px; **one reload attempt** after 30s on `on_load_failed` |

**Current Ad Service (`services/ads.py`):**
- `build_ad_service()` → `YandexAdsService` with hardcoded `_user_consent=True` (line 50)
- `show_interstitial()` — creates fresh `InterstitialAd` each call, 30s interval guard (`INTERSTITIAL_MIN_INTERVAL_SEC=30`)
- `show_app_open()` — creates fresh `AppOpenAd` each call
- Rewarded ad: **deliberately unwired** (docstring line 9-11, roadmap confirms)

---

## 3. flet-yandex-ads 0.1.0 API Verification

| Class | Key Fields | Key Methods | Events | One-Shot Pattern |
|-------|------------|-------------|--------|------------------|
| `YandexAdsService` | `user_consent`, `location_tracking`, `age_restricted`, `logging`, `debug_error_indicator` | `initialize()`, `set_user_consent()`, `set_location_tracking()`, `set_age_restricted()`, `show_debug_panel()` | `on_initialized`, `on_init_failed` | Service added to `page.services` once at startup |
| `InterstitialAd` (extends `FullscreenAd`) | `unit_id` | `load()`, `show()`, `wait_for_dismiss()`, `cancel_loading()`, `destroy()` | `on_shown`, `on_failed_to_show`, `on_dismiss`, `on_impression`, `on_load`, `on_load_failed` | **Fresh instance per show**; load auto-starts when added to `page.services` |
| `AppOpenAd` (extends `FullscreenAd`) | `unit_id` | Same as Interstitial | Same as Interstitial | Fresh instance per show |
| `RewardedAd` (extends `FullscreenAd`) | `unit_id` | Same + `wait_for_dismiss() → RewardEvent\|None` | Same + `on_reward` | Fresh instance per show |
| `BannerAd` (extends `LayoutControl`, `BaseAd`) | `unit_id`, `size_type` (STICKY/INLINE), `max_height` | `reload()` | `on_load`, `on_load_failed`, `on_click`, `on_impression` | Persistent in layout; `reload()` loads new ad |

**All calls in animepahe-tv are valid** — the app uses:
- `YandexAdsService(user_consent=..., logging=..., on_initialized=..., on_init_failed=...)` ✓
- `InterstitialAd(unit_id=..., on_impression=...)` ✓
- `AppOpenAd(unit_id=..., on_impression=...)` ✓
- `BannerAd(unit_id=..., size_type=..., max_height=..., on_load_failed=..., on_impression=...)` ✓

**Correct one-shot pattern used:**
```python
ad = fya.InterstitialAd(unit_id=...)
page.services.append(ad)
await ad.show()
await ad.wait_for_dismiss()  # wait for actual dismissal
await ad.destroy()
page.services.remove(ad)
```
This matches the library's documented pattern exactly.

---

## 4. Gap Analysis: Missing Placements vs KTV

| Gap | KTV Behavior | animepahe-tv Current | Severity | Exact Fix (file:line + fya calls + gating) |
|-----|--------------|---------------------|----------|--------------------------------------------|
| **G1: Pre-roll interstitial BEFORE first playback** | `immersive_player.start_playback()` shows interstitial **before** `video.play()` (line 618-628) | Interstitial fires **after** episode completes in `_play_episode_resolve` (main.py:932-938) — this is **post-roll**, not pre-roll | **HIGH** — revenue loss on session start | **File:** `src/main.py` in `_play_episode_resolve` **before** stream resolution (≈line 920).<br>**Call:** `await show_interstitial(page)` **before** `self._resolve_stage(gen, "Resolving stream…")` (line 990).<br>**Gating:** Reuse `show_interstitial()` — already has mobile/TV + 30s guard. Add premium check if `state.is_premium` exists. |
| **G2: Interstitial preload discipline** | Preload at startup (`main.py:653`), re-preload immediately on close (`ad_service.py:288-292`) | **No preload** — fresh `InterstitialAd` created on-demand every time in `show_interstitial()` (ads.py:110-116) | **HIGH** — latency, failed fills, poor UX | **File:** `src/services/ads.py` — add `preload_interstitial()` mirroring KTV pattern.<br>**New method:** `async def preload_interstitial(page, on_close=None)` — create `InterstitialAd`, append to `page.services`, store ref.<br>**Modify `show_interstitial()`:** if preloaded ad exists & loaded → show it, else fallback to on-demand.<br>**In `main.py:2779`:** after `build_ad_service()`, call `await preload_interstitial(page)`.<br>**Gating:** mobile/TV + non-premium + consent (when wired). |
| **G3: Consent management (UMP)** | Full UMP flow: `ConsentManager`, `request_consent_info_update()`, `load_and_show_consent_form_if_required()`, `can_request_ads()`, `show_privacy_options_form()` — honest status returns | **Hardcoded `_user_consent = True`** (ads.py:50). No UMP, no privacy options, no regulatory posture | **MEDIUM** — regulatory risk if Yandex adds UMP | **File:** `src/services/ads.py` — add `gather_consent(page)` mirroring KTV `ad_service.py:53-112`.<br>**Add:** `_consent_manager`, `_can_request_ads`, `show_privacy_options() → str`.<br>**Wire in `build_ad_service()`:** call `await gather_consent(page)` before returning service.<br>**Gate all ad shows** on `_can_request_ads` (currently hardcoded True).<br>**Settings:** Add "Privacy options" button calling `show_privacy_options()`. |
| **G4: Native / 300×250 banner format** | Three shapes: native 300×250 (grid rows), standard 320×100, anchor 320×50 — all in labeled containers | Only **sticky 320×50** (`STICKY`) and **inline** (max 100px) via `BannerSizeType.INLINE` | **MEDIUM** — missing high-CPM native inventory | **File:** `src/components/banner_ad.py` — add `build_native_ad(page)` returning 300×250 `BannerAd(size_type=INLINE, max_height=250)` in same glass container.<br>**File:** `src/components/ad_breaks.py` — change `AD_EVERY=12` → `AD_EVERY=24` to match KTV `AD_ROW_INTERVAL=24`; insert `build_native_ad(page)` instead of inline banner.<br>**Gating:** mobile + non-premium + consent. |
| **G5: App-open ad cadence** | (Likely) shown on cold start + app resume from background | Only on **cold start** via `on_initialized` callback (main.py:2779) | **LOW** — minor revenue | **File:** `src/main.py` — add `page.on_resume` / `page.on_reconnect` handler to call `show_app_open(page)` with same interval guard as interstitial (or separate 4h guard per Yandex guidance). |
| **G6: Banner on anime detail screen (top)** | KTV channel detail has banner shapes in labeled container | Anime detail only has **grid breaks** between episode chunks (anime_detail_screen.py:563) — no top banner | **LOW** — extra impression | **File:** `src/screens/anime_detail_screen.py` — add `build_banner_ad(page, inline=True)` near top of detail view (above episode grid), gated same as others. |
| **G7: Rewarded ad for downloads** | Not in KTV (AdMob) | Roadmap: "Rewarded early access — out; needs a free-line/paywall rule the app does not have" | **DEFERRED** — owner decision | **No fix needed now.** If owner adds paywall: wire `RewardedAd(unit_id=AD_UNITS["rewarded"], on_reward=...)` in download flow. |

---

## 5. Roadmap Alignment

**docs/roadmap.md (Parked section):**
> **Rewarded early access** — out; needs a free-line/paywall rule the app does not have.

The current code **honors this** — `services/ads.py` docstring (lines 9-11) explicitly states rewarded is "deliberately unwired." No action required until owner defines the gate.

---

## 6. Test Plan (Verification Steps)

| Test | Expected | How to Verify |
|------|----------|---------------|
| **T1: Pre-roll on first play** | Interstitial shows **before** stream loads on first episode of session | Cold start → pick anime → play ep 1 → ad appears before loading spinner |
| **T2: Pre-roll on next-episode** | Interstitial shows before **each** episode playback (not after previous) | Play ep 1 → finish → auto-next or press Next → ad before ep 2 loads |
| **T3: Interval guard** | No interstitial if <30s since last | Rapid next-episode presses → only first shows ad |
| **T4: Preload works** | Interstitial shows instantly (no load delay) on 2nd+ play | Check logs: "Preloading new InterstitialAd..." at startup; "Showing preloaded interstitial ad..." on play |
| **T5: Consent gating** | Ads hidden if `_can_request_ads=False` | Toggle consent flag → banners/interstitials disappear |
| **T6: Premium gating** | No ads for premium users | Set `state.is_premium=True` → zero ad calls |
| **T7: Banner reload** | Failed banner retries once after 30s | Simulate `on_load_failed` → wait 30s → new banner loads |
| **T8: App-open cold start** | App-open shows once on cold start | Fresh install → launch → app-open appears |
| **T9: Native banner (post-G4)** | 300×250 native row every 24 grid items | Scroll discover/home grid → native ad row at positions 24, 48, ... |

---

## 7. Summary (8 Bullets)

- **KTV shows pre-roll interstitial before EVERY playback** (20s timeout, cancels playback on close); animepahe-tv only shows **post-roll between episodes** — **G1 is the highest-revenue gap**.
- **KTV preloads interstitial at startup and re-preloads immediately after each close**; animepahe-tv creates fresh on-demand instances every time — **G2 causes fill-rate loss and user-visible latency**.
- **KTV runs full UMP consent flow** (honest status strings, privacy options); animepahe-tv hardcodes `user_consent=True` — **G3 is regulatory debt**.
- **KTV uses three banner shapes** (native 300×250 every 24 rows, standard 320×100, anchor 320×50); animepahe-tv only has sticky 320×50 + inline — **G4 misses high-CPM native inventory**.
- **All flet-yandex-ads 0.1.0 calls in the app are valid** — one-shot pattern (fresh instance per show, `load` auto on `page.services.append`, `show` → `wait_for_dismiss` → `destroy`) is correctly implemented.
- **App-open ad fires only on cold start**; KTV likely shows on resume too — **G5 is minor but easy to add** via `page.on_resume`.
- **Anime detail screen lacks top banner**; only has grid breaks between episode chunks — **G6 is a quick impression win**.
- **Rewarded ad is correctly left unwired** per roadmap ("needs a free-line/paywall rule the app does not have") — no action until owner defines the gate.