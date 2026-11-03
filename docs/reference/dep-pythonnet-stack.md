# pythonnet stack 3.2.1 / 0.3.1 / 2.1.1 / 3.11 — complete reference (installed venv build)

> Reference compiled from the installed packages
> (`.venv/Lib/site-packages/`, versions per `importlib.metadata` verified live:
> `pythonnet 3.2.1`, `clr_loader 0.3.1`, `cffi 2.1.1`, `pycparser 3.11`,
> `pywebview 6.2.1`) — every behavioural claim below was verified live via
> `uv run --project C:/Users/nwoki/ad-extensions/sources/animepahe-tv python`
> on Win64 / CPython 3.13.15, or is quoted verbatim from the installed source.
> Dependency status: `pywebview 6.2.1` declares
> `Requires-Dist: pythonnet; sys_platform == "win32"` (its METADATA, line 60);
> `pythonnet 3.2.1` declares `Requires-Dist: clr_loader<0.4.0,>=0.3.1`
> (its METADATA, line 25); `clr_loader 0.3.1` declares
> `Requires-Dist: cffi>=1.17` (its METADATA, line 17); `cffi 2.1.1` declares
> `Requires-Dist: pycparser; implementation_name != "PyPy"` (its METADATA).
> Chain: app → pywebview → pythonnet → clr-loader → cffi → pycparser.
> None of the four packages appears in `pyproject.toml` `[project].dependencies`
> (only `pywebview>=6.2.1` under `[dependency-groups] dev`, line 42) — they are
> all transitive, pinned in `uv.lock` (`pythonnet 3.2.1` at line 590,
> `clr-loader 0.3.1` at line 111, `cffi 2.1.1` at line 79).
> Our app's consumer: `src/services/desktop_cf_solver.py` (desktop Cloudflare
> solver, spawned as a subprocess by `src/services/webview_solver.py::_solve_desktop`,
> reads `window.get_cookies()` + `evaluate_js("navigator.userAgent")`).
> Companion doc: `docs/reference/dep-pywebview.md` (pywebview API surface).

## 0. TL;DR for this codebase

- **pythonnet is pywebview's Windows EdgeChromium enabler and nothing else.**
  pywebview's `platforms/edgechromium.py:9-13` does `import clr`, falling back to
  `os.environ['PYTHONNET_RUNTIME'] = 'coreclr'; import clr` on failure; it then
  loads `System.Windows.Forms` + the two `Microsoft.Web.WebView2.*` interop DLLs
  that pywebview ships under `webview/lib/` and drives WebView2 from Python.
  Our solver (`desktop_cf_solver.py`) never touches `clr` / `pythonnet` directly —
  it talks to `webview.create_window` / `window.get_cookies()` only.
- **Default runtime on Windows is .NET Framework (netfx), not .NET Core.**
  `pythonnet/__init__.py:62-67`: `spec == "default"` maps to `"netfx"` on
  `sys.platform == "win32"`. Verified live: `pythonnet.load()` with no env vars →
  `Runtime: .NET Framework`, `System.Environment.Version` → `4.0.30319.42000`.
- **CoreCLR is only reachable via explicit opt-in** (`PYTHONNET_RUNTIME=coreclr`
  or `pythonnet.load("coreclr")`) **and needs a `runtimeconfig.json` or an
  installed `dotnet` SDK/root** — which this machine does NOT have
  (`find_dotnet_root()` → `RuntimeError: Can not determine dotnet root`,
  verified live). pywebview requests coreclr only as a *fallback* (see above);
  on a stock Windows box with .NET Framework present, the first `import clr`
  succeeds on netfx and the fallback never fires.
- **Yes — the solver can reach WebView2's `CoreWebView2CookieManager` directly
  for HttpOnly cookies** (including `cf_clearance`). Verified live:
  after `clr.AddReference(interop_dll_path('Microsoft.Web.WebView2.Core.dll'))`,
  `CoreWebView2CookieManager` exposes `GetCookiesAsync`, `CreateCookie`,
  `AddOrUpdateCookie`, `CopyCookie`, `CreateCookieWithSystemNetCookie`,
  `DeleteAllCookies`, `DeleteCookie(s)`, `DeleteCookiesWithDomainAndPath`;
  `CoreWebView2Cookie` exposes `Name/Value/Domain/Path/Expires/IsHttpOnly/
  IsSecure/IsSession/SameSite` (+ `ToSystemNetCookie`). pywebview's own
  `EdgeChrome.get_cookies` (`edgechromium.py:170-204`) already goes through
  exactly this path (`CoreWebView2.CookieManager.GetCookiesAsync(self.url) …`
  reading `c.IsHttpOnly`), so `window.get_cookies()` in the solver already
  returns HttpOnly cookies — no direct CLR work is needed (see §6).
