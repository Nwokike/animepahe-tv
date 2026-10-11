# pywebview 6.2.1 — complete API reference (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/webview/`, version `6.2.1` per `_version.py`:
> `__version__ = version = '6.2.1'`) — every signature verified live against the
> loaded module via `uv run python` from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.
> Dev dependency per `pyproject.toml`: `"pywebview>=6.2.1"`.
> Our app's consumer: `src/services/desktop_cf_solver.py` (desktop Cloudflare
> solver, spawned as a subprocess by `src/services/webview_solver.py::_solve_desktop`).

## Module surface (`webview/__init__.py`)

```python
__all__ = ('active_window', 'start', 'create_window', 'token', 'renderer',
           'screens', 'settings', 'Event', 'JavascriptException',
           'WebViewException', 'Screen', 'Window')
```

- `windows: list[Window]` — every created window, in creation order.
  First window gets `uid='master'`, later ones `'child_<8hex>'` (`__init__.py:377`).
- `renderer: str | None` — set by `start()` to `guilib.renderer`
  (on Windows: `'edgechromium'`, `'cef'`, or `'mshtml'`).
- `token` — CSRF token for the built-in HTTP server (`webview.util._TOKEN`).
- `active_window() -> Window | None` — delegates to `guilib.get_active_window()`;
  on WinForms, matches `WinForms.Form.ActiveForm` handle against
  `BrowserView.instances` (`platforms/winforms.py:970`).
- `screens` (module property) — lazily initializes GUI and returns
  `guilib.get_screens()`.

Global knobs:

```python
settings = ImmutableDict({
    'ALLOW_DOWNLOADS': False,
    'ALLOW_FILE_URLS': True,
    'DRAG_REGION_SELECTOR': '.pywebview-drag-region',
    'DRAG_REGION_DIRECT_TARGET_ONLY': False,
    'DEFAULT_HTTP_PORT': 42001,
    'OPEN_EXTERNAL_LINKS_IN_BROWSER': True,
    'OPEN_DEVTOOLS_IN_DEBUG': True,
    'REMOTE_DEBUGGING_PORT': None,   # EdgeChromium appends --remote-debugging-port=<n>
    'IGNORE_SSL_ERRORS': False,      # EdgeChromium attaches AlwaysAllow cert-error handler
    'SHOW_DEFAULT_MENUS': True,
    'WEBVIEW2_RUNTIME_PATH': None,   # custom WebView2 runtime folder (relative ok)
})
_state = ImmutableDict({             # set via webview.start(...) kwargs
    'debug': False, 'storage_path': None, 'private_mode': True,
    'user_agent': None, 'http_server': False, 'ssl': False,
    'icon': None, 'menu': None,
})
```

Log level via `PYWEBVIEW_LOG` env var (default `INFO`); `debug=True` forces `DEBUG`.

## 1. `create_window` — every parameter

Verified live signature (`uv run python`, `inspect.signature`):

```python
create_window(
    title: str,
    url: str | callable | None = None,   # URL string OR WSGI/ASGI callable
    html: str | None = None,             # inline HTML (mutually exclusive-ish with url)
    js_api: Any = None,                  # object whose public methods become window.pywebview.api.*
    width: int = 800,
    height: int = 600,
    x: int | None = None,                # None => CenterScreen (WinForms)
    y: int | None = None,
    screen: Screen | None = None,        # center on this screen when x/y unset
    resizable: bool = True,              # False => FixedSingle border, no maximize box
    fullscreen: bool = False,
    min_size: tuple[int, int] = (200, 100),
    hidden: bool = False,                # created via Show()+Hide() opacity trick (see §7)
    frameless: bool = False,             # FormBorderStyle.None
    easy_drag: bool = True,              # drag-region selector handling
    shadow: bool = True,                 # DWM frame extension (skipped when transparent)
    focus: bool = True,                  # False => WS_EX_NOACTIVATE so kb focus stays elsewhere
    minimized: bool = False,             # WindowState.Minimized at creation
    maximized: bool = False,             # WindowState.Maximized at creation
    on_top: bool = False,                # Form.TopMost
    confirm_close: bool = False,         # OK/Cancel quit-confirmation dialog on close
    background_color: str = '#FFFFFF',   # validated ^#(?:[0-9a-fA-F]{3}){1,2}$; WebView2 DefaultBackgroundColor
    transparent: bool = False,           # transparent WebView2 bg (EdgeChromium only); Show/Hide hack
    text_select: bool = False,           # platform text-selection policy
    zoomable: bool = False,              # (macOS trackpad zoom; inert on Windows)
    draggable: bool = False,             # (macOS window drag; inert on Windows)
    vibrancy: bool = False,              # (macOS only; inert on Windows)
    menu: list[Menu] = [],               # window-level MenuStrip
    localization: Mapping[str, str] | None = None,  # per-window string overrides
    server: type[http.ServerType] = http.BottleServer,
    http_port: int | None = None,
    server_args: http.ServerArgs = {},
) -> Window | None
```

