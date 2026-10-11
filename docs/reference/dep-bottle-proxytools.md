# bottle 0.13.4 + proxy-tools 0.1.0 — combined reference (installed venv build)

> Reference compiled from the installed packages
> (`.venv/Lib/site-packages/bottle.py`, `.venv/Lib/site-packages/proxy_tools/`,
> `*.dist-info/METADATA`, `uv.lock`) plus `grep` over pywebview's installed source
> (`.venv/Lib/site-packages/webview/`) plus `grep` over `src/` and `tests/` plus
> live introspection via `uv run python` from
> `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.
> Both are transitive dev-only deps: `pyproject.toml` dev group lists
> `"pywebview>=6.2.1"`; neither package is a direct dependency.

Method (repro):

- `Read` `proxy_tools/__init__.py` (179 lines); `grep`/`sed` over `bottle.py`
  (4681 lines, 180066 bytes); `METADATA` of both dist-infos; `uv.lock` pins.
- `grep -rn "bottle"` and `grep -rn "proxy_tools"` over
  `.venv/Lib/site-packages/webview/`; `Read` `webview/http.py` (228 lines) and
  relevant slices of `webview/__init__.py`, `webview/window.py`, `webview/util.py`.
- `grep -rn "bottle\|proxy_tools\|proxy-tools"` over `src/` (exit 1, no matches)
  and over `tests/` (no matches); `grep webview|pywebview` over `src/`+`tests/`.
- Live: `uv run python -c "import bottle, proxy_tools, webview.http…"`.

## 0. Position in the graph

| Pkg | Version (source of truth) | Declares dep on | Required by (METADATA) | Chain to this app |
|---|---|---|---|---|
| bottle | 0.13.4 (`bottle-0.13.4.dist-info/METADATA` `Name/Version`; `bottle.py:20` `__version__ = '0.13.4'`; live `bottle.__version__` → `0.13.4`) | nothing | `pywebview` (`pywebview-6.2.1.dist-info/METADATA:70` `Requires-Dist: bottle`, unpinned, ungated) | `dev-group pywebview → bottle` (unconditional, not extra-gated) |
| proxy-tools (import name `proxy_tools`) | 0.1.0 (`proxy_tools-0.1.0.dist-info/METADATA` `Name: proxy_tools` / `Version: 0.1.0`; module has **no** `__version__`) | nothing | `pywebview` (`pywebview-6.2.1.dist-info/METADATA:69` `Requires-Dist: proxy_tools`, unpinned, ungated) | `dev-group pywebview → proxy-tools` (unconditional, not extra-gated) |

`uv.lock` pins: `[[package]] name = "bottle" version = "0.13.4"` (registry,
sdist + wheel hashes) and `[[package]] name = "proxy-tools" version = "0.1.0"`
(registry, sdist only, uploaded 2014-05-05). `[[package]] name = "pywebview"
version = "6.2.1"` lists `{ name = "bottle" }` and `{ name = "proxy-tools" }`
in its `dependencies`.

`bottle-0.13.4.dist-info/entry_points.txt` declares one console script:
`bottle = bottle:main`. Nothing in the app or pywebview invokes it.

## 1. bottle 0.13.4 — what it is

`bottle-0.13.4.dist-info/METADATA` Summary: "Fast and simple WSGI-framework
for small web-applications." MIT, single-module package
(`.venv/Lib/site-packages/bottle.py`, no package directory). Python 2.7 + 3
classifiers; installed here under `requires-python = ">=3.13"`.

Public API surface (top-level `class`/`def` in `bottle.py`, selected):

- App: `Bottle` (:614; `run()` method at :860), `AppStack` (:2601).
- Server adapters: `ServerAdapter` (:3468) + built-ins (`CGIServer`, wsgiref,
  etc. below it). Base shape:
  ```python
  class ServerAdapter(object):
      quiet = False
      def __init__(self, host='127.0.0.1', port=8080, **options): ...
      def run(self, handler): ...   # live sig: (self, handler)
  ```
- Routing: `Router` (:299), `Route` (:502), errors `RouteError`, `RouteReset`,
  `RouterUnknownModeError`, `RouteSyntaxError`, `RouteBuildError`.
- Request/response: `BaseRequest` (:1153), `LocalRequest` (:1929),
  `BaseResponse` (:1637), `LocalResponse` (:1939); **module-level singletons**
  `request = LocalRequest()` (:4603) and `response = LocalResponse()` (:4607).
- Helpers pywebview actually calls: `static_file(filename, root,
  mimetype=True, download=False, charset='UTF-8', etag=None, headers=None)`
  (:2839), `run(app=None, server='wsgiref', host='127.0.0.1', port=8080,
  interval=1, reloader=False, quiet=False, plugins=None, debug=None,
  config=None, **kargs)` (live sig; def at :3885), `abort`, `redirect`,
  `debug`, `cookie_encode`/`cookie_decode`, `parse_auth`,
  `parse_range_header`, `static_file`, `FileUpload`, `ConfigDict`,
  `JSONPlugin`, `TemplatePlugin`.
- Data types: `DictProperty`, `cached_property`, `lazy_attribute`,
  `MultiDict`, `FormsDict`, `HeaderDict`, `WSGIHeaderDict`, `ResourceManager`.

## 2. Where pywebview uses bottle (`webview/http.py` — the only file)

`grep -rn "bottle" webview/` matches exactly one file: `webview/http.py`.
Reference lines: `import bottle` (:30); `ThreadedAdapter(bottle.ServerAdapter)`
(:56); `bottle.Bottle()`, `bottle.response`, `bottle.request`,
`bottle.static_file`, `bottle.run`, `bottle.ServerAdapter` (:104–165).

### 2.1 `ThreadedAdapter` (:56–72)

```python
class ThreadedAdapter(bottle.ServerAdapter):
    def run(self, handler):
        if self.quiet:
            class QuietHandler(WSGIRequestHandler):
                def log_request(*args, **_): pass
            self.options['handler_class'] = QuietHandler
        class ThreadAdapter(ThreadingMixIn, WSGIServer): pass
        server = make_server(self.host, self.port, handler,
                             server_class=ThreadAdapter, **self.options)
        server.serve_forever()