- **cffi's role is the native bridge inside clr-loader; pycparser is
  build-time-only.** `clr_loader/ffi/__init__.py:5` does `import cffi` and builds
  one shared `ffi = cffi.FFI()` whose `cdef`s come from `ffi/hostfxr.py`,
  `ffi/mono.py`, `ffi/netfx.py`; every CLR call crosses this bridge
  (`types.py:64-65`: `ffi.from_buffer` + `ffi.cast`). pycparser is referenced
  nowhere in `clr_loader/` (grep-verified); cffi uses it only to parse C
  declarations at `ffi.cdef()` time — it ships no runtime code path of ours.

## 1. What pythonnet 3.2.1 loads on Windows (runtime selection)

Entry points (`pythonnet/__init__.py`, the whole file is 169 lines):

```python
__all__ = ["set_runtime", "set_runtime_from_env", "load", "unload", "get_runtime_info"]
```

Runtime names: `"netfx"`, `"coreclr"`, `"mono"`, `"default"`
(`_create_runtime_from_spec`, lines 58-93).

| Selector | Code | Effect on Windows |
|---|---|---|
| default (no env, bare `import clr` / `load()`) | `__init__.py:62-67` — `if sys.platform == "win32": spec = "netfx"` | .NET Framework via bundled `ClrLoader.dll` |
| `PYTHONNET_RUNTIME=coreclr` (env) | `set_runtime_from_env`, lines 96-115; per-param overrides `PYTHONNET_<RUNTIME>_<PARAM>` via `_get_params_from_env` (lines 43-55) | .NET Core via `hostfxr`, needs `runtime_config` or discoverable `dotnet` root |
| `PYTHONNET_RUNTIME=netfx` (env) | same | explicit .NET Framework |
| `pythonnet.load("coreclr")` / `load("netfx")` | `load()`, lines 118-152 | same, programmatic |
| pywebview fallback | `edgechromium.py:9-13`, `winforms.py:13-17`, `mshtml.py:9-14`: try `import clr`, except → set `PYTHONNET_RUNTIME=coreclr`, retry | netfx first, coreclr only if netfx failed |

`clr.py` (7 lines, verbatim) is the legacy shim every `import clr` executes:

```python
"""
Legacy Python.NET loader for backwards compatibility
"""

from pythonnet import load

load()
```

So the first `import clr` in a process calls `set_runtime_from_env()` once;
after that `_LOADED = True` and further `load()` calls return immediately
(lines 128-129), while `set_runtime()` after load raises
`RuntimeError("The runtime … has already been loaded")` (line 26) — both
verified live (double `load()` silent, `set_runtime("coreclr")` post-load raised
`RuntimeError: The runtime <clr_loader.netfx.NetFx object at 0x…> has already
been loaded`).

**Live probe (this machine, no `PYTHONNET_*` set):**

```
runtime_info before load: None
Runtime: .NET Framework
=============
  Version:      <undefined>
  Initialized:  True
  Shut down:    False
  Properties:
    domain =
    config_file = None
clr OK: clr
NET version: 4.0.30319.42000
```

Notes: `Version: <undefined>` is normal for netfx — `NetFx.info()` hardcodes
`version="<undefined>"` (`netfx.py:28-36`); the real CLR version comes from
`System.Environment.Version` (`4.0.30319.42000` = .NET Framework 4.x CLR).

What "loads" physically on the netfx path (`clr_loader/ffi/__init__.py:53-65`):

```python
def load_netfx():
    if sys.platform != "win32":
        raise RuntimeError(".NET Framework is only supported on Windows")
    dirname = Path(__file__).parent / "dlls"
    if sys.maxsize > 2**32:
        arch = "amd64"
    else:
        arch = "x86"
    path = dirname / arch / "ClrLoader.dll"
    return ffi.dlopen(str(path))
```