Notes (source evidence):

- `Window.__init__` stores the same list positionally (`__init__.py:379-413`
  passes all 30 args through). `Window.original_url = None if html else url`;
  `real_url` is resolved later in `Window._initialize` (local file/WSGI URLs are
  rewritten to the built-in HTTP server address).
- `background_color` is validated up front — non-hex-triplet raises `ValueError`
  (`__init__.py:373-375`). On EdgeChromium it becomes
  `WebView2.DefaultBackgroundColor` (`edgechromium.py:106-111`); WinForms form
  `BackColor = ColorTranslator.FromHtml(...)` unless `transparent`
  (`winforms.py:286-292`).
- No `user_agent` / `on_loaded` / `http_server` params on `create_window` —
  those live on `webview.start()` (`user_agent`, `http_server`, `private_mode`,
  `storage_path`) and on `window.events` (`window.events.loaded += handler`).
  There is **no** `on_loaded` keyword; the solver wires
  `window.events.loaded += on_loaded` (`desktop_cf_solver.py:109`).
  There is **no** per-window `user_agent` either — only the global
  `webview.start(user_agent=...)`, applied to WebView2 via
  `CoreWebView2.Settings.UserAgent` (`edgechromium.py:298-299`).
- Late creation: if `start()` already runs and the caller is off the main
  thread, `create_window` immediately initializes and shows the window
  (`__init__.py:417-428`). Returns `None` only if the
  `window.events.initialized` handler vetoes creation.
- `title` has a live property + `set_title()`; `width/height/x/y` are live
  properties reading the native form (converted logical px, see §8).

## 2. `webview.start()` mechanics

Verified live signature:

```python
start(
    func: Callable[..., None] | None = None,   # invoked in a NEW thread after GUI boot
    args: Iterable[Any] | None = None,         # single value auto-wrapped to tuple
    localization: dict[str, str] = {},
    gui: GUIType | None = None,                # 'qt'|'gtk'|'cef'|'mshtml'|'edgechromium'|'android'|'cocoa'
    debug: bool = False,                       # DevTools, context menus, DEBUG logging
    http_server: bool = False,                 # serve local files over HTTP (per-window server)
    http_port: int | None = None,
    user_agent: str | None = None,             # global UA override (all windows)
    private_mode: bool = True,                 # default True: ephemeral profile, cookies wiped
    storage_path: str | None = None,           # persistent profile dir (implies cache_dir)
    menu: list[Menu] = [],                     # app-level menu
    server: type[http.ServerType] = http.BottleServer,
    server_args: dict[Any, Any] = {},
    ssl: bool = False,                         # self-signed cert for local server (needs cryptography)
    icon: str | None = None,                   # GTK/QT only (Windows uses exe icon)
)
```

Behavior (`__init__.py:164-306`):

- **Must run on `MainThread`** with at least one window, else `WebViewException`.
- **Blocks**: on Windows the master path spins the WinForms STA thread, then
  `thread.Join(500)` in a loop so Ctrl+C is still processed; `app.Run()` pumps
  until the last window closes (`winforms.py:771-834`). Nothing after
  `webview.start(...)` executes until shutdown.
- `func` runs on a **background thread**, not the GUI thread. Our solver passes
  `check_cookies` as `func` and the target `window` as `args`
  (`desktop_cf_solver.py:110`: `webview.start(check_cookies, window)` — a bare
  `Window` is not iterable, so `start` wraps it to `(window,)`; `check_cookies(window)`
  then polls once per second).
