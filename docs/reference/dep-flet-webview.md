# flet-webview 0.85.3 — complete API reference (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/flet_webview/` — 3 files: `__init__.py`, `types.py`,
> `webview.py`). Every signature below was verified live via `uv run python`
> (`inspect.signature` + construction tests) from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.

`Name: flet-webview, Version: 0.85.3, Requires-Python: >=3.10, Requires-Dist: flet==0.85.3, Apache-2.0`
Verified live: `importlib.metadata.version('flet-webview') == '0.85.3'`,
`version('flet') == '0.85.3'`. Based on Flutter `webview_flutter` /
`webview_flutter_web` (per METADATA description).

`__all__ = ["JavaScriptMode", "LogLevelSeverity", "RequestMethod", "WebView",
"WebViewConsoleMessageEvent", "WebViewJavaScriptEvent", "WebViewScrollEvent"]`
(`__init__.py`, lines 1-19).

Platform support matrix (from `flet-webview-0.85.3.dist-info/METADATA`):

| Platform | Windows | macOS | Linux | iOS | Android | Web |
|---|---|---|---|---|---|---|
| Supported | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ |

The `WebView` class docstring (`webview.py:19-26`) narrows this further:
"Supported only on the following platforms: iOS, Android, macOS, and Web"
and points Windows/Linux support at
`https://github.com/flet-dev/flet-webview/issues/17`.

## 1. Constructor — EVERY parameter

```python
@ft.control("WebView")
class WebView(ft.LayoutControl): ...   # webview.py:17-18
```

MRO (verified live): `WebView -> LayoutControl -> Control -> BaseControl -> object`.

Own parameters (defaults all `None`; verified via `inspect.signature(WebView.__init__)`):

```python
(url: Optional[str] = None,
 prevent_links: Optional[list[str]] = None,
 bgcolor: Optional[ft.ColorValue] = None,
 on_page_started: Optional[ft.ControlEventHandler["WebView"]] = None,
 on_page_ended: Optional[ft.ControlEventHandler["WebView"]] = None,
 on_web_resource_error: Optional[ft.ControlEventHandler["WebView"]] = None,
 on_progress: Optional[ft.ControlEventHandler["WebView"]] = None,
 on_url_change: Optional[ft.ControlEventHandler["WebView"]] = None,
 on_scroll: Optional[ft.EventHandler[WebViewScrollEvent]] = None,
 on_console_message: Optional[ft.EventHandler[WebViewConsoleMessageEvent]] = None,
 on_javascript_alert_dialog: Optional[ft.EventHandler[WebViewJavaScriptEvent]] = None,
 # ...plus all LayoutControl/Control kwargs (expand, width, height, visible, ...))
```

Semantics per docstring (`webview.py:28-114`):

- `url: Optional[str]` — "The URL of the web page to load." Settable any time;
  assigning a new URL navigates (standard Flet control property behavior).
- `prevent_links: Optional[list[str]]` — "List of url-prefixes that should not
  be followed/loaded/downloaded."
- `bgcolor: Optional[ft.ColorValue]` — "Defines the background color of the WebView."
- `on_page_started` — "Fires soon as the first loading process of the webview
  page is started." `e.data: str` = URL. iOS/Android/macOS only.
- `on_page_ended` — "Fires when all the webview page loading processes are
  ended." `e.data: str` = URL. iOS/Android/macOS only.
- `on_web_resource_error` — "Fires when there is error with loading a webview
  page resource." `e.data: str` = error message. iOS/Android/macOS only.
- `on_progress` — "Fires when the progress of the webview page loading is
  changed." `e.data: int` = progress value. iOS/Android/macOS only.
- `on_url_change` — "Fires when the URL of the webview page is changed."
  `e.data: str` = new URL. iOS/Android/macOS only.
- `on_scroll` — `WebViewScrollEvent`, iOS/Android only.
- `on_console_message` — `WebViewConsoleMessageEvent`, iOS/Android/macOS only.
- `on_javascript_alert_dialog` — `WebViewJavaScriptEvent`, iOS/Android/macOS only.

Parameters that **do NOT exist** in 0.85.3 (verified: `TypeError` on construction):