```

Live MRO: `['ThreadedAdapter', 'ServerAdapter', 'object']`. This is what makes
the built-in server multi-threaded; the stdlib `wsgiref` server alone is
single-threaded.

### 2.2 `BottleServer` (:75–160) — pywebview's built-in HTTP server

Live MRO: `['BottleServer', 'object']` (plain class, not a `ServerAdapter`).

`BottleServer.start_server(urls, http_port, keyfile=None, certfile=None)`
(:84–155):

- `apps = [u for u in urls if is_app(u)]` — `is_app` = `callable(url)`
  (`util.py:70-72`). If a window URL is a WSGI/ASGI callable, that callable
  **is** the app (`app = apps[0]`, `common_path = '.'`).
- Else builds `app = bottle.Bottle()` with exactly two route handlers:
  - `POST /js_api/<server.uid>` (`js_api`, :106–120): sets
    `Access-Control-Allow-Origin: *` + allow-methods/headers, parses
    `json.loads(bottle.request.body.read().decode('utf-8'))`, dispatches
    `server.js_callback[body['uid']](body)`, missing uid → `logger.error`.
    This is the **js_api bridge over HTTP** (used by some backends instead of
    native messaging).
  - `GET /` and `/<file:path>` (`asset`, :122–130): sets
    `Cache-Control: no-cache, no-store, must-revalidate`, `Pragma: no-cache`,
    `Expires: 0`, returns `bottle.static_file(file, root=server.root_path)`
    where `root_path` is the common dir of the local URLs. Empty `root_path`
    → returns `''`.
- Serves on a daemon thread:
  `bottle.run(app=app, server=server_adapter, port=server.port,
  quiet=not _state['debug'])` — `server_adapter` is `ThreadedAdapter` (plain
  HTTP) or `SSLWSGIRefServer` (keyfile+certfile).
- Address `http(s)://127.0.0.1:<random-or-given-port>/`
  (`_get_random_port` binds-probes `localhost` in 1023–65535, :42–53);
  `js_api_endpoint = <address>js_api/<uid>` (:153).

### 2.3 `SSLWSGIRefServer(bottle.ServerAdapter)` (:165–199)

HTTPS variant used only when `keyfile`+`certfile` passed (i.e.
`webview.start(ssl=True)`, which generates a throwaway cert via
`cryptography`). Wraps the `wsgiref` socket in `ssl.SSLContext`, disables
reverse-DNS in `FixedHandler.address_string`, deletes the keyfile after load
(:193–194). `pragma: no cover` on `run`.