- Multi-window: `guilib.create_window(windows[0])` runs the master on the GUI
  loop; windows[1:] are created from `_create_children`, which waits up to 10 s
  for `windows[0].events.shown` then creates the rest on a helper thread
  (`__init__.py:209-214, 290-303`). Child windows marshal via
  `_main_window_created.wait()` + `Invoke` (`winforms.py:836-839`).
- Event flow per navigation (`util.inject_pywebview`, `util.py:168-244`):
  `before_load` fires → `window.pywebview` JS object + bridge injected →
  worker thread runs `finish.js` (`_createApi(...)`, dispatches
  `pywebviewready`) → `_pywebviewready` set → **`loaded` set**.
  `load_url`/`load_html` clear `loaded`, `before_load`, `_pywebviewready` before
  navigating (`window.py:283-285, 298-300`).
- Local-file/WSGI URLs start the built-in HTTP server (`BottleServer` default);
  with `private_mode=True` the port is random, otherwise `DEFAULT_HTTP_PORT`
  (42001). Remote `http(s)` URLs bypass it.
- `gui=` or `PYWEBVIEW_GUI` env forces a backend; on Windows the only legal
  values that reach `guilib.initialize` are `qt` (→ Qt, else WinForms) or
  default (WinForms: CEF → EdgeChromium → MSHTML, see §5).

## 3. Window API (verified live via `inspect.signature(Window.*)`)

All calls marshal to the GUI thread and most gate on an event
(`window.py:32-69` — `_api_call` waits up to **20 s** for the gating event,
else `WebViewException('Main window failed to start')`):

| Method (live signature) | Gate | Backend path (WinForms) |
|---|---|---|
| `load_url(url: str) -> None` | `shown` | `EdgeChrome.load_url` → `WebView2.Source = Uri(url)`; clears loaded/before_load/_pywebviewready first |
| `load_html(html, base_uri=<appdir>) -> None` | `shown` | `CoreWebView2.NavigateToString(html)` |
| `load_css(stylesheet: str) -> None` | `loaded` | `run_js('pywebview._loadCss(...)')` |
| `evaluate_js(script, callback=None) -> Any` | `_pywebviewready` | `ExecuteScriptAsync` + JSON round-trip; sync return; promise→`callback`; JS throw→`JavascriptException` |
| `run_js(script) -> Any` | `before_load` | fire-and-forget `evaluate_js(..., False)`; result not guaranteed |
| `get_cookies()` | `loaded` | WinForms `get_cookies(uid)` → list of `SimpleCookie` (§6) |
| `clear_cookies()` | `loaded` | `CookieManager.DeleteAllCookies()` (EdgeChromium/CEF only; logs error otherwise) |
| `get_current_url() -> str \| None` | `loaded` | cached `browser.url` (updated on `SourceChanged`/`NavigationCompleted`) |
| `destroy() -> None` | `shown` | `Form.Close()`; releases pending JS semaphore; `Application.Exit()` when last window closes |
| `show() / hide()` | `shown` | `Form.Show()+Activate()` / `Form.Hide()` |
| `resize(w, h, fix_point=NORTH\|WEST)` | `shown` | `SetWindowPos`, logical→physical px |
| `move(x, y)` | `shown` | `SetWindowPos` NOSIZE\|NOZORDER\|SHOWWINDOW |
| `maximize / minimize / restore / toggle_fullscreen` | `shown` | `WindowState` / borderless `Bounds` swap |
| `set_title(title)` + `title` property (setter gates `loaded`) | `shown` | `Form.Text` |
| `width/height/x/y` properties | `shown` (15 s wait) | `get_size`/`get_position`, physical→logical px |
| `create_confirmation_dialog(title, message) -> bool` | `shown` | `MessageBox OKCancel`; True on OK |
| `create_file_dialog(type=10, directory='', allow_multiple=False, save_filename='', file_types=())` | `shown` | Open/Save/Folder dialogs; `file_types` entries `'Desc (*.ext[;*.ext])'` validated by `parse_file_type` |
| `expose(*functions)` | — | registers extra callables alongside `js_api`; if `loaded` already set, re-runs `_createApi` live |

Gating gotcha for the solver: `evaluate_js` waits on `_pywebviewready`, which
is set only after the bridge injection finishes. Calling it from a `loaded`
handler is safe (loaded fires after); calling it before any navigation
completes raises after 20 s.

### `evaluate_js` details (`window.py:436-505`)