| Name asked about | Verdict |
|---|---|
| `javascript_mode` (ctor kwarg) | REJECTED — `WebView.__init__() got an unexpected keyword argument 'javascript_mode'`. JS mode is a **method**: `set_javascript_mode(mode)` (`webview.py:374`). |
| `zoom_enabled` (ctor kwarg) | REJECTED — same `TypeError`. Zoom is **methods**: `enable_zoom()` / `disable_zoom()` (`webview.py:188-206`). |
| `scrolling_enabled` | Does not exist in any form (no attribute, no method). |
| `user_agent` (ctor kwarg) | Does not exist. There is only a **getter**: `get_user_agent()` (`webview.py:261`). No setter anywhere. |
| `on_page_finished` | REJECTED — `Did you mean 'on_page_ended'?` The correct name is `on_page_ended`. |
| `on_page_started`/`on_page_finished` pair | Only `on_page_started` + `on_page_ended` exist. |
| `on_web_resource_received`, `on_http_response`, request interception | Do not exist. No such attribute or method (`webview.py` has 11 handlers total, listed above). |

## 2. Method surface — complete

All 17 async methods are gated by `_check_mobile_or_mac_platform`
(`webview.py:116-129`):

```python
def _check_mobile_or_mac_platform(self):
    if self.page is None:
        raise RuntimeError("WebView must be added to page first.")
    if self.page.web or self.page.platform not in [
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.IOS,
        ft.PagePlatform.MACOS,
    ]:
        raise ft.FletUnsupportedPlatformException(
            "This method is supported on Android, iOS and macOS platforms only."
        )
```

Consequences (verified against source): every method raises `RuntimeError` if
the control is not on a page yet, and `ft.FletUnsupportedPlatformException` on
Flet-Web (`page.web` truthy), Windows, Linux — **and `ANDROID_TV`**, which is a
separate `PagePlatform` member not in the allow-list (verified live:
`[m.name for m in ft.PagePlatform] == ['IOS','ANDROID','ANDROID_TV','MACOS','WINDOWS','LINUX']`).
See §6 for what this means for the TV path.

Signatures (verified live via `inspect`):

```python
async def reload(self) -> None                          # webview.py:131
async def can_go_back(self) -> bool                     # webview.py:141
async def can_go_forward(self) -> bool                  # webview.py:154
async def go_back(self) -> None                         # webview.py:167
async def go_forward(self) -> None                      # webview.py:177
async def enable_zoom(self) -> None                     # webview.py:188
async def disable_zoom(self) -> None                    # webview.py:198
async def clear_cache(self) -> None                     # webview.py:208
    # clears browser HTTP cache + Cache API caches + application cache
async def clear_local_storage(self) -> None             # webview.py:223
async def get_current_url(self) -> Optional[str]        # webview.py:233
    # current URL, or None if no URL was ever loaded
async def get_title(self) -> Optional[str]              # webview.py:248
async def get_user_agent(self) -> Optional[str]         # webview.py:261
    # value of the HTTP User-Agent request header
async def load_file(self, path: str) -> None            # webview.py:274
async def load_request(self, url: str,
    method: RequestMethod = RequestMethod.GET) -> None  # webview.py:290
async def run_javascript(self, value: str) -> None      # webview.py:306
    # returns None — fire-and-forget; there is NO value-returning eval
async def load_html(self, value: str,
    base_url: Optional[str] = None) -> Self             # webview.py:322
async def scroll_to(self, x: int, y: int) -> None       # webview.py:340
async def scroll_by(self, x: int, y: int) -> None       # webview.py:357
async def set_javascript_mode(self, mode: JavaScriptMode) -> None  # webview.py:374
    # DISABLED may cause "unexpected web page behaviour" per docstring
```

Methods that **do NOT exist** (verified live with `hasattr` → all `False`):

- `evaluate_javascript` / `run_javascript_returning_result` / `inject_javascript`
- `clear_all` (only `clear_cache` + `clear_local_storage` separately)
- any cookie API (`get_cookies`, `set_cookies`, `clear_cookies` — none exist)
- any `set_user_agent` (getter only)

`run_javascript` source (`webview.py:306-320`) awaits `_invoke_method` but
discards the result and returns `None`. There is therefore **no supported way
to get a JS expression value back** — the only data path from page → Python is
`console.log(...)` → `on_console_message`, or navigation events.

## 3. Event payloads

`ft.Event` dataclass fields (verified live): `['name', 'data', 'control']`.
**There is no `.url` attribute on events** — URL/error/progress payloads arrive
in `e.data`. Handler type matters:

