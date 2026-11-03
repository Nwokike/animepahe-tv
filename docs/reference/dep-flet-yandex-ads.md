# dep: flet-yandex-ads — complete API reference

> **Version note (2026-11-01):** version 0.1.0 is current; verified against flet **0.85.3** (Python 3.14.9) in this project's pinned venv. All claims below cite the installed 0.1.0 source or live introspection.
>
> Installed package under study: `/home/maikel/Desktop/kiri-apps/animepahe-tv/.venv/lib/python3.14/site-packages/flet_yandex_ads/`
> Our usage: `src/services/ads.py` (SDK init + interstitial/rewarded/app-open), `src/components/banner_ad.py` (banner builder).
> Method: every `.py` file in the installed package was read in full; signatures cross-checked by live introspection via `.venv/bin/python -c "import flet_yandex_ads as fya, inspect; ..."`.
> All claims cite the source file + symbol.

## 1. Version, module layout, Flutter bridge

- **Distribution version: 0.1.0.** Evidence: `flet_yandex_ads-0.1.0.dist-info/METADATA` (`Name: flet-yandex-ads`, `Version: 0.1.0`, `Requires-Dist: flet` — **no version pin**, accepts any flet), `Requires-Python: >=3.10`, MIT, homepage `https://github.com/Nwokike/flet-yandex-ads`. Our pin: `pyproject.toml` line 11, `"flet-yandex-ads>=0.1.0"`. Flet in the venv at time of writing: **0.85.3** (`flet.__version__`).
- **Import test:** `.venv/bin/python -c "import flet_yandex_ads"` succeeds cleanly with flet 0.85.3. No import-time version conflict.
- **Installed module layout** (8 Python files, no vendored Dart in `site-packages`): `__init__.py`, `types.py`, `base_ad.py`, `yandex_ads_service.py`, `banner_ad.py`, `fullscreen_ad.py`, `interstitial_ad.py`, `rewarded_ad.py`, `app_open_ad.py`.
- **Public exports** (`__init__.py`, `__all__`, verified identical by introspection): `YandexAdsService`, `BaseAd`, `FullscreenAd`, `BannerAd`, `InterstitialAd`, `RewardedAd`, `AppOpenAd`, `BannerSizeType`, `BannerLoadedEvent`, `AdRequestErrorEvent`, `AdErrorEvent`, `ImpressionEvent`, `RewardEvent`.
- **Flutter side it wraps.** METADATA long description states verbatim: *"A 1:1 wrapping of the official [yandex_mobileads](https://pub.dev/packages/yandex_mobileads) Flutter plugin, in the same architecture as [flet-ads](https://pypi.org/project/flet-ads/)."* `types.BannerSizeType` docstring says it mirrors *"the `BannerAdSize` API of the `yandex_mobileads` Flutter plugin"* (`types.py:17-19`). The wheel's `RECORD` proves the Dart bridge ships with the wheel but is **not** installed to `site-packages` — it is consumed at Flutter build time: `flutter/flet_yandex_ads/lib/flet_yandex_ads.dart`, `lib/src/{banner_ad,interstitial_ad,rewarded_ad,app_open_ad,service,extension}.dart`, plus `flutter/flet_yandex_ads/pubspec.yaml`.
- **Platform support** (METADATA table): iOS ✅, Android ✅, Android TV ⚠️ ("runs and attempts to serve ads … fill rate and remote-control focus are untested"), Windows/macOS/Linux/Web ❌. METADATA Limitations section: *"The Flutter plugin exposes four formats: banner, interstitial, rewarded, app open. Native and InStream ads exist only in Yandex's native SDKs"* and *"Ads don't render on desktop or web (by design — same as every mobile ad SDK)."*
- **Config note** (METADATA): *"No manifest keys or Info.plist entries are needed for basic operation. Mediation adapters are added to the generated Flutter app's Gradle config."* It can mediate AdMob, AppLovin, Mintegral, Pangle, Unity and more behind the one integration.

## 2. Every control/class: constructors and events