- Wraps user code in `eval(...)`, serializes via `pywebview.stringify`, returns
  the last value. Sync path returns the value directly; with `callback=fn`,
  promises resolve into `fn(value)` via the `pywebviewAsyncCallback` bridge and
  the call returns `"true"`.
- JS exceptions come back as `{'pywebviewJavascriptError420': True, ...}` and
  are re-raised as `JavascriptException(result)` (a dict subclass —
  `webview.errors`).
- `run_js` skips all of that (raw `ExecuteScriptAsync`, no return).
- EdgeChromium path: `ExecuteScriptAsync(script).ContinueWith(...)` on the sync
  context, result parsed with `json.loads(task.Result)`; a `Semaphore` blocks
  the calling (background) thread until the GUI thread answers
  (`edgechromium.py:136-165`). Never call it from the GUI thread itself.

### Events (`window.events`, `event.py`)

```python
closed, closing(+veto), loaded, before_load(+veto), before_show(+veto),
initialized(+veto), shown, minimized, maximized, restored, resized,
moved, request_sent, response_received, _pywebviewready(internal)
```

- `Event` = `threading.Event` + handler list. `+= fn` / `-= fn` subscribe;
  `fn()` (0 args), `fn(window, *args)` (`window` param), or `fn(*args)` are all
  accepted. Non-locking events dispatch handlers on a new thread; `*_lock`
  events (`closing`, `before_load`, `before_show`, `initialized`) run inline and
  returning `False` from any handler **vetoes** the transition (`set()` returns
  True → cancel/ Veabort).
- Solver-relevant: `loaded` fires after every completed navigation (bridge
  ready); `shown` fires once from `Form.Shown` (`winforms.py:367-370`);
  `closed` fires in `on_close` after removing the instance; `closing` can cancel
  via `args.Cancel`. `request_sent`/`response_received` fire per WebView2
  resource (EdgeChromium `WebResourceRequested/ResponseReceived` handlers) with
  `webview.models.Request/Response` payloads.
- `events.loaded += on_loaded` in `desktop_cf_solver.py:109` matches the
  intended pattern: handler takes 0 args (`def on_loaded():`), so it is called
  with no arguments.

### DOM manipulation (`window.dom`, `webview/dom/`)

`window.dom` (`DOM` object) offers `get_element(s)`, `create_element`,
query helpers and `EventHandler` wiring; elements serialize over
`evaluate_js` with `data-pywebview-id` tracking (`js/api.js: _getNodeId`,
`_processElements`). Not used by the solver.

## 4. `js_api` bridge — how Python receives JS calls

1. Python side: pass any object as `js_api=` to `create_window`. Every public
   method (recursively into nested objects/classes, `_`-prefixed skipped,
   `_serializable=False` skipped) becomes `window.pywebview.api.<path>`
   (`util.get_functions`, `util.py:180-211`). Extra free functions can be added
   with `window.expose(fn)`.
2. On each navigation, `inject_pywebview` builds
   `[{'func': name, 'params': [...]}]` and runs
   `window.pywebview._createApi(funcList)` (`finish.js:1`), which manufactures
   **async** JS functions: each call posts
   `[funcName, stringify(params), id]` via `chrome.webview.postMessage` on
   EdgeChromium (`api.js:83-133`) and returns a `Promise` parked in
   `_returnValuesCallbacks[funcName][id]` (`_checkValue`).
3. .NET side: `EdgeChrome.on_script_notify` (`edgechromium.py:225-253`)
   parses `[func_name, func_param, value_id]` and calls
   `util.js_bridge_call`, which runs the Python function **on a new thread**
   and resolves the JS promise with `{value: '<json>'}` or
   `{isError: true, value: '<json>'}`.
4. Special-cased inbound names (never reach user code): `pywebviewMoveWindow`,
   `pywebviewEventHandler` (DOM events), `pywebviewAsyncCallback` (promise
   results for `evaluate_js(..., callback)`), `pywebviewStateUpdate/Delete`
   (`util.py:276-340`).
5. Direction is symmetric: `evaluate_js('window.pywebview.api.foo(...)')` from
   Python invokes the same path and awaits the promise only if a `callback` is
   given.

The solver does **not** use `js_api` — it only calls
`window.evaluate_js("navigator.userAgent" | "document.title")` (sync reads)
and `window.get_cookies()` / `get_current_url()`.