### 2.4 When the server actually starts (verified call sites)

- `webview/__init__.py:274`: in `start()`,
  `if (http.global_server is None) and (http_server or has_local_urls)` →
  `http.start_global_server(...)`, where
  `has_local_urls = [w.original_url for w in windows if
  is_local_url(w.original_url)]` and `is_local_url` returns False for
  `http://`, `https://`, `file://`, empty, or callable URLs (`util.py:75-84`).
  Non-`private_mode` without explicit port → `DEFAULT_HTTP_PORT` 42001.
- `window.py:195`: `Window._initialize` starts a **per-window** server only
  `if is_app(self.original_url)` (WSGI callable) and no global server.
- `window.py:280`: `load_url` starts a server only `if is_app(url) or
  is_local_url(url)`.
- `window.py:186-208`: `js_api_endpoint` on a window is
  `http.global_server.js_api_endpoint if http.global_server is not None else
  None` — None when no server runs.

Net: a window showing a **remote `https://` URL with no `js_api`** (exactly
what the desktop CF solver does — see §4) **never starts bottle**; all four
conditions above are False.

### 2.5 Incidental: `pythonw.exe` stdout shim (`http.py:7-13`)

On win32 with `pythonw.exe` or frozen exe, `sys.stdout`/`sys.stderr` (None)
are replaced with `os.devnull` handles because "bottle.py versions prior to
0.12.23 … require stdout and stderr to exist". Historical guard; installed
bottle is 0.13.4 so the original bug is gone, but the shim is harmless.

## 3. proxy-tools 0.1.0 — what it is

`proxy_tools-0.1.0.dist-info/METADATA` Summary: "Proxy Implementation",
author Jonathan Tushman, MIT. Single module
`.venv/Lib/site-packages/proxy_tools/__init__.py` (179 lines); header:
"Proxy. Extracted from Werkzeug … (c) 2013 by Armin Ronacher (adapted by
Jonathan Tushman 2014)". No Python-3-only modernization — still ships
`PY2 = sys.version_info[0] == 2` branches and Py2-only dunders
(`__getslice__`, `__long__`, `__cmp__`, `__coerce__`, `__unicode__`: dead code
on 3.13 but valid).

Public API (live `dir(proxy_tools)` non-underscore):
`['PY2', 'Proxy', 'implements_bool', 'module_property', 'proxy', 'sys']`.

- `Proxy(local, name=None)` (:25–174): forwards **every** operation to the
  current object. Two binding modes in `_get_current_object` (:56–66):
  - plain callable: `self.__local()` (no `__release_local__` attr);
  - object+name pair: `getattr(self.__local, self.__name__)`, unbound →
    `RuntimeError('no object bound to …')`.
  - `__slots__ = ('__local', '__dict__', '__name__')`; `__dict__` property
    proxies to the target; `__getattr__` delegates; `__setattr__`/`__delattr__`
    and ~40 operator dunders (`__call__`, `__iter__`, `__len__`,
    `__getitem__`, comparisons, arithmetic, reflected arithmetic, context
    manager, `__bool__` → False when unbound) all forward. Only operations
    **not** forwarded: right-handed operands and any kind of assignment
    (per docstring :26–28).
- Aliases (:177–179): `module_property = Proxy`, `proxy = Proxy` — same class,
  three names. The `module_property` name documents the intended use: decorate
  a module-level function so attribute access on the module lazily computes
  the value on every access.

### Where pywebview uses it (`webview/__init__.py` — the only file)

`grep -rn "proxy_tools" webview/` matches exactly one file:
`webview/__init__.py:24` (`from proxy_tools import module_property`), used at
5 sites:

| Line | Decorated name | Behavior |
|---|---|---|
| 88 | `OPEN_DIALOG` | deprecated; `logger.warning`, returns `10` |
| 96 | `FOLDER_DIALOG` | deprecated; `logger.warning`, returns `20` |
| 104 | `SAVE_DIALOG` | deprecated; `logger.warning`, returns `30` |
| 149 | `DRAG_REGION_SELECTOR` | deprecated; warns, returns `settings['DRAG_REGION_SELECTOR']` |
| 512 | `screens` | lazy init: `guilib = initialize()` if unset, returns `guilib.get_screens()` |