i.e. cffi `dlopen`s the `ClrLoader.dll` shipped inside the clr-loader wheel
(`clr_loader/ffi/dlls/amd64/ClrLoader.dll` + `.pdb` present in the venv),
which exposes five C functions (`ffi/netfx.py` cdef, verbatim):

```
typedef void* pyclr_domain;
typedef int (*entry_point)(void* buffer, int size);
void pyclr_initialize();
void* pyclr_create_appdomain(const char* name, const char* config_file);
entry_point pyclr_get_function(pyclr_domain domain, const char* assembly_path,
                               const char* class_name, const char* function);
void pyclr_close_appdomain(pyclr_domain domain);
void pyclr_finalize();
```

pythonnet then loads exactly one managed assembly through it
(`__init__.py:140-148`): `<site-packages>/pythonnet/runtime/Python.Runtime.dll`
(present; alongside `Python.Runtime.deps.json` + `.xml`), calling
`Python.Runtime.Loader.Initialize` and registering `unload()` at exit.
The `.deps.json` targets `netstandard2.0` (`runtimeTarget.name` =
`.NETStandard,Version=v2.0/`, package `Python.Runtime/3.2.1`) — hence it runs
on Framework 4.7.2+ and on any modern CoreCLR.

`get_netfx()` parameters (`clr_loader/__init__.py:180-196`): only
`domain: str | None` and `config_file` (AppDomain config, non-root domains
only). No runtimeconfig.json involved on this path.

## 2. The clr_loader mechanism + which runtime config files it needs

Three runtime classes, one per hosting API:

- `clr_loader/netfx.py` — `NetFx`. In-process COM-style hosting via the bundled
  `ClrLoader.dll`. Config surface: optional AppDomain `config_file` only.
  No JSON config, no SDK discovery, no `dotnet` CLI involved.
- `clr_loader/hostfxr.py` — `DotnetCoreRuntime`. Hosts .NET Core through
  `hostfxr.dll` resolved under a `dotnet_root` (`ffi/__init__.py:17-41`: globs
  `<dotnet_root>/host/fxr/*/hostfxr.dll`, newest version first). **Requires
  either `runtime_config` (a `runtimeconfig.json` as produced by
  `dotnet publish`) or `entry_dll`** (`__init__.py:92-177`); with neither, it
  auto-generates a temp `runtimeconfig.json` from the newest
  `Microsoft.NETCore.App` found by `find_runtimes()`. Root discovery order
  (`util/find.py:23-63`): `$DOTNET_ROOT` → `%ProgramFiles%\dotnet` (win32) →
  `dotnet` on `PATH` (resolved to its parent dir) → else
  `RuntimeError("Can not determine dotnet root")`.
  **This machine: no `DOTNET_ROOT`, no `%ProgramFiles%\dotnet`, no `dotnet` on
  PATH → both `find_dotnet_root()` and `find_runtimes()` raise that exact
  error (verified live). CoreCLR cannot initialise here.**
- `clr_loader/mono.py` — `Mono`. Irrelevant on Windows for us (default is
  netfx; pywebview never requests mono on win32), listed for completeness.
  Looks for `%ProgramFiles%\Mono\bin\mono-2.0-sgen.dll` (`util/find.py:138-148`).

Version floor note: `mono.py:192-205` warns that hosting Mono < 6.12 is
"known to be problematic" — netfx/CoreCLR paths unaffected.

`DotnetCoreRuntimeSpec.write_config` (`util/runtime_spec.py:38-40`) writes the
minimal config the auto-generate path uses:

```json
{"runtimeOptions": {"tfm": "netX.Y",
 "framework": {"name": "Microsoft.NETCore.App", "version": "X.Y.0"}}}
```

Bottom line for config files: **on the netfx path this app actually uses,
clr-loader needs zero config files** — the native hosting DLL and
`Python.Runtime.dll` both ship inside the wheels. `runtimeconfig.json` only
matters if someone forces `PYTHONNET_RUNTIME=coreclr`.

## 3. What .NET APIs become reachable from Python

Once loaded, `import clr; clr.AddReference(<name-or-path>)` makes CLR
namespaces importable as Python packages (per pythonnet METADATA usage docs,
lines 52-68). Verified live on the default netfx runtime:

- `clr.AddReference('System.Windows.Forms')` → `from System.Windows.Forms
  import Form` works (`<class 'System.Windows.Forms.Form'>`).
- `clr.AddReference(interop_dll_path('Microsoft.Web.WebView2.Core.dll'))`
  (absolute path into `webview/lib/…`, resolved by `webview/util.py:480-493`)
  → `from Microsoft.Web.WebView2.Core import CoreWebView2Cookie` works.

Full `CoreWebView2CookieManager` member list (verified live via `dir()` after
`AddReference`, netfx runtime):

```
AddOrUpdateCookie, CopyCookie, CreateCookie, CreateCookieWithSystemNetCookie,
DeleteAllCookies, DeleteCookie, DeleteCookies, DeleteCookiesWithDomainAndPath,
GetCookiesAsync (+ Equals/Finalize/GetHashCode/GetType/ToString boilerplate)
```

`CoreWebView2Cookie` members (same probe): `Domain, Expires, IsHttpOnly,
IsSecure, IsSession, Name, Path, SameSite, Value, ToSystemNetCookie`
(+ get_/set_ accessors). `IsHttpOnly` is a plain readable property — so yes,
**a solver holding a `CoreWebView2` instance can enumerate HttpOnly cookies
(e.g. `cf_clearance`) via `CookieManager.GetCookiesAsync(url)`**, create or
overwrite them via `CreateCookie(name, value, domain, path)` +
`AddOrUpdateCookie(cookie)`, and wipe them via `DeleteAllCookies()`.
pywebview's `EdgeChrome` already exercises all three (`edgechromium.py:168`
`clear_cookies`, `:202` `get_cookies`, `:303` private-mode wipe), and its
`get_cookies` explicitly marshals `c.IsHttpOnly` into each returned cookie
(`:190`, then `create_cookie(data)` at `:194` → `window.get_cookies()` returns
`http.cookies.SimpleCookie` objects — which is exactly what
`desktop_cf_solver.py:68-76` iterates).

Caveat (source-evidence, not run-evidence): reaching `CoreWebView2` directly
requires a live `WebView2.CoreWebView2` instance, which only exists after
`EnsureCoreWebView2Async` completes inside a running WinForms message loop —
pywebview owns that lifecycle (`EdgeChrome.__init__`, `edgechromium.py:58-120`).
There is no supported way to conjure a second `CoreWebView2` from the solver
subprocess without going through pywebview's window. Practically: use
`window.get_cookies()`, not raw CLR.

## 4. cffi's role (pycparser → cffi → clr-loader chain)