## 5. Backends on Windows — which one runs, cookie capture per backend

### Backend selection (`guilib.initialize` + `platforms/winforms.py:130-155`)

On `platform.system() == 'Windows'` (unless `gui='qt'` forces Qt):

1. `forced_gui == 'cef'` → **CEF** (`renderer='cef'`). Requires the
   `pywebview[cef]` extra + CEF binaries; `WebBrowserInterop` native DLLs ship
   under `webview/lib/`.
2. Else if WebView2 usable → **EdgeChromium** (`renderer='edgechromium'`).
   `_is_chromium()` returns True when `WEBVIEW2_RUNTIME_PATH` is set, or when
   .NET ≥ 4.6.2 **and** a WebView2 Runtime/Edge build ≥ `86.0.622.0` is
   registered in `HKCU/HKLM ...\EdgeUpdate\Clients\{...}` (Runtime, Beta, Dev,
   Canary GUIDs checked). This is the **default on any current Windows 10/11
   box** — WebView2 ships with Edge/Office/Windows itself.
3. Else → **MSHTML** (legacy IE11 Trident, deprecated warning; needs
   `IE._set_ie_mode()` registry emulation). No `get_cookies`/`clear_cookies`
   (logs `not implemented`), no modern JS (Cloudflare Turnstile will not solve).

Force/override: `webview.start(gui='mshtml'|'cef'|'edgechromium'|'qt')` or
`PYWEBVIEW_GUI` env (same values). There is no separate `gui` that selects
"Chrome" — EdgeChromium *is* the Chromium backend.

### Cookie capture

- **EdgeChromium (default)**: `get_cookies()` → `CookieManager.GetCookiesAsync(url)`
  → per-cookie `create_cookie({'name','value','path','domain','expires','secure',
  'httponly','samesite'})` → **`http.cookies.SimpleCookie` objects**
  (`edgechromium.py:170-204`, `util.create_cookie`). The list covers **all**
  cookies for the current URL **including HttpOnly** — they come from the native
  `CoreWebView2CookieManager`, not `document.cookie`. `IsHttpOnly` is preserved
  in the morsel (`cookie[name]['httponly']`), as are `secure`/`samesite`. The
  solver iterates `for key, morsel in c.items()` and joins `key=morsel.value`
  (`desktop_cf_solver.py:68-76`) — correct for this shape.
  `expires` is RFC-1123 (`ToString('r', en-US)`).
- **CEF**: `VisitUrlCookies(url, includeHttpOnly=True, visitor)` → same
  `SimpleCookie` list (`cef.py:170-176`). Note the explicit `True` — HttpOnly
  included by design.
- **MSHTML**: not implemented — returns `[]` with an error log
  (`winforms.py:463-477`).
- `clear_cookies()` → `DeleteAllCookies()` (EdgeChromium/CEF only). In
  `private_mode` WebView2 cookies from a previous run are additionally deleted
  at init (`edgechromium.py:301-303`), and `on_close` wipes the user-data
  folder when `private_mode` is on (`winforms.py:372-380`).

### Storage / persistence

- `private_mode=True` (default) + no `storage_path` → `cache_dir` is a fresh
  `tempfile.TemporaryDirectory().name` per run (`winforms.py:740-758`) → solver
  starts with a clean jar every launch; nothing persists.
- `private_mode=False` or `storage_path=<dir>` → profile under
  `%APPDATA%\pywebview` (or the given path), passed as WebView2
  `UserDataFolder` (`edgechromium.py:79`). Cookies then persist across runs.
- The solver uses all defaults → **ephemeral profile**: each invocation must
  re-solve the challenge; `cf_clearance` is captured in-memory and printed as
  `{"cookies": "<k=v; ...>", "user_agent": "<ua>"}` on stdout for the parent to
  persist (`webview_solver.py:94-111` parses the `{...}` line).

## 6. Our usage (`src/services/desktop_cf_solver.py`, 111 lines)