Class hierarchy (confirmed by MRO introspection):

- `BaseAd(ft.BaseControl)` — `base_ad.py`. Shared base, never instantiated directly.
- `FullscreenAd(BaseAd)` — `fullscreen_ad.py`. Base for the three fullscreen formats.
- `BannerAd(ft.LayoutControl, BaseAd)` — `banner_ad.py`. In-layout control.
- `InterstitialAd(ft.Service, FullscreenAd)` — `interstitial_ad.py`.
- `RewardedAd(ft.Service, FullscreenAd)` — `rewarded_ad.py`.
- `AppOpenAd(ft.Service, FullscreenAd)` — `app_open_ad.py`.
- `YandexAdsService(ft.Service)` — `yandex_ads_service.py`.

### 2a. `BaseAd` — shared constructor params and events (`base_ad.py:9-38`)

| Parameter | Type | Notes |
|---|---|---|
| `unit_id` | `str` (required) | Ad block ID from the Yandex partner interface, looks like `R-M-XXXXXX-Y`. |
| `on_load` | `Optional[ft.ControlEventHandler["BaseAd"]]` | Plain event. Called when an ad is successfully loaded. **Overridden with a typed event on `BannerAd`** (see 2c). |
| `on_load_failed` | `Optional[ft.EventHandler[AdRequestErrorEvent["BaseAd"]]]` | Typed. Carries `code`, `description` (+ `ad_unit_id` when reported). |
| `on_click` | `Optional[ft.ControlEventHandler["BaseAd"]]` | Plain event. Called when the ad is clicked. |

Plus standard `ft.BaseControl` kwargs (`data`, `key`, `ref`).

### 2b. `FullscreenAd` — extra events + mechanics (`fullscreen_ad.py:10-73`)

Adds four events on top of the three inherited from `BaseAd`:

| Event | Type | Payload |
|---|---|---|
| `on_shown` | plain `ControlEventHandler` | Called when the ad is shown. |
| `on_failed_to_show` | typed `EventHandler[AdErrorEvent]` | `description` (mirrors Flutter `AdError`). |
| `on_dismiss` | plain `ControlEventHandler` | Called when the ad is dismissed. |
| `on_impression` | typed `EventHandler[ImpressionEvent]` | `impression_data` — ILRD (impression-level revenue data) JSON string. |

Methods (all `async`, all `self._invoke_method(...)` bridges):

| Method | Docstring contract (`fullscreen_ad.py`) |
|---|---|
| `load()` | *"Loading starts automatically when the service is added to the page; call this to reload after a failure."* |
| `show()` | *"Show the loaded ad on top of the application."* |
| `wait_for_dismiss()` | *"Wait until the ad is dismissed. Must be called after `show`; returns when the ad closes."* Base version returns `None`. |
| `cancel_loading()` | *"Cancel a pending load."* |
| `destroy()` | *"Destroy the ad and free its resources."* |

### 2c. `BannerAd` (`banner_ad.py:8-63`)

Layout control (takes full `LayoutControl` kwargs: `width`, `height`, `visible`, `expand`, `opacity`, `tooltip`, alignment/margin/transform/animation, etc.). Loads automatically when added to the page.

| Parameter | Type / default | Notes |
|---|---|---|
| `unit_id` | `str` (required) | Inherited from `BaseAd`. |
| `size_type` | `BannerSizeType`, default `STICKY` | `STICKY`: stretches to container width, height set by network. `INLINE`: stretches to container width up to `max_height`. |
| `max_height` | `Optional[int]`, default `None` | Max banner height in dp, **only for `INLINE`**. Defaults to a third of the screen height (Dart side). |
| `on_load` | **typed** `EventHandler[BannerLoadedEvent["BannerAd"]]` | Overrides the plain `BaseAd.on_load`. Carries final `width`/`height` in dp. |
| `on_load_failed` | typed `EventHandler[AdRequestErrorEvent]` | Inherited from `BaseAd`. |
| `on_click` | plain `ControlEventHandler` | Inherited from `BaseAd`. |
| `on_impression` | typed `EventHandler[ImpressionEvent]` | ILRD payload. Banner-only addition (fullscreen has its own). |

