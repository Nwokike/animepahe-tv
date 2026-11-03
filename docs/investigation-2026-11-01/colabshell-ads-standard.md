# ColabShell Ad Implementation Standard — House Reference

**Source**: `/home/maikel/Desktop/kiri-apps/CollabShell` (owner's production app)  
**Date**: 2026-11-02  
**Purpose**: Document exact implementation for verbatim adoption in animepahe-tv

---

## 1. Ad Touch Points — Placements Table

| Format | Screen / Trigger | File:Line | Notes |
|--------|------------------|-----------|-------|
| **SDK Init / Consent** | App bootstrap (main.py) | `src/main.py:264-267` | `AdService(page)` → `gather_consent()` (UMP) → `preload_interstitial()` |
| **Banner** | HomeScreen — between sessions list & features | `src/screens/home/__init__.py:341` | `build_banner_ad(page)` |
| **Banner** | HomeScreen — between features & how-it-works | `src/screens/home/__init__.py:343` | `build_banner_ad(page)` |
| **Banner** | SessionSelectorTab (Notebooks/Terminals/Files tabs) | `src/screens/session_selector.py:86` | `build_banner_ad(page)` |
| **Banner** | FilesScreen — below toolbar | `src/screens/files/__init__.py:598` | `build_banner_ad(page)` |
| **Banner** | HistoryScreen — bottom of screen | `src/screens/history/__init__.py:325` | `build_banner_ad(page)` |
| **Banner** | SettingsScreen — after Auth section | `src/screens/settings/__init__.py:93` | Labeled "SPONSOR" |
| **Banner** | SettingsScreen — after Behavior section | `src/screens/settings/__init__.py:99` | Labeled "SPONSOR" |
| **Banner** | NotebookView — every 2nd cell | `src/screens/session/notebook_view.py:1424` | `(i+1) % 2 == 0` |
| **Banner** | NotebookView — tab bar area | `src/screens/session/notebook_view.py:1564` | Below tab bar |
| **Interstitial** | New Session Sheet — after hardware confirm, before provisioning | `src/components/new_session_sheet.py:157-158` | `ad_service.show_interstitial()` |
| **Interstitial** | App cold start — preloaded immediately after consent | `src/main.py:267` | `page.run_task(ad_service.preload_interstitial)` |
| **Rewarded** | Wallet Dialog — "Watch ad for credits" | `src/components/wallet_dialog.py:159-161` | `show_rewarded_interstitial(_on_reward)` |
| **Rewarded** | FilesScreen — batch download | `src/screens/files/actions.py:255-258` | `show_rewarded_interstitial(on_close=_do_downloads)` |
| **Rewarded** | HistoryScreen — export logs | `src/screens/history/__init__.py:99-102` | `show_rewarded_interstitial(on_close=_do_export)` |

**NOT PRESENT in ColabShell**:
- ❌ App-open interstitial (on cold start / resume after 4h)
- ❌ Native ads
- ❌ Any user-facing ad settings/toggles

---

## 2. User Configuration — Findings

**Confirmed: NO user-facing ads toggle/settings anywhere.**

- **SettingsScreen** (`src/screens/settings/__init__.py`) — 13 sections, zero ad-related controls
- **Premium section** (`src/screens/settings/premium_section.py:76-91`) — `page_has_ads()` detects if ads *can* show (mobile only, non-premium), used only for copy ("Removes ads" vs credits-only pitch)
- **Advanced section** (`src/screens/settings/advanced_section.py`) — only "Log to Stderr" toggle
- **Premium entitlement** (`src/core/state.py:95`, `src/services/ad_service.py:74-81`) — single source of truth: `state.is_premium` → ads disabled entirely
- **Channel gating** (`src/screens/settings/__init__.py:88-89`, `src/screens/settings/premium_section.py:161-164`) — Play channel builds ZERO premium card, "not even a disabled card — nothing to declare, nothing to reach, ads stay on"

**Highest-paying format selection logic** (`src/services/ad_service.py:31-40`):
- `USE_TEST_IDS = False` (production IDs active by default)
- Single banner ID + single interstitial ID (same ID used for both regular + rewarded interstitial)
- No mediation / waterfall / priority logic — AdMob decides via single ad unit
- Native ad ID defined (`NATIVE_ID_ANDROID_PROD`) but **never used** in codebase

---

## 3. Show / Load Flow per Format

### Banner (build_banner_ad / AdService.get_banner_ad)
**Files**: `src/core/styles.py:108-158`, `src/services/ad_service.py:133-165`

```python
# Flow: instant synchronous build
def get_banner_ad(self) -> ft.Control:
    if premium or not mobile or not _HAS_ADS or not _can_request_ads:
        return Container(0,0)  # collapsed
    return Container(
        content=fta.BannerAd(unit_id=self.banner_id, width=320, height=50),
        width=320, height=50, centered
    )
```
- **No preload** — `BannerAd` loads itself on mount
- **No reload logic** — Flet handles refresh internally
- **Collapses to 0×0** for premium/desktop/no-consent — zero layout shift

### Interstitial (AdService.preload_interstitial → show_interstitial)
**File**: `src/services/ad_service.py:167-292`

```python
# PRELOAD (single-use in flet-ads 1.0)
async def preload_interstitial(self, on_close=None):
    self._on_close = on_close
    if premium or not mobile or not _HAS_ADS or not _can_request_ads:
        return
    self._interstitial_loaded = False
    self._interstitial_shown = False
    self.interstitial = fta.InterstitialAd(
        unit_id=self.interstitial_id,
        on_load=self._handle_loaded,
        on_error=self._handle_error,
        on_close=self._handle_close,
    )
    self.page.services.append(self.interstitial)

# HANDLERS
_handle_loaded:   _interstitial_loaded=True; if _pending_interstitial → run _show_loaded()
_handle_error:    interstitial=None; _interstitial_loaded=False; _pending_interstitial=False
_show_loaded:     await interstitial.show(); _interstitial_shown=True; last_interstitial_ts=now
_handle_close:    _interstitial_shown=False; run _on_close; preload_interstitial(on_close=_on_close)

# SHOW (with 60s central gap guard in state.last_interstitial_ts)
async def show_interstitial(self) -> bool:
    if premium or not mobile or not _HAS_ADS or not _can_request_ads: return False
    if now - state.last_interstitial_ts < MIN_INTERSTITIAL_GAP (60s): return False
    if interstitial ready & loaded & not shown:
        await interstitial.show(); _interstitial_shown=True; last_interstitial_ts=now; return True
    if _pending_interstitial: return True  # already queued
    _pending_interstitial=True
    await preload_interstitial(on_close=self._on_close)
    return True
```

**Key invariants**:
- **Single-use**: each `InterstitialAd` shown once, then replaced
- **60s global gap** (`MIN_INTERSTITIAL_GAP`) enforced in `state.last_interstitial_ts`
- **Preload-on-startup**: `main.py:267` runs immediately after consent
- **Auto-reload after show**: `_handle_close` → `preload_interstitial()` for next impression
- **Queueing**: `_pending_interstitial` prevents double-load; gap only stamped on actual show

### Rewarded Interstitial (AdService.show_rewarded_interstitial)
**File**: `src/services/ad_service.py:294-350`

```python
async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
    if premium or not _HAS_ADS or not mobile:
        logger.info("No rewarded ad available - granting nothing")
        await on_close()  # still continue flow, but NO REWARD
        return False

    self._active_rewarded_ad = fta.InterstitialAd(
        unit_id=self.interstitial_id,  # SAME ID as regular interstitial
        on_load=lambda e: page.run_task(_show, e),
        on_close=lambda e: page.run_task(_close, e),
        on_error=...,
    )
    page.services.append(self._active_rewarded_ad)
    return True
```

**Critical rule** (lines 298-303): **Reward MUST be paid for by an ad that actually closed**. Desktop/web/premium → `on_close` fires but returns `False`, grants nothing.

---

## 4. House Helpers Worth Copying

| Helper | Location | Purpose |
|--------|----------|---------|
| `build_banner_ad(page, unit_id?)` | `src/core/styles.py:108` | Glass-wrapped banner, collapses on premium/desktop, centers horizontally, adaptive glass bg/border |
| `AdService._is_mobile()` | `src/services/ad_service.py:83-94` | `not page.web and page.platform.is_mobile()` — single platform gate |
| `AdService._premium` property | `src/services/ad_service.py:74-81` | Reads `state.is_premium` — single source of truth |
| `page_has_ads(page, state, services)` | `src/screens/settings/premium_section.py:76-91` | Detects if ads *can* show (for premium pitch copy) |
| `MIN_INTERSTITIAL_GAP = 60.0` | `src/services/ad_service.py:31` | Central cooldown in `state.last_interstitial_ts` |
| `_pending_interstitial` flag | `src/services/ad_service.py:49, 200, 280, 286` | Prevents double-load; gap only spent on real impression |
| `_can_request_ads` (UMP consent) | `src/services/ad_service.py:98-115` | `gather_consent()` runs UMP, sets flag; defaults to `True` on failure |

---

## 5. Port to animepahe-tv — Concrete Checklist

### Current animepahe-tv state (per task):
- Interstitial before each episode resolve + 30s guard + preload
- App-open on cold start + resume 4h
- Banners: home/discover/search/detail/downloads/settings
- **WRONG**: 'Personalised ads' settings toggle (must DELETE)

### What to ADD (from ColabShell):
- [ ] **UMP Consent flow** — `AdService.gather_consent()` at boot, `_can_request_ads` gate
- [ ] **Central 60s interstitial gap** — single `state.last_interstitial_ts` (not per-screen)
- [ ] **Single-use interstitial reload pattern** — `_handle_close` → `preload_interstitial()` auto-queue
- [ ] **Rewarded interstitial with SAME unit ID** — no separate rewarded ad unit
- [ ] **Reward ONLY on actual ad close** — desktop/premium → `on_close` fires but returns `False`, grants nothing
- [ ] **`build_banner_ad()` helper** — glass-wrapped, collapses to 0×0, adaptive theming
- [ ] **`page_has_ads()` helper** — for premium pitch copy
- [ ] **Premium entitlement check** — `state.is_premium` gate in every ad call site

### What to REMOVE (from animepahe-tv):
- [ ] **'Personalised ads' settings toggle** — DELETE entirely (ColabShell has ZERO ad toggles)
- [ ] **App-open interstitial** — ColabShell does NOT do this; only preloads on cold start
- [ ] **4h resume app-open guard** — REMOVE
- [ ] **Per-screen interstitial guards** — REPLACE with central `state.last_interstitial_ts` 60s gap
- [ ] **Separate rewarded ad unit ID** — USE same `interstitial_id` for rewarded

### What to CHANGE (in animepahe-tv):
- [ ] **Interstitial gap**: 30s → **60s** (ColabShell standard)
- [ ] **Banner placement**: adopt exact ColabShell screens (home×2, session selector, files, history, settings×2, notebook every 2nd cell)
- [ ] **Interstitial triggers**: ONLY `new_session_sheet` (before provisioning) + central preload; REMOVE episode-resolve trigger
- [ ] **Rewarded triggers**: ONLY gated actions (download, export, credits top-up) — NOT episode resolve
- [ ] **Banner collapse**: 0×0 Container for premium/desktop/no-consent (not `visible=false`)
- [ ] **Ad IDs**: Use single banner + single interstitial ID (same for rewarded)

---

## 8-Bullet Summary

- **One AdService class** owns all formats: banner, interstitial, rewarded (same interstitial unit ID)
- **UMP consent at boot** → `_can_request_ads` gate; defaults `True` on failure
- **Zero user-facing ad controls** — premium (`state.is_premium`) is the only off-switch
- **Banners**: `build_banner_ad()` helper → glass-wrapped, 320×50, collapses to 0×0 on premium/desktop
- **Interstitials**: single-use, preload on startup, **60s central gap** (`state.last_interstitial_ts`), auto-reload after show via `_handle_close`
- **Rewarded**: same interstitial ID, **reward ONLY on real ad close** (desktop/premium → `on_close` fires but `False`, no grant)
- **Placements**: 10 banner slots (home×2, session selector, files, history, settings×2, notebook cells×2), 1 interstitial trigger (new session), 3 rewarded (wallet, download, export)
- **App-open ads**: NOT implemented in ColabShell — preload only on cold start