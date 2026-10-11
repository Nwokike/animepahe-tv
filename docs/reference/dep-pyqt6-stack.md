# Dependency reference: PyQt6 / QtWebEngine stack (installed)

Scope: the five packages in `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\.venv\Lib\site-packages\`
as resolved by `uv` on 2026-10-11. Versions: **pyqt6 6.11.0, pyqt6-qt6 6.11.2,
pyqt6-webengine 6.11.0, pyqt6-webengine-qt6 6.11.2, pyqt6-sip 13.13.0**
(dev dependency group only — see §7). Live introspection was done with
`uv run python` from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.

Upstream verdict first (§7): **on Windows this stack is currently an unused
optional pywebview backend.** The desktop solver takes the WebView2 path by
default. Everything below is still factually verified against the installed
files, so it stands as a reference if anyone ever forces `gui='qt'`.

## 1. What each package ships (binaries vs bindings vs sip)

| Package | Version | Role | Key contents (per `*.dist-info/RECORD` + `METADATA`) |
|---|---|---|---|
| `pyqt6` | 6.11.0 | **Python bindings** (compiled SIP extensions + `.pyi` stubs). No Qt C++ code of its own. | `PyQt6/QtCore.pyd`, `QtGui.pyd`, `QtWidgets.pyd`, `QtNetwork.pyd`, … + matching `.pyi` stubs. `METADATA` Requires-Dist: `PyQt6-sip (>=13.8,<14)`, `PyQt6-Qt6 (>=6.11.0,<6.12.0)`; license GPL-3.0-only. |
| `pyqt6-qt6` | 6.11.2 | **The actual Qt6 C++ binaries** ("subset of a Qt installation … required by PyQt6", per its `METADATA` summary). License LGPL v3. | `PyQt6/Qt6/bin/Qt6Core.dll` (~10 MB), `Qt6Gui.dll`, `Qt6Widgets.dll`, `Qt6Network.dll`, QML/Quick, multimedia, positioning, etc. |
| `pyqt6-webengine` | 6.11.0 | **Python bindings for the Qt WebEngine framework** ("based on the Chrome browser", per its `METADATA`). Requires `PyQt6 (>=6.2.0)` + `PyQt6-sip` + `PyQt6-WebEngine-Qt6`. | `PyQt6/QtWebEngineCore.pyd` (~391 KB), `QtWebEngineWidgets.pyd`, `QtWebEngineQuick.pyd` + `.pyi` stubs + SIP sources under `PyQt6/bindings/QtWebEngineCore/` (`.toml`/`.sip`). |
| `pyqt6-webengine-qt6` | 6.11.2 | **The actual Chromium-embedded Qt binaries + runtime data.** 111 files in `RECORD`; this is the heavy one. | `PyQt6/Qt6/bin/Qt6WebEngineCore.dll` (**~203 MB**), `Qt6WebEngineWidgets.dll`, `Qt6WebEngineQuick.dll`, `QtWebEngineProcess.exe` (renderer subprocess launcher), `PyQt6/Qt6/resources/`: `icudtl.dat` (~10 MB), `qtwebengine_*.pak`, `v8_context_snapshot.bin`, plus `qtwebengine_devtools_resources.*` (~75 MB debug pak). License LGPL v3. |
| `pyqt6-sip` | 13.13.0 | **SIP runtime helper** for the bindings. Tiny. | Exactly one binary: `PyQt6/sip.cp313-win_amd64.pyd` (~111 KB) + `sip.pyi`. Import path is `from PyQt6 import sip` — verified: top-level `import sip` raises `ModuleNotFoundError` in this venv. |

Version-skew note: bindings are 6.11.0 while the Qt binary wheels are 6.11.2.
That is within the declared ranges (`>=6.11.0,<6.12.0`), so pip/uv accepts it.

Live version facts (introspected, `uv run python`):

- `PyQt6.QtCore.QT_VERSION_STR` = **6.11.0**, `PYQT_VERSION_STR` = **6.11.0**.
- `PyQt6.QtWebEngineCore.qWebEngineChromiumVersion()` = **140.0.7339.225**,
  `qWebEngineChromiumSecurityPatchVersion()` = **151.0.7922.71**.
  (Both functions are declared at the bottom of `PyQt6/QtWebEngineCore.pyi`,
  lines ~1301–1302.)

## 2. WebEngine view API surface reachable through PyQt6

All signatures below are quoted from the installed `.pyi` stubs
(`PyQt6/QtWebEngineCore.pyi`, `PyQt6/QtWebEngineWidgets.pyi`,
`PyQt6/QtNetwork.pyi`). The `.pyd` files are compiled, so stubs +
introspection are the source of truth at the Python level.

### 2.1 Rendering widget — `QWebEngineView` (`QtWebEngineWidgets.pyi:48`)

`class QWebEngineView(QtWidgets.QWidget)` — constructible from a page, a
profile, or bare. Navigation/content: `setUrl(QUrl)`, `setHtml(html, baseUrl)`,
`setContent(data, mimeType, baseUrl)`, `reload/back/forward/stop`,
`url()/title()/history()/icon()/iconUrl()`. Observability signals:
`loadStarted/loadProgress/loadFinished/urlChanged/titleChanged`,
`renderProcessTerminated`. Extras: `findText(subString, options, callback)`,
`printToPdf(...)` overloads incl. callback form, `triggerPageAction(...)`,
`createStandardContextMenu()`, `setZoomFactor()`.

### 2.2 Profile — `QWebEngineProfile` (`QtWebEngineCore.pyi:841`)

The per-identity container (cookies, cache, UA, storage). Relevant members:

- **User-Agent setter, per profile:** `setHttpUserAgent(str|None)` /
  `httpUserAgent() -> str` (stub lines ~910–911). There is also
  `setHttpAcceptLanguage()` and a `clientHints()` accessor
  (`QWebEngineClientHints`).
- **Off-the-record profiles:** `isOffTheRecord() -> bool`. Constructor
  overloads: `QWebEngineProfile(parent=None)` (anonymous → off-the-record)
  vs `QWebEngineProfile(name, parent=None)` (named → persistent). How pywebview
  uses this, see §3.
- **Storage/cache control:** `setPersistentStoragePath()/persistentStoragePath()`,
  `setCachePath()/cachePath()`, `setHttpCacheType(Memory/Disk/NoCache)`,
  `setPersistentCookiesPolicy(...)`, `clearHttpCache()`,
  `setDownloadPath()`, `setPersistentPermissionsPolicy(...)`.
- **Cookie store access:** `cookieStore() -> QWebEngineCookieStore|None`.
- **Request interception:** `setUrlRequestInterceptor(interceptor)`.
- **Script injection:** `scripts() -> QWebEngineScriptCollection` (persistent
  Greasemonkey-style injection point — pywebview does *not* use it; it injects
  per-load via `runJavaScript`, §3).
- `defaultProfile()` static; `downloadRequested`, `clearHttpCacheCompleted` signals.

### 2.3 Cookie store — `QWebEngineCookieStore` + `QNetworkCookie`

`QWebEngineCookieStore` (stub lines 178–198):

- Signals **`cookieAdded`** and **`cookieRemoved`** — fired for every cookie
  the network stack sets, **including HttpOnly ones**, because the payload is
  a `QNetworkCookie` object, not `document.cookie`.
- Methods: `loadAllCookies()`, `setCookie(cookie, origin=...)`,
  `deleteCookie(cookie, origin=...)`, `deleteAllCookies()`,
  `deleteSessionCookies()`, `setCookieFilter(callback)` (accept/reject filter
  receiving a `FilterRequest` with `firstPartyUrl/origin/thirdParty`).

`QNetworkCookie` (`QtNetwork.pyi`, class at ~line 1120):

- **`isHttpOnly() -> bool` / `setHttpOnly()`** — HttpOnly-ness is a visible
  attribute, not a hiding mechanism, at this layer.
- **`toRawForm(form=Full) -> QByteArray`** — full `Set-Cookie` bytes
  (name, value, domain, path, expiry, Secure/HttpOnly flags). This is exactly
  what pywebview's Qt backend consumes (§3).
- Also `name()/value()/domain()/path()/expirationDate()/isSecure()/
  isSessionCookie()/sameSitePolicy()`, `parseCookies()`, `setCookiesFromUrl()`
  on the jar.

Consequence for the solver question: a QtWebEngine-based solver **can see
`cf_clearance` (HttpOnly) via `cookieAdded` → `toRawForm()`** without any JS.
`document.cookie` blindness to HttpOnly does not apply at this layer.

### 2.4 JS evaluation with return values — `runJavaScript` overloads

On `QWebEnginePage` (stub lines ~706–710) and mirrored on `QWebEngineView`
(~line 366):

```python
def runJavaScript(self, scriptSource, worldId=..., resultCallback=...) -> None
def runJavaScript(self, scriptSource, resultCallback) -> None
```

Semantics: execution is **asynchronous**; the result (any JS value, mapped to
`QJsonValue`/Python) arrives via `resultCallback`. There is no synchronous
return. pywebview bridges this with a `Semaphore` per call (§3). `worldId`
selects the isolated-world id for the script.

## 3. How pywebview's Qt backend drives it (`webview/platforms/qt.py`, pywebview 6.2.1)

Import chain: `webview/platforms/qt.py` imports Qt **through qtpy**
(lines 14–39): `qtpy.QtCore/QtGui/QtWidgets`, plus
`qtpy.QtWebChannel.QWebChannel`, `qtpy.QtWebEngineCore.QWebEngineUrlRequestInterceptor`,
`qtpy.QtWebEngineWidgets.{QWebEnginePage,QWebEngineProfile,QWebEngineSettings,QWebEngineView}`.
If that import fails it falls back to `PyQt5.QtWebKitWidgets` (legacy
`qtwebkit` renderer). qtpy's own shim (`qtpy/QtWebEngineWidgets.py`) re-exports
`QWebEnginePage/Profile/Script/Settings` from `PyQt6.QtWebEngineCore` and
everything else from `PyQt6.QtWebEngineWidgets` on the PyQt6 path — verified.
qtpy resolves the binding via `QT_API` env / already-imported modules
(`qtpy/__init__.py` lines ~166–196; default literal is `"pyqt5"` but an
already-imported `PyQt6` module wins unless `FORCE_QT_API` is set).

Per-window wiring (`BrowserView.__init__`, lines ~394–453):

- View: custom `BrowserView.WebView(QWebView)` subclass (context-menu
  inspector hook, drag-drop, frameless-drag) with a `BrowserView.WebPage`
  page. `WebPage.userAgentForUrl()` (lines 310–315) returns
  `_state['user_agent']` when set, else the default — i.e. UA override applies
  **per navigation request**, on top of the profile-level setting below.
- Profile: `QWebEngineProfile()` (anonymous → off-the-record) when
  `private_mode` is on; else `QWebEngineProfile('pywebview')` +
  `setPersistentStoragePath(~/.pywebview or storage_path)` (lines 418–422).
  `profile.setHttpUserAgent(user_agent)` when a UA is configured (424–426).
  `profile.setUrlRequestInterceptor(RequestInterceptor)` (432) — fires
  `window.events.request_sent` and can rewrite headers via
  `info.setHttpHeader()`. Note the header-snapshot code at lines 244–248
  re-encodes keys as values (`k.data()…: k.data()…`), which looks like an
  upstream bug but is their code, not ours.
- Cookies: `cookie_store.cookieAdded → on_cookie_added` (lines 548–553):
  `raw = str(cookie.toRawForm(), 'utf-8')` → `create_cookie(raw)` (which for a
  `str` input is just `http.cookies.SimpleCookie(raw)`) → dict keyed by raw
  string. `get_cookies()` returns `list(self.cookies.values())`;
  `clear_cookies()` clears the dict + `cookieStore().deleteAllCookies()`.
  Nothing is ever read from `document.cookie`, so HttpOnly cookies are
  captured. Caveat: `cookieAdded` only fires for cookies set **after** the
  connection, so cookies already in a persistent profile from a prior run are
  missed unless `loadAllCookies()` is called — pywebview never calls it.
- JS: `evaluate_js(script, parse_json)` (838–853) emits to the GUI thread and
  blocks on a `Semaphore`; `on_evaluate_js` (699–728) calls
  `page().runJavaScript(script, 0, return_result)` on Qt6, converts
  `QJsonValue → str/None` via `_convert_string` (873–877), optionally
  `json.loads`. The js-bridge (`_set_js_api`, 855–870) injects
  `qwebchannel.js` + registers the `external` object over `QWebChannel`.
- Chromium flags appended at runtime: `--use-fake-ui-for-media-stream`,
  `--enable-features=AutoplayIgnoreWebAudio` (397–401); `--no-sandbox` (twice)
  on arch/manjaro/nixos/rhel/pop (53–62); `--ignore-certificate-errors` when
  `IGNORE_SSL_ERRORS`; `--remote-debugging-port=` when `REMOTE_DEBUGGING_PORT`;
  `QTWEBENGINE_REMOTE_DEBUGGING=<port>` (from 8228 up) when debug mode.
- Window lifetime (`create_window`, 921–970): `window.hidden=True` → the
  `browser.show()` call is skipped entirely (lines 940–943, only
  `events.shown.set()` fires). The `QWebEngineView`/`QWebEnginePage` objects
  are still fully constructed and `setUrl`/`setHtml` still runs — i.e. **page
  loads proceed in a never-shown window**. Whether in-page JS keeps executing
  normally there is **Unverified** (see §8) — nothing in `qt.py` gates
  `runJavaScript` on visibility, but Chromium throttles hidden renderers.

## 4. Hidden/offscreen windows and JS execution — what the installed code says

- Supported: creating a never-shown window (`hidden=True` path, `qt.py`
  940–943), `hide()/show()` toggling at runtime (650–654), `WA_ShowWithoutActivating`
  + `WindowDoesNotAcceptFocus` when `focus=False` (377–380).
- The JS path (`on_evaluate_js` → `page().runJavaScript`) has no visibility
  check in the installed source. But "no gate in the wrapper" ≠ "Chromium
  executes normally": background-page timer throttling, `requestAnimationFrame`
  suspension, and Cloudflare's own visibility/focus heuristics all live below
  this layer. No headless/offscreen-render flag (`QTWEBENGINE_CHROMIUM_FLAGS`
  has no `--headless`/`--disable-gpu` handling in `qt.py`) is wired up.
- Our solver does not rely on hidden mode today: `desktop_cf_solver.py`
  creates a visible 800×600 window (§6). Any move to hidden solving needs an
  on-device run — listed under Unverified (§8).

## 5. User-agent control

Two layers, both verified in `qt.py`: profile-level
`QWebEngineProfile.setHttpUserAgent()` (applied when pywebview is started with
`user_agent=...`) and per-request `WebPage.userAgentForUrl()` override. Our
solver passes **no** `user_agent` to `webview.start`, so the Qt backend would
send Chromium 140's default UA; the solver instead captures the real
`navigator.userAgent` via JS after load (`on_loaded`, `desktop_cf_solver.py`
lines 9–16) and again at completion. That read-back design is backend-agnostic
and works on either backend.

## 6. What our app actually uses today

- `src/services/desktop_cf_solver.py` (the whole solver): `webview.create_window(
  "Cloudflare Turnstile Solver", url, width=800, height=600)` then
  `webview.start(check_cookies, window)` — **no `gui=` argument** (lines 106–110).
- Backend selection is then up to `webview/guilib.py:initialize()`. On
  **Windows** the order is `[import_winforms]` unless `gui='qt'` was forced or
  `PYWEBVIEW_GUI=qt` is set (guilib.py, Windows branch: `guis =
  [import_winforms]` by default, `[import_qt, import_winforms]` only when
  forced). `import_winforms` = **pythonnet + system Edge WebView2**
  (`webview/platforms/winforms.py` drives `Microsoft.Web.WebView2`), and
  **pythonnet 3.2.1 + clr_loader are installed** in this venv — so the import
  succeeds and Qt is never touched on this machine's default path.
- `pythonnet` is a *runtime* dependency of pywebview on win32
  (`pywebview-6.2.1.dist-info/METADATA`: `pythonnet; sys_platform == "win32"`),
  whereas `PyQt6`/`PyQt6-WebEngine`/`QtPy` are only `extra == "qt"/"qt6"` and
  in our project only in `[dependency-groups] dev` (`pyproject.toml`) —
  required for the desktop-dev solver subprocess, but the Qt half of that dev
  group is dormant on Windows.
- The solver loop itself (poll `window.get_cookies()` 1×/s for ≤120 s, require
  `cf_clearance` + a target-site marker cookie, confirm via `document.title`
  and `__cf_chl` URL check, return `cookies` header + UA as JSON on stdout) is
  backend-agnostic pywebview API and works identically on winforms/WebView2.
  `WebViewSolver._solve_desktop` (`src/services/webview_solver.py:41–118`)
  spawns `.venv/Scripts/python.exe desktop_cf_solver.py <url>` and parses the
  JSON line. Mobile uses `flet_webview` + pyjnius `CookieManager` (native,
  HttpOnly-visible) — unrelated to Qt.

## 7. Verdict: is the PyQt6 stack relevant to us?

**Beyond being an installed-but-unused pywebview backend on Windows, no —
with evidence:**

1. Default backend on Windows is WebView2/winforms, not Qt (`guilib.py`
   Windows branch; pythonnet present so `import_winforms` succeeds).
2. Our solver never requests `gui='qt'` (`desktop_cf_solver.py:106–110`).
3. Qt packages are dev-group-only in `pyproject.toml`; a packaged/production
   install would not even contain them.
4. The one platform where Qt *could* become the backend by default is Linux
   (fallback `[import_gtk, import_qt]`), which is not our desktop-solver target
   today.

It is **not** a better backend for Cloudflare solving on desktop given our
setup: WebView2 uses the system's evergreen Edge Chromium (mainstream
fingerprint, no extra payload), while the Qt path would pin Chromium 140,
require shipping `Qt6WebEngineCore.dll` (~203 MB) + ICU/pak resources, and
send a QtWebEngine UA unless overridden. Qt's advantages (per-profile UA,
off-the-record profiles, `cookieAdded`-level HttpOnly capture,
`QWebEngineUrlRequestInterceptor`, remote-debugging port) are real but all
either already available on the WebView2 path (`CookieManager.GetCookiesAsync`
in `edgechromium.py:201–202` sees HttpOnly cookies too; UA via
`settings.UserAgent`, `edgechromium.py:298–299`) or unneeded by our solver's
read-back design.

## 8. App improvement opportunities (ranked, evidence-backed)

1. **Log which backend actually solves.** `webview.start` leaves the chosen
   module in `webview.guilib` / `window.gui.renderer` (`'qtwebengine'` vs
   WebView2). One debug log line in `desktop_cf_solver.py` after start (or in
   `WebViewSolver._solve_desktop` from subprocess stderr) removes all guesswork
   about Qt-vs-WebView2 on any machine. Evidence: `qt.py:41`
   (`renderer = 'qtwebengine'`), `window.py:212`
   (`events.initialized.set(gui.renderer)`).
2. **Keep the solver window visible; do not "optimize" to `hidden=True`.**
   The solver's visible 800×600 window is load-bearing for Turnstile
   interaction/visibility heuristics. `qt.py:940–943` proves hidden windows
   load pages, but nothing proves CF passes in them. Status quo is correct.
3. **Deliberately decide `gui=` instead of inheriting the default.**
   Passing `gui='edgechromium'`/default on Windows pins the evergreen,
   mainstream-fingerprint path; passing `gui='qt'` would pin Chromium 140 +
   ~250 MB of Qt binaries for no solver-visible gain today. Evidence: §1 size
   table, §2 Chromium version, `guilib.py` fallback order.
4. **Remember `private_mode` defaults to `True`** (`webview/__init__.py`
   `start()` docstring) and the solver relies on it implicitly (fresh cookie
   jar per run; on the Qt path that means an off-the-record profile, `qt.py`
   418–422). If anyone ever sets `private_mode=False` + `storage_path` for
   "remember me" behavior, note pywebview never calls `loadAllCookies()`, so
   pre-existing persistent cookies would be invisible to `get_cookies()` on
   the Qt path until a new cookie arrives.
5. **Do not add `document.cookie`-based capture on desktop.** Both desktop
   backends expose HttpOnly cookies natively (Qt: §2.3; WebView2:
   `CoreWebView2Cookie` via `CookieManager.GetCookiesAsync`,
   `edgechromium.py:170–202`). The mobile fallback's `document.cookie`
   limitation (noted in `webview_solver.py:281–284`) does not apply here.

### Unverified (need an on-device run)

- U1. Whether a never-shown (`hidden=True`) Qt window still executes
  Turnstile JS well enough to pass (timer/rAF throttling, CF visibility
  checks). Code shows no wrapper-level gate (§4); behavior needs a live run
  with `PYWEBVIEW_GUI=qt`.
- U2. QtWebEngine-vs-WebView2 Cloudflare pass rate / fingerprint difference
  (default QtWebEngine UA string, `navigator.webdriver`, plugin/mime
  surface) on the real challenge pages.
- U3. Exact `cf_clearance` capture latency via `cookieAdded` under `gui='qt'`
  vs the current 1 s poll loop — expected to be equivalent-or-faster, but
  unmeasured.
- U4. Whether `private_mode=True` (off-the-record profile) itself affects
  Cloudflare risk scoring vs a persistent profile. Unknown; current behavior
  works, so no change proposed.