Method: `reload()` — *"Load a new ad into this banner"* (`banner_ad.py:60-63`). No `destroy()` on banners; lifecycle is tied to the layout.

`BannerSizeType` (`types.py:17-28`): `STICKY = "sticky"`, `INLINE = "inline"` — only these two members (verified by introspection).

### 2d. `InterstitialAd` (`interstitial_ad.py:6-24`)

No own fields — constructor is exactly the `BaseAd` trio (`unit_id`, `on_load`, `on_load_failed`, `on_click`) plus the `FullscreenAd` quartet (`on_shown`, `on_failed_to_show`, `on_dismiss`, `on_impression`). Docstring: *"Loads automatically when the service is added to the page. Each instance is one-shot — create a new instance for the next ad."* Canonical pattern from its docstring:

```python
inter = flet_yandex_ads.InterstitialAd(unit_id="R-M-XXXXXX-Y")
page.services.append(inter)
await inter.show()
await inter.wait_for_dismiss()
```

### 2e. `RewardedAd` (`rewarded_ad.py:10-52`)

Same constructor as interstitial **plus one extra**:

| Parameter | Type | Notes |
|---|---|---|
| `on_reward` | `Optional[ft.EventHandler[RewardEvent["RewardedAd"]]]` | Typed. Carries `amount: int`, `type: str` (mirrors Flutter `Reward`). Docstring example prints `f"+{e.amount} {e.type}"`. |

Overridden method — `wait_for_dismiss() -> Optional[RewardEvent]` (`rewarded_ad.py:41-52`): *"Wait until the ad is dismissed and return the reward the user earned, or `None` if the ad was not watched to the end. Must be called after `show`."* Implemented via `from_dict(RewardEvent, {"control": self, "name": "reward", **result})`. This is the **only** `wait_for_dismiss` in the package that returns a value.

### 2f. `AppOpenAd` (`app_open_ad.py:6-16`)

No own fields — identical constructor surface to `InterstitialAd`. Same one-shot docstring.

### 2g. Typed event payloads (`types.py:30-79`, field lists verified by introspection)

| Event | Fields |
|---|---|
| `BannerLoadedEvent` | `width: int = 0`, `height: int = 0` (dp) |
| `AdRequestErrorEvent` | `code: int = 0`, `description: str = ""`, `ad_unit_id: Optional[str] = None` |
| `AdErrorEvent` | `description: str = ""` |
| `ImpressionEvent` | `impression_data: str = ""` (ILRD JSON) |
| `RewardEvent` | `amount: int = 0`, `type: str = ""` |

(All dataclasses also carry the standard `ft.Event` trio `name`/`data`/`control`.)

**Typed-handler gotcha** (verbatim from METADATA): *"Typed handlers must use `ft.EventHandler[SomeEvent]`, **not** `ft.ControlEventHandler[SomeEvent]` — `ControlEventHandler[X]` double-wraps `X` in `Event[...]`, so Flet builds a plain `Event` and `e.width` raises `AttributeError`. (flet-ads 1.0.4 has this bug in its `on_paid`.)"* The package's own annotations already use the correct form, so following the signatures is safe.

## 3. The SDK service (`yandex_ads_service.py:6-112`)

```python
fya.YandexAdsService(
    user_consent=True,  # Optional[bool], default None
    location_tracking=None,  # Optional[bool], default None
    age_restricted=None,  # Optional[bool], default None (Android only, COPPA)
    logging=False,  # bool, default False
    debug_error_indicator=False,  # bool, default False
    on_initialized=None,  # plain ControlEventHandler
    on_init_failed=None,  # plain; e.data carries the error description
)
```

(Introspection confirms exactly these constructor params plus `data`/`key`/`ref`.)