- `clr_loader/ffi/__init__.py:5,11-14`: `import cffi`, one module-global
  `ffi = cffi.FFI()`, then `ffi.cdef(...)` for every declaration in
  `ffi/hostfxr.py` + `ffi/mono.py` + `ffi/netfx.py`. The C sources are parsed
  **at import time** — this is the only place pycparser participates (cffi's
  `cdef` parser), and only on CPython (`pycparser; implementation_name !=
  'PyPy'` marker in cffi's METADATA).
- Every CLR invocation crosses cffi: `Assembly.get_function` returns a
  `ClrFunction` whose `__call__` does `ffi.from_buffer("char[]", buffer)` +
  `ffi.cast("void*", …)` (`types.py:61-65`). Native lib: `_cffi_backend.cp313-
  win_amd64.pyd` present in the venv (compiled, version-matching CPython 3.13).
- Failure implication: if cffi's backend `.pyd` is missing/mismatched,
  **nothing** CLR-flavoured works — `import clr_loader.ffi` itself fails before
  any .NET code runs. No such problem here (`type(ffi)` →
  `<class 'cffi.api.FFI'>`, verified live).
- pycparser (`3.11`, pure Python, `Requires-Python: >=3.10`) is therefore a
  **build/parse-time transitive dep with no runtime code path of ours** —
  correctly classified as a dev-only transitive in the task brief. It can be
  ignored for failure analysis.

## 5. Version constraints (all verified against installed METADATA / lock)

| Package | Installed | Requires-Python | Key pin |
|---|---|---|---|
| pythonnet | 3.2.1 | `>=3.11,<3.16` (supports 3.11–3.15; we run 3.13.15 ✓) | `clr_loader<0.4.0,>=0.3.1` |
| clr-loader | 0.3.1 | `>=3.10` | `cffi>=1.17` (we have 2.1.1 ✓) |
| cffi | 2.1.1 | `>=3.10` (incl. 3.13/3.14/3.15 + free-threading per classifiers) | `pycparser` iff not PyPy |
| pycparser | 3.11 | `>=3.10` | none |
| pywebview | 6.2.1 | `>=3.8` | `pythonnet; sys_platform == "win32"` (win-only dep) |
| app | 1.0.9 | `>=3.13` (`pyproject.toml:5`) | `pywebview>=6.2.1` dev-group only (line 42); none of the four in main `dependencies` (lines 7-14) |

`uv.lock` pins: `pythonnet 3.2.1` (line 590, `dependencies = [{name =
"clr-loader"}]`), `clr-loader 0.3.1` (line 111), `cffi 2.1.1` (line 79),
`pywebview 6.2.1` win32-gated (line 614). pythonnet ships `py.typed`
markers (`clr_loader/py.typed` present) — typed API.

Upgrade headroom (record, not recommendation): pythonnet Requires-Python caps
at `<3.16`, so a future CPython 3.16 would break the stack; cffi 2.1.1 already
covers up to 3.15. No action — app pins `>=3.13` with 3.13.15 installed.

## 6. How the desktop solver actually uses this path (cross-check)

`src/services/webview_solver.py::_solve_desktop` (lines 41-118) spawns
`[.venv python, src/services/desktop_cf_solver.py, url]` as a subprocess and
reads one JSON line from its stdout. `desktop_cf_solver.py` (whole file,
103 lines) calls only three pywebview APIs: `webview.create_window`,
`window.events.loaded`, `webview.start(check_cookies, window)`; its poll loop
calls `window.get_cookies()` (returns `list[SimpleCookie]`) and
`window.evaluate_js("navigator.userAgent")` / `get_current_url()`, completing
when `cf_clearance` + a target marker (`animepahe_session|serverid|xsrf-token|
latest`) are present and the title/URL no longer look like a challenge
(`is_challenge_complete`, lines 19-55).

Dispatch chain for `get_cookies()` on this machine (all verified in source):

1. `window.get_cookies()` (`window.py:329-334`, `@_loaded_call`) →
   `self.gui.get_cookies(self.uid)`.
2. `winforms.get_cookies(uid)` (`winforms.py:932-938`) → `BrowserView.get_cookies`
   (`:463-477`), which **returns `[]` with `logger.error('get_cookies() is not
   implemented for this platform')` unless `is_chromium`** (`:467-470`).
3. `is_chromium = not is_cef and _is_chromium() and forced_gui_ != 'mshtml'`
   (`winforms.py:130-131,140-146`): needs a WebView2 runtime (registry check in
   `_is_chromium`, `:68-127`) and selects `renderer = 'edgechromium'`.
   **Registry check on this machine: `HKLM\…\EdgeUpdate\Clients` lists three
   client GUIDs and `HKCU\…\EdgeUpdate\Clients\{56EB18F8-…}` exists** (live
   `reg query`), i.e. Edge/WebView2 registration is present — the chromium path
   is expected. If it ever evaluated false, pywebview would silently fall back
   to MSHTML (`renderer = 'mshtml'`, `:147-155`) and the solver's cookie loop
   would poll empty jars until its 120 s timeout — with no error raised.
4. `EdgeChrome.get_cookies` (`edgechromium.py:170-204`):
   `CoreWebView2.CookieManager.GetCookiesAsync(self.url).ContinueWith(…)` on
   the UI sync-context scheduler, then `_parse_cookies` on the GUI thread
   (required — WebView2 throws off-thread; comment cites
   `MicrosoftEdge/WebView2Feedback#1976` at `:178-179`), mapping each cookie
   including `httponly: c.IsHttpOnly` and `expires` in RFC-1123 `en-US` via
   `CultureInfo`, through `create_cookie` (`util.py:133`).

Also load-bearing: `desktop_cf_solver.py` sets `captured_ua` default to an
Edge UA string (`… Chrome/149.0.0.0 … Edg/149.0.0.0`, line 6) — consistent with
the EdgeChromium renderer, not with MSHTML.

## 7. Common failure modes on Windows (exact error strings)

All strings below are verbatim from the installed source or from live probes
on this machine (probes marked LIVE; the rest are source-verbatim strings that
fire on the documented trigger).

**Runtime discovery / selection**

1. No .NET Core SDK when coreclr requested (LIVE — this machine has none):
   `RuntimeError: Can not determine dotnet root` (`util/find.py:61`), from
   `find_dotnet_root()` when `$DOTNET_ROOT`, `%ProgramFiles%\dotnet`, and
   `dotnet`-on-`PATH` all miss. Trigger in practice: `PYTHONNET_RUNTIME=coreclr`
   set (or pywebview's `import clr` fallback firing) on a box without the
   `dotnet` SDK/runtime. Note the netfx-first order means this only bites if
   Framework loading already failed.
2. No usable CoreCLR runtime found (source-verbatim, `__init__.py:154`):
   `RuntimeError: Failed to find a suitable runtime` — `get_coreclr()` with no
   config found zero `Microsoft.NETCore.App` entries (optionally filtered by
   `runtime_version="X.Y"`).
3. `hostfxr.dll` present but unloadable (source-verbatim, `ffi/__init__.py:38-41`):
   `RuntimeError: Could not find a suitable hostfxr library in <dotnet_root>.
   The following paths were scanned:` + per-path `dlopen` errors.
4. Invalid runtime name (LIVE): `RuntimeError: Failed to create a .NET runtime
   (bogus) using the parameters {}.` (`pythonnet/__init__.py:90-93`).
5. Default-runtime creation failure (source-verbatim wrapper, `__init__.py:81-88`):
   `RuntimeError: Failed to create a default .NET runtime, which would have
   been "<spec>" on this system. Either install a compatible runtime or
   configure it explicitly via set_runtime or the PYTHONNET_* environment
   variables (see set_runtime_from_env).` — chained (`from exc`) onto the root
   cause. **This is the error to grep logs for**: its `__cause__` names the real
   problem.
6. `set_runtime` after load (LIVE):
   `RuntimeError: The runtime <clr_loader.netfx.NetFx object at 0x…> has already
   been loaded`. And `load()` post-load is a silent no-op (LIVE-verified).
7. `Python.Runtime.dll` init failure (source-verbatim, `__init__.py:145-146`):
   `RuntimeError: Failed to initialize Python.Runtime.dll` — corrupted install.
8. Missing assembly / member on netfx (LIVE):
   `RuntimeError: Failed to resolve Foo.Bar.Baz from C:/nonexistent/Nope.dll`
   (`netfx.py:46-49`, NULL function pointer). Same shape for a typo'd
   `clr.AddReference` target that resolves-but-lacks the type.
9. `hostfxr` numeric errors surface as `ClrError("<hex>: <NAME> =>
   <message>")` (`util/__init__.py:27-41` checking `err_code < 0` against
   `hostfxr_errors.py` names e.g. `FrameworkMissingFailure=0x80008096`,
   `HostApiFailed`, `InvalidConfigFile`, `CoreClrInitFailure`…). Operators
   will see e.g. `0x80008096: FrameworkMissingFailure` when the
   `runtimeconfig.json` names a framework version that isn't installed.

**pywebview-level (what the solver actually surfaces)**

10. pythonnet missing/broken at backend import: `guilib.py:78`
    `logger.exception('pythonnet cannot be loaded')`, escalating to
    `WebViewException('You must have pythonnet installed in order to use
    pywebview.')` (`:135`). (Only reachable on Windows if `import winforms`
    fails entirely.)
11. Silent MSHTML downgrade (no exception at all): if `_is_chromium()` is false,
    `winforms.py:147-155` logs `MSHTML is deprecated…` + `Using WinForms /
    MSHTML`, and every `get_cookies()` returns `[]` with `logger.error(
    'get_cookies() is not implemented for this platform')` (`:468-470`).
    **Solver symptom: `[DEBUG] Cookie jar has 0 entries` × 120, then quiet
    exit 0 via `window.destroy()`** — indistinguishable from a stuck challenge
    without `PYWEBVIEW_LOG=DEBUG`. The single most likely "it just times out"
    cause attributable to this stack.
12. WebView2 init failure at runtime: `on_webview_ready` logs
    `WebView2 initialization failed with exception:\n <InitializationException>`
    (`edgechromium.py:267-273`) and returns — window stays on `DEFAULT_HTML`,
    cookies never populate. Missing/corrupt WebView2 runtime or bad
    `WEBVIEW2_RUNTIME_PATH` land here, not in pythonnet.
13. `get_cookies` marshaling is per-cookie try/except (`:182-197`): a single
    malformed cookie logs `logger.exception(e)` and is skipped — a jar that is
    *missing* `cf_clearance` but non-empty points here or at challenge state,
    not at CLR loading.

**cffi/pycparser-level**: a broken `_cffi_backend` fails at
`import clr_loader.ffi` (before any message about .NET) — symptom is an
`ImportError` naming `_cffi_backend`, never a CLR error string. pycparser has
no failure mode of its own at runtime (parse-time only).

## App improvement opportunities

Ranked by evidence strength. "Verified" = claim checked against installed
source and/or live probe in this pass. "Unverified" = needs an on-device run
(flagged, not asserted).

1. **Nothing in the pythonnet/clr-loader/cffi/pycparser layer needs changing —
   it works as pywebview's dependency. (Verified.)** Default netfx load
   succeeds, `Python.Runtime.dll` + `ClrLoader.dll` ship in-wheel, no config
   files needed, `CoreCLR` fallback correctly dormant without a `dotnet` SDK,
   `CookieManager` (incl. `IsHttpOnly`) reachable, `window.get_cookies()`
   already returns HttpOnly cookies through it. No pin changes, no env vars,
   no direct `clr` usage recommended: the solver's three-call pywebview surface
   (`create_window`/`get_cookies`/`evaluate_js`) covers everything, and raw CLR
   would couple the solver to pywebview's private `CoreWebView2` lifecycle (§3
   caveat). If the doc must say one thing: **leave this stack alone.**
2. **If the desktop solver ever "just times out", check for the silent MSHTML
   downgrade first — one env var, zero code. (Verified mechanism; Unverified
   whether it has ever fired here.)** Run the solver once with
   `PYWEBVIEW_LOG=DEBUG` and grep stderr for `Using WinForms / MSHTML` vs
   `Using WinForms / Chromium` (`winforms.py:138/145`), plus
   `get_cookies() is not implemented for this platform`. The registry on this
   machine shows EdgeUpdate clients (evidence §6.3), so chromium is expected —
   but that registration can differ per user machine, and the failure mode is
   completely silent at default log level. (Unverified: needs one on-device
   solver run with debug logging to confirm `renderer='edgechromium'` +
   non-empty cookie jar.)
3. **Consider asserting the renderer in the solver subprocess instead of
   trusting it. (Verified API; Unverified need.)** After `webview.start`, the
   backend exposes `webview.renderer` (`__init__.py`, cf. dep-pywebview.md §0:
   `'edgechromium'` on Windows). A two-line guard —
   `if webview.renderer != 'edgechromium': fail fast with a clear message` —
   converts failure mode #11 from "120 s of empty jars" into an instant,
   actionable error naming WebView2 as the missing piece. Costs nothing when
   healthy. (Unverified: whether `renderer` is readable from the solver's
   `check_cookies` thread context at that point — needs a live run.)
4. **Parked / explicitly not recommended:** forcing `PYTHONNET_RUNTIME=coreclr`
   (no SDK on this machine — §2 — it would convert a working netfx load into
   failure mode #1); pinning `clr-loader`/`cffi` directly in `pyproject.toml`
   (they're correctly transitive via `pythonnet`'s `Requires-Dist`; direct pins
   add maintenance with no behavioural effect); touching pycparser (parse-time
   only, §4); upgrading pythonnet for its own sake (3.2.1 supports our CPython
   3.13; the `<3.16` ceiling only matters if the interpreter moves).

What was checked and found **not** significant: Mono paths (never selected on
win32), `PYTHONNET_*` per-param overrides (no evidence any are set or needed),
`Python.Runtime.deps.json` contents (netstandard2.0 target compatible both
ways — informational only), `ClrLoader.pdb` (debug symbols, inert),
`WebBrowserInterop.x86/x64.dll` (CEF/MSHTML interop, unused on the chromium
path), `pywebview/lib/runtimes/` native WebView2 loader DLLs (pywebview
appends `win-arm64/win-x64/win-x86` to `PATH` at `edgechromium.py:50-51` —
works, no action).