```
__main__: url = sys.argv[1]
window = webview.create_window("Cloudflare Turnstile Solver", url, width=800, height=600)
window.events.loaded += on_loaded          # refresh captured_ua via evaluate_js("navigator.userAgent")
webview.start(check_cookies, window)       # blocks; check_cookies runs on bg thread
  check_cookies: 120 × (sleep 1s → window.get_cookies() → join k=v pairs)
    complete ⇔ "cf_clearance" ∈ keys AND (any of {animepahe_session, serverid,
               xsrf-token, latest} ∈ keys  — note: keys are case-sensitive,
               so "XSRF-TOKEN" from a real Set-Cookie will NOT match "xsrf-token"
               — OR title ∉ challenge markers and contains "animepahe"/"anime")
    also bails (returns False) while "__cf_chl" ∈ current URL
    on success: re-read UA, print JSON to stdout, window.destroy()
    on 120 s timeout: window.destroy() with no stdout JSON
```

- Called from `webview_solver._solve_desktop` via
  `asyncio.create_subprocess_exec(python, desktop_cf_solver.py, url)`; stdout
  JSON → `(cookies, ua)`; stderr `[DEBUG]` lines are logs only.
- Default UA fallback if JS read fails: hardcoded `Edg/149.0.0.0` string at
  module top; `webview_solver` falls back to a `Chrome/120` UA string.
- `webview.start` is **not** passed `gui/debug/user_agent/private_mode`, so all
  defaults apply: EdgeChromium, `private_mode=True` (clean jar), system UA.
  To pin the UA at the browser level, pass
  `webview.start(..., user_agent="...")` instead of only reading it back.
- Polling `get_cookies()` + `evaluate_js` from the `func` thread is the
  documented pattern (both marshal to the GUI thread internally). `loaded`
  fires per navigation, so `on_loaded` refreshes the UA as the challenge
  redirects.

## 7. Hidden / minimized operation limits

- `hidden=True` does **not** skip rendering. WinForms `create_window`
  (`winforms.py:771-790`) still constructs the form and WebView2 control, then
  does `Opacity=0; Show(); Hide(); Opacity=1` — i.e. the page **loads and runs
  JS normally**, it is just never painted. `on_navigation_completed` still
  fires, `inject_pywebview` still runs, `loaded` still fires, and
  `evaluate_js`/`get_cookies` work unchanged.
- Practical limits for a hidden solver window:
  - Cloudflare **non-interactive** challenges generally complete hidden (JS,
    cookies, redirects all function).
  - **Interactive Turnstile** (checkbox / "verify you are human") cannot be
    clicked while hidden — the user must `window.show()` it. Our solver keeps
    the window visible for exactly this reason.
  - `minimized=True` keeps the window in the taskbar; rendering/JS continue,
    same as hidden, but the user can restore it. Some GPU-throttled timers may
    run slower when occluded — negligible for a ≤120 s poll loop.
  - `focus=False` sets `WS_EX_NOACTIVATE` so the solver window never steals
    keyboard focus — useful combined with a visible window.
  - Headless (no logged-in session / no display server, e.g. Windows service
    or SSH without desktop) is **unsupported**: WebView2/WinForms needs an
    interactive desktop. There is no `--headless` flag; `hidden=True` still
    needs a window station.
- Showing later: `window.show()` / `window.hide()` are callable any time after
  `shown` (both gate on `shown`).

## 8. Windows platform quirks

- **Threading**: WinForms + WebView2 run STA. `webview.start` must be called on
  `MainThread`; the master window is created on a dedicated STA thread while
  the main thread pumps `Join(500)` so signals work. All `Window.*` methods
  `Invoke` onto the GUI thread — never block it yourself (no `time.sleep` on
  a `loaded` handler; the solver correctly sleeps on the `func` thread).
- **DPI**: process is set DPI-aware (`SetProcessDPIAware`); all geometry
  (`width/height/x/y/resize/move/get_size/get_position`) is exposed in
  **logical px** and converted via `GetDpiForWindow/96` (EdgeChromium path).
- **New windows / popups**: `NewWindowRequested` is always `Handled=True` —
  target=_blank links open in the **system browser** by default
  (`OPEN_EXTERNAL_LINKS_IN_BROWSER=True`); set False to load in-place. The
  challenge flow rarely needs this, but OAuth-style redirects would leave the
  solver window.
- **Downloads**: `ALLOW_DOWNLOADS=False` default → `DownloadStarting` is
  cancelled. Irrelevant to cookie capture.