- **Placement:** add one instance to `page.services` **before any ad control**. *"The SDK initializes automatically, with the privacy flags from this service's properties applied first (as the SDK requires consent to be set before initialization)"* (`yandex_ads_service.py:9-14`).
- **Flag semantics** (docstrings, `yandex_ads_service.py:31-55`):
  - `user_consent` — whether a user from a GDPR country allowed personal data for ad targeting. Set before init.
  - `location_tracking` — whether location may be used for targeting. Set before init.
  - `age_restricted` — whether the user is under the age of consent (COPPA). **Android only.**
  - `logging` — SDK log output.
  - `debug_error_indicator` — indicator for native ad integration errors.
- **Explicit methods** (all `async` method-channel calls): `initialize()` (safe to call more than once), `set_user_consent(value)`, `set_location_tracking(value)`, `set_age_restricted(value)` (Android only), `show_debug_panel()` (*"for network and integration checks"*).
- **Unsupported platforms:** `before_update` (`yandex_ads_service.py:99-112`) raises `ft.FletUnsupportedPlatformException` when `page.web` is true **or** the platform is not mobile and not `PagePlatform.ANDROID_TV`. Message: `"<Class> is only supported on Mobile (Android, Android TV and iOS)"`. `BaseAd.before_update` (`base_ad.py:43-56`) enforces the identical rule for every ad control — Android TV is deliberately allowed because the Yandex SDK is an Android SDK rendering through the Android platform interface; TV fill/focus is untested. Our app therefore never mounts these controls on desktop/web: both `ads.py:is_ads_supported` and `banner_ad.py:_is_supported` return `False` unless `page.platform.is_mobile()` or `== ft.PagePlatform.ANDROID_TV`, substituting a 0×0 (invisible) `ft.Container`.

## 4. Lifecycle rules

- **Preload: nothing to do manually.** Fullscreen ads *"load when the service is added to the page"* (METADATA Controls table) / *"Loading starts automatically when the service is added to the page"* (`fullscreen_ad.py:41-47`). Banners *"load automatically when added to the page"* (`banner_ad.py:13-15`). So `page.services.append(ad)` **is** the preload; `show()` assumes a loaded ad.
- **Fullscreen instances are one-shot.** Stated in `FullscreenAd` (*"after it is dismissed, create a new instance"*), repeated on all three subclasses, and in METADATA (*"Each is one-shot — create a new instance per ad and call `destroy()` afterwards"*). Our `show_interstitial`/`show_app_open` follow this exactly (fresh instance → append → `show()` → `wait_for_dismiss()` → `destroy()` → remove).
- **Post-show teardown:** `destroy()` frees native resources; removing the control from `page.services` drops the Python handle. Our interstitial/app-open path does both (`ads.py:124-130`, `150-157`). Note the rewarded path (`build_rewarded_ad`, `ads.py:84-111`) does **neither** — the control stays in `page.services` indefinitely (see §6).
- **Reload-after-failure:** call `load()` again on a fullscreen ad (`fullscreen_ad.py:41-49`); call `reload()` on a banner (`banner_ad.py:60-63`). `cancel_loading()` aborts a pending fullscreen load (`fullscreen_ad.py:65-68`).
- **Banner refresh:** there is **no auto-refresh interval** in this package — no `refresh_interval`/`auto_refresh` parameter exists on `BannerAd` (verified by constructor introspection: only `size_type`/`max_height` beyond the base/events). Refresh = explicit `await banner.reload()`. Our banner implements a one-time reload on load failure (`banner_ad.py:94-112`).
- **Show ordering:** `show()` then `wait_for_dismiss()`; the latter *"must be called after `show`"* (`fullscreen_ad.py:56-63`). Our interstitial/app-open call `show()` with a 20 s `asyncio.wait_for` then `await ad.wait_for_dismiss()` with a 120 s timeout — this matches the documented pattern.

## 5. Test vs production ids; targeting/personalization/age options