- `ft.ControlEventHandler["WebView"]` handlers (`on_page_started`,
  `on_page_ended`, `on_web_resource_error`, `on_progress`, `on_url_change`)
  receive a plain event whose **`data`** carries the payload:
  - `on_page_started`: `data: str` = URL that started loading
  - `on_page_ended`: `data: str` = URL that finished loading
  - `on_web_resource_error`: `data: str` = error message
  - `on_progress`: `data: int` = progress value
  - `on_url_change`: `data: str` = new URL
- Typed `ft.EventHandler[...]` handlers receive dataclass instances:

```python
@dataclass
class WebViewScrollEvent(ft.Event["WebView"]):   # types.py:62-80
    x: float   # horizontal offset, origin at leftmost of the WebView
    y: float   # vertical offset, origin at topmost of the WebView
    # fires on scroll-position change; iOS + Android only

@dataclass
class WebViewConsoleMessageEvent(ft.Event["WebView"]):  # types.py:83-93
    message: str                  # text written to the console
    severity_level: LogLevelSeverity  # ERROR/WARNING/DEBUG/INFO/LOG
    # fires when JS writes to console; iOS/Android/macOS only

@dataclass
class WebViewJavaScriptEvent(ft.Event["WebView"]):      # types.py:96-108
    message: str  # text of the alert() message
    url: str      # URL of the page requesting the dialog
    # fires when the page calls alert(); iOS/Android/macOS only
```

Enums (`types.py:20-60`):

```python
class RequestMethod(Enum): GET = "get"; POST = "post"
class JavaScriptMode(Enum): UNRESTRICTED = "unrestricted"; DISABLED = "disabled"
class LogLevelSeverity(Enum): ERROR="error"; WARNING="warning"; DEBUG="debug"; INFO="info"; LOG="log"
```

`LogLevelSeverity` maps `console.error/warning/debug/info/log` (per docstrings,
`types.py:30-49`).

## 4. Cookie handling

The control exposes **no cookie API at all** — verified: `webview.py` contains
no `cookie` string in any form; the full method list in §2 has no cookie
method. Consequences:

- Everything cookie-related must come from platform APIs (pyjnius
  `android.webkit.CookieManager` on Android) or from JS (`document.cookie`
  round-tripped through `console.log` → `on_console_message`).
- `HttpOnly` visibility: `document.cookie` **never** includes `HttpOnly`
  cookies (`cf_clearance` is `HttpOnly`), so the `console.log('COOKIE:' +
  document.cookie)` fallback can never capture `cf_clearance`. On Android the
  native `CookieManager.getCookie(url)` **does** include `HttpOnly` cookies —
  that is the only working capture path, which matches the design in
  `src/services/webview_solver.py:_solve_mobile` (pyjnius primary,
  `document.cookie` last-resort-only).
- There is no `clear_cookies` either: `clear_cache()` (HTTP/Cache-API/app
  caches) + `clear_local_storage()` are the closest reset primitives; cookies
  themselves cannot be cleared through this control.

## 5. Desktop behavior under `flet run` + platform notes

- `flet-webview` renders through Flutter platform views. On desktop
  (`flet run` on Windows/Linux) third-party extension controls are not built
  into the desktop runner, so `WebView` shows as an **unknown control** —
  this is the `flet-dev/flet#5168` context referenced in
  `src/services/webview_solver.py:solve_challenge` (the fetch of the issue
  page itself failed in this environment, so the issue-number claim rests on
  the code comment, not on the GitHub page).
- Our app's workaround (verified in `src/services/webview_solver.py:24-38`):
  `solve_challenge` routes mobile-family platforms to the in-app `WebView`
  and everything else to a `pywebview` subprocess (`desktop_cf_solver.py`).
  The routing predicate is `page.platform.is_mobile() or
  page.platform == ft.PagePlatform.ANDROID_TV` (verified live:
  `ANDROID.is_mobile() == True`, `ANDROID_TV.is_mobile() == False`, so the
  explicit TV comparison carries the TV case).
- Platform gate risk for TV: `_check_mobile_or_mac_platform` allows only
  `ANDROID/IOS/MACOS`. If Flutter reports an Android TV device as
  `PagePlatform.ANDROID_TV` at runtime, **every** `WebView` method
  (`get_current_url`, `run_javascript`, `scroll_by`, …) raises
  `FletUnsupportedPlatformException` on that device. Whether a real TV reports
  `ANDROID` or `ANDROID_TV` was not observable in this environment — flagged
  as a runtime verification item, not a confirmed bug.

## 6. CF-solver-relevant API we are NOT using