- **DevTools**: enabled only with `debug=True` (`AreDevToolsEnabled`,
  accelerator keys, context menus all follow `_state['debug']`;
  `OPEN_DEVTOOLS_IN_DEBUG` auto-opens the window). For debugging the solver
  locally: `webview.start(..., debug=True)` + `REMOTE_DEBUGGING_PORT`.
- **TLS**: self-signed/local HTTPS interception needs `ssl=True` (generates a
  throwaway cert via `cryptography`) or `IGNORE_SSL_ERRORS=True`
  (AlwaysAllow). Plain `https://animepahe…` needs neither.
- **File URLs**: `ALLOW_FILE_URLS=True` appends
  `--allow-file-access-from-files` to WebView2 args.
- **Shutdown**: closing the last window calls `Application.Exit()`, which
  unblocks `webview.start`. `window.destroy()` from the poll thread (as the
  solver does) is the clean exit; the 120 s timeout path also destroys, so the
  parent never hangs — but prints no JSON, which the parent reports as
  `"Verification was closed or failed."`.
- **Anti-bot note**: WebView2 presents a genuine Edge UA and full JS engine,
  so `cf_clearance` issuance works, but the `navigator.webdriver`-style
  automation flags are *absent* (real embedded browser, not Selenium) — while
  window-size/DPI fingerprints reflect the 800×600 solver window. The solver
  mitigates UA drift by capturing `navigator.userAgent` live and returning it
  alongside the cookies so subsequent API calls reuse the exact string.

## 9. Facts vs. gaps (things NOT in this package)

- No `on_loaded`/`user_agent`/`http_server` kwargs on `create_window` (they are
  `start()`-level or event-level — see §1).
- No `get_cookies_dict`, `save_cookies`, async API, proxy arg, or per-request
  header hooks. Header observation only via `request_sent`/`response_received`
  events (read + mutate, EdgeChromium only).
- No headless mode, no screenshot API on WinForms, no built-in adblock.
- `get_cookies()` returns `list[SimpleCookie]`, **not** a dict — iterate
  `.items()` per cookie as the solver does.
- CEF backend exists (`platforms/cef.py`, 401 lines) but needs the optional CEF
  extra; MSHTML (`platforms/mshtml.py`) is a dead end for Cloudflare.

## 10. App improvement opportunities (evidence-backed)

Verified against the installed sources above; each item cites the file +
signature it depends on. Items I could not verify from source are listed
separately at the end — no speculation presented as fact.

### A. Pin the browser UA via `webview.start(user_agent=...)` (recommended)

Today the solver only *reads back* `navigator.userAgent` and hopes the
subsequent API calls reuse a matching string. `webview.start()` accepts
`user_agent: str | None = None` (`__init__.py:164-180`), stored to
`_state['user_agent']` and applied natively in
`EdgeChrome.on_webview_ready` as `settings.UserAgent = _state['user_agent']`
(`platforms/edgechromium.py:298-299`). Passing the *stored* UA from the
previous successful solve (the one `store.save_clearance` persisted) makes
the challenge solve and the later `primp` requests present the identical UA,
which is exactly what `cf_clearance` is bound to. Cost: one kwarg. Evidence
of the read-back path it replaces: `evaluate_js("navigator.userAgent")`
in `desktop_cf_solver.py:12,80`.

### B. Replace the 1 s cookie poll with event-driven checks (recommended)

`check_cookies` polls `window.get_cookies()` every 1.0 s up to 120 times
(`desktop_cf_solver.py:61-62`), so success is detected up to ~1 s late and
120 wakeups burn GUI-thread round-trips. Two verified faster triggers:

1. `window.events.loaded` fires after **every** completed navigation
   (`util.inject_pywebview`, `util.py:225-238`; cleared on each
   `load_url`, `window.py:283-285`). Calling `get_cookies()` directly from a
   `loaded` handler is gate-free in practice: `_api_call` waits on the
   `loaded` threading event (`window.py:32-53`), which is already set at that
   point, so `Event.wait(20)` returns immediately (`event.py:68-69`).
2. `window.events.response_received` fires per WebView2 resource with a
   `webview.models.Response(url, status_code, headers)` payload
   (`edgechromium.py:351-357`, `models.py:15-22`), and `request_sent` with
   `Request(url, method, headers)` (`edgechromium.py:359-383`). A handler can
   inspect `response.url` for the target host (`animepahe`) vs. the challenge
   host and only then pay for a `get_cookies()` call — cutting both latency
   and the 120 `ExecuteScriptAsync`-adjacent round-trips. Keep the 120 s loop
   purely as a timeout backstop.