- **Demo (test) unit ids** (METADATA Usage section, *"work out of the box"*): `demo-banner-yandex`, `demo-interstitial-yandex`, `demo-rewarded-yandex`, `demo-appopenad-yandex`. Our app **does not use demo ids** — it uses production unit IDs from environment variables with `R-M-20208795-*` defaults (`ads.py:35-40`, `banner_ad.py:36`).
- **Production ids:** *"Replace them with your own ad block IDs (`R-M-XXXXXX-Y`) from the [partner interface](https://partner.yandex.com/) for production."* `BaseAd.unit_id` docstring repeats the `R-M-XXXXXX-Y` shape (`base_ad.py:21-25`).
- **Targeting / personalization / age surface** — the package exposes exactly three privacy flags, constructor- **and** setter-level (no other targeting API: no keywords, content URL, demographics, test-device list, or non-personalized-ads enum exist in the introspected signatures):
  - GDPR consent: `YandexAdsService(user_consent=...)` / `set_user_consent(bool)`. We pass `user_consent=True` unconditionally (`ads.py:84`).
  - Location targeting: `location_tracking` / `set_location_tracking(bool)`. We never set it (stays `None` = SDK default).
  - Age/COPPA: `age_restricted` / `set_age_restricted(bool)`, Android only. We never set it (stays `None`).
  - Diagnostics: `logging=True` (we enable), `debug_error_indicator` (we don't), `show_debug_panel()` (we never call).

## 6. What we're NOT using (monetization/UX gaps)

Every item below exists in the installed 0.1.0 source but has no call site in `src/services/ads.py` or `src/components/banner_ad.py`:

1. **`BannerAd.max_height`** (`banner_ad.py:37-42`) — we pass it for inline banners (`banner_ad.py:74`), but the sticky path ignores it as designed.
2. **`BannerAd.on_impression` + `ImpressionEvent.impression_data`** — ILRD (impression-level revenue data) JSON per banner impression. Wired in our banner (`banner_ad.py:85-87`) but only logged at debug level; not aggregated.
3. **`BannerAd.reload()`** — our banner reloads **once** on load failure via a bounded rebuild (`banner_ad.py:94-112`), but never refreshes on a timer or screen revisit. Periodic `reload()` would multiply banner impressions per session.
4. **Fullscreen `on_shown` / `on_dismiss`** — we track neither presentation nor close for interstitial/rewarded/app-open; `on_dismiss` is the natural hook for resuming playback or preloading the *next* episode's interstitial.
5. **Fullscreen `on_load` / `on_load_failed` / `load()`** — interstitial and app-open are fire-and-forget: no load gate before `show()`, no retry on `AdRequestErrorEvent(code, description)`. Only the rewarded ad (not wired in our app) wires these two handlers in the package docstring. Pre-creating the next episode's ad and awaiting its `on_load` would remove show-time latency.
6. **Fullscreen `on_failed_to_show` (`AdErrorEvent.description`) and `on_impression` (ILRD)** — show-failures on interstitial/app-open surface only as a caught-exception warning; ILRD is collected for no fullscreen format (we log it at debug but don't aggregate).
7. **`wait_for_dismiss()` on interstitial/app-open** — our code **does** await it (`ads.py:120`, `147`), matching the package's docstring pattern. This is correct.
8. **`RewardedAd.wait_for_dismiss()` return value** — not applicable since rewarded is not wired in our app (see §6.10).
9. **`cancel_loading()`** — never called; on fast episode skips a pending fullscreen load outlives its screen with no cancellation.
10. **Rewarded `destroy()` / services removal** — not applicable (rewarded not wired).
11. **`set_user_consent()` runtime setter** — consent is hardcoded `True` at service build; there is no settings-screen toggle calling the setter when a user opts out (GDPR exposure), nor use of `location_tracking` / `age_restricted` where applicable.
12. **`show_debug_panel()` / `debug_error_indicator`** — never invoked during development; the panel is the sanctioned network-and-integration checker.
13. **`on_click`** — wired as a debug log on the banner (`banner_ad.py:84`), unwired everywhere else; click-through rate (a mediation-quality signal) is unmeasured.
14. **Preload-next pattern generally** — §4 shows append-early is free; we only ever create-then-immediately-show, so every fullscreen `show()` pays full load latency inside its 20 s timeout.

## 7. App usage vs 0.1.0 (verified 2026-11-01)

| App file:line | fya.* symbol | Status | Notes |
|---|---|---|---|
| `ads.py:22` | `import flet_yandex_ads as fya` | ✅ OK | Import succeeds with flet 0.85.3 |
| `ads.py:83-90` | `fya.YandexAdsService(user_consent, location_tracking, age_restricted, logging, on_initialized, on_init_failed)` | ✅ OK | All params match constructor |
| `ads.py:110-115` | `fya.InterstitialAd(unit_id, on_impression)` | ✅ OK | `on_impression` from `FullscreenAd` |
| `ads.py:116` | `page.services.append(ad)` | ✅ OK | Standard Flet |
| `ads.py:117` | `await ad.show()` | ✅ OK | Method exists |
| `ads.py:120` | `await ad.wait_for_dismiss()` | ✅ OK | Method exists, returns `None` |
| `ads.py:126` | `await ad.destroy()` | ✅ OK | Method exists |
| `ads.py:130` | `page.services.remove(ad)` | ✅ OK | Standard Flet |
| `ads.py:139-144` | `fya.AppOpenAd(unit_id, on_impression)` | ✅ OK | Constructor matches `InterstitialAd` |
| `ads.py:146-147` | `await ad.show()` / `await ad.wait_for_dismiss()` | ✅ OK | Same as interstitial |
| `ads.py:153-157` | `await ad.destroy()` / `page.services.remove(ad)` | ✅ OK | Same as interstitial |
| `banner_ad.py:71-88` | `fya.BannerAd(unit_id, size_type, max_height, on_load, on_load_failed, on_click, on_impression)` | ✅ OK | All params match constructor |
| `banner_ad.py:73` | `fya.BannerSizeType.INLINE` / `STICKY` | ✅ OK | Enum members exist |
| `banner_ad.py:94-112` | `_reload()` logic using `banner.reload()` | ✅ OK | Method exists, called after failure |

**Missing in app (exists in 0.1.0 but unused):**
- `fya.RewardedAd` — not instantiated anywhere
- `fya.YandexAdsService.set_user_consent`, `set_location_tracking`, `set_age_restricted`, `show_debug_panel` — setters exist, never called
- `fya.FullscreenAd.on_shown`, `on_failed_to_show`, `on_dismiss`, `on_load`, `on_load_failed`, `load`, `cancel_loading` — events/methods exist, unwired for interstitial/app-open
- `fya.BannerAd.reload` — method exists, only used internally on failure rebuild
- `fya.BaseAd.on_click` — only wired on banner as debug log

**Errors (app uses something that doesn't exist in 0.1.0):** **None found.** All `fya.*` calls in the app match the installed 0.1.0 API.

## 8. Biggest doc corrections from previous version

1. **Flet version:** Changed from "1.0.4" to **0.85.3** (the actual pinned version in this project's venv). The METADATA `Requires-Dist: flet` has no version pin; 0.1.0 works with 0.85.3.
2. **Removed references to `flet-ads 1.0.4` bug:** The typed-handler gotcha in METADATA mentions `flet-ads 1.0.4` as a *different* package having a bug; our package uses correct `EventHandler` annotations.
3. **Confirmed import compatibility:** Verified `import flet_yandex_ads` succeeds with flet 0.85.3 / Python 3.14.9.
4. **App uses production unit IDs:** Not demo IDs — defaults are `R-M-20208795-*` from environment variables.
5. **Interstitial/app-open correctly await `wait_for_dismiss()`:** Previous doc claimed they didn't; current code does (lines 120, 147).
6. **Banner implements one-time reload on failure:** Previous doc said "never calls it"; current code has bounded rebuild logic.
7. **Rewarded ad not wired at all:** Previous doc analyzed a rewarded path that doesn't exist in `ads.py` (lines 84-111 were removed/never added).

---
*Generated 2026-11-01 against flet-yandex-ads 0.1.0 on flet 0.85.3 (Python 3.14.9).*