All of these exist in installed 0.85.3 and are usable from the mobile solver
today (file:line cited; all gated to Android/iOS/macOS as in §2):

- `get_title() -> Optional[str]` (`webview.py:248`) — page title without JS.
- `get_user_agent() -> Optional[str]` (`webview.py:261`) — real request UA
  without JS.
- `on_progress` (`data: int`) — loading-progress signal; Cloudflare
  interstitials stall/reload in distinctive progress patterns.
- `on_url_change` (`data: str` = new URL) — navigation signal; cheaper and
  earlier than polling `get_current_url()` every 1.5 s.
- `on_web_resource_error` (`data: str` = error message) — detects challenge
  resource failures / blocks.
- `on_javascript_alert_dialog` (`WebViewJavaScriptEvent`) — surfaces pages
  that use `alert()`.
- `prevent_links: list[str]` (ctor) — block URL prefixes from being
  followed/loaded/downloaded during the challenge.
- `load_request(url, method=RequestMethod.GET/POST)` (`webview.py:290`) —
  re-issue the target URL as GET or POST without rebuilding the control.
- `clear_cache()` / `clear_local_storage()` (`webview.py:208/223`) — reset
  solver state between attempts.
- `enable_zoom()` / `disable_zoom()` (`webview.py:188/198`) — the supported
  zoom switch (method, not a ctor flag).
- `set_javascript_mode(JavaScriptMode.UNRESTRICTED)` (`webview.py:374`) — the
  supported JS-mode call (method, not a ctor flag).
- `can_go_back/go_back/can_go_forward/go_forward` (`webview.py:141-186`) —
  history navigation if the challenge redirects away.
- `load_html(value, base_url=None)` (`webview.py:322`) — render interstitial
  HTML locally.
- `scroll_to(x, y)` (`webview.py:340`) — absolute scroll (solver uses only
  relative `scroll_by`).

Explicitly **absent** (checked the complete 17-method list, so a solver design
must not rely on these): `on_http_response` / any response or request
interception, custom-User-Agent setter, value-returning JS evaluation,
`clear_all`, cookie get/set/clear.

## 7. Correctness notes on our current usage (`src/services/webview_solver.py`)

Bugs found by testing the solver's calls against the installed package
(verified live; fix recommendations):

1. `WebView(..., javascript_mode="unrestricted", zoom_enabled=False, ...)`
   (`webview_solver.py:252-262`) raises `TypeError: WebView.__init__() got an
   unexpected keyword argument 'javascript_mode'` (first failure wins; the
   `zoom_enabled` kwarg fails identically). Neither ctor parameter exists —
   use `set_javascript_mode(JavaScriptMode.UNRESTRICTED)` (method,
   `webview.py:374`) and `disable_zoom()` (method, `webview.py:198`) after the
   control is mounted, or drop both (defaults already allow JS/zoom).
2. `on_page_finished=on_page_ended` (`webview_solver.py:261`) raises
   `TypeError ... Did you mean 'on_page_ended'?`. Rename to `on_page_ended`.
3. `webview.run_javascript_returning_result(...)` (`webview_solver.py:164`,
   `212`) does not exist (`hasattr == False`). `run_javascript` returns
   `None`. Title/UA reads must use `get_title()` / `get_user_agent()`, or keep
   the `console.log` → `on_console_message` round-trip for cookie strings.
4. `e.url` in `on_url_change`/`on_page_ended` handlers
   (`webview_solver.py:232-244`) — `ft.Event` has fields
   `name/data/control` only (verified live); the URL is `e.data`, so `e.url`
   raises `AttributeError` at runtime. The inline comments claiming
   "flet_webview's WebView has no get_title()/get_user_agent()" are also
   factually wrong — both exist (§6).
5. TV gate risk — see §5: if the device reports `ANDROID_TV`, all method
   calls raise. Needs a runtime check on real TV hardware.

## 8. App improvement opportunities

Every item below cites a verified source (file + signature from §§1-3).
Items that could not be verified against the installed package are separated
at the end. Ordered by expected impact on the Cloudflare solver.

1. **Replace the 1.5 s `get_current_url()` poll with `on_url_change`.**
   `on_url_change: Optional[ft.ControlEventHandler["WebView"]]` delivers the
   new URL in `e.data: str` the moment navigation happens (`webview.py:81-90`).
   The solver currently polls `get_current_url()` (`webview_solver.py:264-300`);
   an event-driven navigation signal shortens challenge-completion detection
   from up to one poll interval to ~instant and removes a periodic
   `_invoke_method` round-trip that competes with the challenge JS for CPU on
   low-power TV hardware.