So `module_property` gives pywebview **lazy module attributes with
deprecation warnings**: each access re-invokes the function (deprecation
warnings fire on *every* access, not once). `screens` is the only
non-deprecated use — it defers GUI init until first access. Replacing
`proxy_tools` with `functools.cached_property`-style caching would change
warning semantics; pywebview intentionally re-warns.

## 4. Does our app touch either package?

**No — verified by grep, for both `src/` and `tests/`:**

- `grep -rn "bottle\|proxy_tools\|proxy-tools" src/` → exit 1, zero matches.
- `grep -rln "bottle\|proxy_tools\|proxy-tools" tests/` → zero matches.
- Neither appears in `pyproject.toml` (runtime deps: flet, flet-video,
  flet-webview, flet-yandex-ads, flet-notifications, primp; dev group adds
  ruff, pytest, pytest-asyncio, pywebview, qtpy, pyqt6-webengine).
- `import webview` appears exactly once in `src/`
  (`src/services/desktop_cf_solver.py:4`); all other `webview` hits are
  `flet_webview` (mobile/TV path) or comments.

### Relevance to the desktop CF solver

Chain: `webview_solver._solve_desktop` (`src/services/webview_solver.py:41`)
spawns `desktop_cf_solver.py` as a subprocess; that script does
`webview.create_window("Cloudflare Turnstile Solver", url, …)` (:106–108)
with a **remote `https://` URL from `sys.argv[1]`** and
`webview.start(check_cookies, window)` (:110) with all defaults
(`http_server=False`, no `js_api`, no `server=` override):

- Per §2.4, a remote https URL is neither app nor local, and `http_server`
  is False → `http.global_server` stays None → **bottle never runs** in the
  solver process. No localhost port is opened, `window.js_api_endpoint` is
  None, and the `POST /js_api/<uid>` / `GET /<file:path>` routes never exist.
- The challenge page, its Turnstile JS, and `cf_clearance` issuance all happen
  inside WebView2 against the remote host; cookie capture goes through
  `window.get_cookies()` (native `CookieManager`), not through bottle.
- `proxy_tools.module_property` executes only inside the pywebview package
  itself (deprecated-constant warnings, lazy `screens`); the solver never
  accesses `webview.screens` or the deprecated dialog constants, so the Proxy
  machinery is inert at runtime beyond import time.
- Therefore: **upgrading, pinning, or removing bottle/proxy-tools has zero
  behavioral effect on the solver as long as the solver keeps passing a
  remote URL with no `js_api`**. They matter only if the solver ever (a)
  serves a local solver page over HTTP, (b) passes a WSGI callable as `url`,
  or (c) passes `js_api=` (which on some backends is served via the
  `/js_api/<uid>` bottle route).

## 5. App improvement opportunities

Nothing significant exists — stated plainly with the evidence of what was
checked:

1. **No action on either package.** Both are unpinned transitive deps of a
   dev-only dependency (`pywebview>=6.2.1`), unreachable from `src/` or
   `tests/` (empty greps, §4), and provably inert in the solver's
   remote-URL configuration (§2.4, §4). There is no version to bump in
   `pyproject.toml` (they are not listed there), no API of ours to migrate,
   and no bottle-served surface to harden (no localhost listener exists in
   the solver process).
2. **Only conditional note (not a recommendation):** if the solver ever gains
   a locally-hosted solver page (e.g. `create_window(..., html=…)` with local
   assets or a `js_api=` bridge), bottle's `BottleServer` *would* start
   listening on `127.0.0.1` with `Access-Control-Allow-Origin: *` on the
   `/js_api/<uid>` route (`http.py:106-120`) and no-cache static serving
   (`http.py:122-130`). That configuration would deserve a security review
   (CORS wildcard + random port + per-process uid). Today that code path is
   dead for the solver — confirmed by the start conditions in
   `__init__.py:274`, `window.py:195`, `window.py:280` — so this is a
   future-tripwire note, not a finding.
3. Checked and dismissed: `bottle = bottle:main` console script (never
   invoked); `SSLWSGIRefServer` (needs `ssl=True`, solver uses defaults);
   `ThreadedAdapter` quiet flag (follows `_state['debug']`, defaults quiet);
   `proxy_tools` Py2 dead code (upstream maintenance state, no runtime effect
   on 3.13); replacing `module_property` (would change pywebview's
   warn-on-every-access semantics — not our code to change).