### C. Guard the backend: abort unless `webview.renderer` is EdgeChromium/CEF

On machines without WebView2 ≥ 86.0.622.0 (or .NET < 4.6.2),
`platforms/winforms.py:130-155` silently falls back to **MSHTML**, where
`get_cookies()` is not implemented and returns `[]` after logging an error
(`winforms.py:463-477`) — the solver would then spin the full 120 s and exit
with no JSON. Note `gui='edgechromium'` does **not** hard-fail: the WinForms
selection expression is `is_chromium = not is_cef and _is_chromium() and
forced_gui_ != 'mshtml'`, so a missing runtime still lands on MSHTML. The
robust check, available after `start()` sets it (`__init__.py:248-249`), is
`webview.renderer in ('edgechromium', 'cef')` — assert it on startup (or check
`HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-…}` as
`_is_chromium()` does) and fail fast with a "install WebView2 Runtime"
message instead of a 2-minute silent timeout.

### D. Hidden-first window with on-demand show (conditional win)

`create_window(hidden=True, focus=False, ...)` still constructs the WebView2
control and runs the full navigation/JS/cookie pipeline — WinForms only swaps
`Opacity=0; Show(); Hide(); Opacity=1` (`winforms.py:777-781`), and
`on_webview_ready` loads `real_url` regardless of visibility
(`edgechromium.py:305-311`). `focus=False` adds `WS_EX_NOACTIVATE` so the
window never steals keyboard focus (`winforms.py:294-299`). So: launch hidden
for the common non-interactive challenge, and call `window.show()` (gates on
`shown`, callable any time after) only if no `cf_clearance` appears within
~15–20 s — i.e. escalate to visible exactly when the challenge is likely an
interactive Turnstile that needs a click. `window.hide()` can return it to
hidden afterwards. This preserves today's behavior in the hard case while
removing the popup in the easy case.

### E. What the `js_api` bridge can and cannot do for this solver

The bridge (`util.js_bridge_call`, `util.py:247-266`; `js/api.js:83-133`)
exposes **Python functions to page JS** (`window.pywebview.api.*`, async,
Promise-based). It does not give Python any new observation power over
third-party pages: Cloudflare's challenge JS will never call our functions,
so `js_api` cannot detect challenge progress. The correct tools for that are
already in the package and already partially used: `evaluate_js` (sync reads
of `document.title`, `navigator.userAgent`), `get_current_url()`, and the
`request_sent`/`response_received` events (B). Do not add a `js_api` expecting
challenge callbacks — it only pays off on pages we serve ourselves.

### F. Minor: match `WEBVIEW2_RUNTIME_PATH` / `REMOTE_DEBUGGING_PORT` usage

- `settings['WEBVIEW2_RUNTIME_PATH']` (relative paths resolved against app
  root) pins a known-good runtime (`edgechromium.py:64-77`) — useful for
  frozen builds where the system runtime is unpredictable.
- `settings['REMOTE_DEBUGGING_PORT']` appends `--remote-debugging-port=<n>`
  (`edgechromium.py:87-90`); combined with `start(debug=True)` it allows
  attaching DevTools to a stuck solver run. Dev-only, never ship it on.

### Explicitly unverified (checked, could not confirm from source)

- Whether a **hidden** WebView2 window passes Cloudflare bot-detection at the
  same rate as a visible one. Source confirms the page pipeline is identical
  (D); bot verdict depends on Cloudflare server-side signals (occlusion,
  focus, GPU throttling) that cannot be determined by reading this package.
  Needs an A/B run, not a code read.
- Whether `cf_clearance` issuance differs between `private_mode=True`
  (fresh `TemporaryDirectory` profile, `winforms.py:740-758`) and a persistent
  `storage_path`. Source confirms the storage mechanics; issuance policy is
  Cloudflare-side. The current default (ephemeral) is the safer choice until
  measured.
- Exact Turnstile-interactive behavior while minimized (timer throttling under
  occlusion) — WinForms/EdgeChromium sources show rendering continues, but
  frame-rate/throttle policy lives in Chromium internals, not this package.