2. **Replace the title/UA JS round-trips with `get_title()` /
   `get_user_agent()`.** `async def get_title(self) -> Optional[str]`
   (`webview.py:248`) and `async def get_user_agent(self) -> Optional[str]`
   (`webview.py:261`) are native getters. The solver's
   `run_javascript_returning_result("document.title" / "navigator.userAgent")`
   calls cannot work (method absent, §2) — these getters are the drop-in fix
   and also remove two `console.log`-channel dependencies from the
   `_try_resolve` hot path.
3. **Add `on_progress` + `on_web_resource_error` as challenge-state signals.**
   `on_progress` (`e.data: int`, `webview.py:70-79`) exposes load-progress
   changes; `on_web_resource_error` (`e.data: str` error message,
   `webview.py:59-68`) fires on resource-load failures. Together they let the
   solver distinguish "challenge still working" (progress moving) from
   "challenge stalled/failed" (error or progress stuck) instead of inferring
   state from title strings alone.
4. **Reset state between attempts with `clear_cache()` /
   `clear_local_storage()`.** `async def clear_cache(self) -> None`
   (`webview.py:208`, clears HTTP + Cache-API + app caches) and
   `async def clear_local_storage(self) -> None` (`webview.py:223`). Calling
   both before loading the challenge URL gives each solve attempt a clean
   slate, avoiding stale `cf_clearance`/service-worker state from a previous
   run poisoning retries. (Neither clears cookies — §4 — so this complements
   rather than replaces the pyjnius cookie path.)
5. **Pin the challenge flow with `prevent_links` + history guard.**
   `prevent_links: Optional[list[str]]` (`webview.py:31-32`) blocks
   URL-prefixes from being followed/loaded/downloaded — useful to keep the
   solver on the challenge/target host. `can_go_back()/go_back()` and
   `can_go_forward()/go_forward()` (`webview.py:141-186`) recover if the
   challenge redirects away.
6. **Use `set_javascript_mode(JavaScriptMode.UNRESTRICTED)` explicitly after
   mount.** `async def set_javascript_mode(self, mode: JavaScriptMode)`
   (`webview.py:374`; enum `types.py:52-60`). Guarantees the challenge JS runs
   even if a future default changes, and replaces the crashing
   `javascript_mode=` ctor kwarg with the API that actually exists.
7. **Use `disable_zoom()` / `enable_zoom()` methods for the TV experience.**
   `async def enable_zoom/disable_zoom(self)` (`webview.py:188-206`) are the
   supported zoom switch — the solver's `zoom_enabled=False` kwarg crashes
   (§7.1). Disabling zoom after mount keeps the current no-DOM-mutation
   stance (no viewport CSS injection) while using a real API.
8. **Fix the event payload access (`e.data`, not `e.url`).** All five
   `ControlEventHandler` events deliver payloads in `e.data`
   (`ft.Event` fields `name/data/control`, verified live). One-line fix in
   both handlers; without it the solver's navigation/title logic raises
   `AttributeError` on first navigation.

Unverified / explicitly absent — checked and NOT in installed 0.85.3, so no
improvement can be built on them without a different package or version:

- HTTP response inspection / request interception (`on_http_response` or
  similar): no such handler or method in `webview.py`; full 11-handler /
  17-method enumeration in §§1-2 is the evidence.
- Custom User-Agent override: only `get_user_agent()` getter exists
  (`webview.py:261`); no setter, no ctor parameter.
- Value-returning JS evaluation: `run_javascript` returns `None`
  (`webview.py:306-320`, source read); `evaluate_javascript` /
  `run_javascript_returning_result` / `inject_javascript` all `hasattr ==
  False`. The `console.log` → `on_console_message` channel
  (`WebViewConsoleMessageEvent.message: str`, `types.py:83-93`) remains the
  only page→Python data path.
- Native cookie get/set/clear: zero cookie surface in the package (§4).
- Whether `flet-dev/flet#5168` is still the reason desktop needs the
  `pywebview` subprocess: the issue page could not be fetched in this
  environment, so that attribution rests on the code comment in
  `webview_solver.py:27-30`, not on an independently verified issue.
- Whether real Android TV hardware reports `PagePlatform.ANDROID` (methods
  work) or `ANDROID_TV` (all methods raise per `webview.py:116-129`):
  needs a runtime check on device; both enum members exist (verified live).
