# Test + dev-tooling stack — complete API reference (installed venv builds)

> Compiled from the installed packages in `.venv/Lib/site-packages/` and the
> repo's own `tests/` + `pyproject.toml`. Every signature below was read from
> the installed source or verified live with `uv run python` from the repo
> root. Suite state at time of writing: **112 tests, all passing**
> (`112 passed in 5.51s`), 16 of them `@pytest.mark.asyncio` (all in
> `tests/test_store.py`), 10 `asyncio.run(...)` call sites across 6 files.

Installed versions (verified via `importlib.metadata`):

| Package | Version | Role |
|---|---|---|
| `pytest` | 9.1.1 | test runner, fixtures, marks |
| `pytest-asyncio` | 1.4.0 | async test/fixture execution |
| `qtpy` | 2.4.3 | Qt binding shim (dev dep for desktop CF solver path) |
| `ruff` | 0.15.20 | linter + formatter (only tool configured; no `[tool.ruff]` section exists) |
| `pywebview` | 6.2.1 | desktop `webview` module used by `src/services/desktop_cf_solver.py` |
| `PyQt6` / `PyQt6-WebEngine` | 6.11.0 | Qt backend behind `qtpy` / `pywebview gui="qt"` |

`pyproject.toml` currently has **no** `[tool.pytest.ini_options]` and **no**
`[tool.ruff]` section — verified by reading the file (it ends at the
`[dependency-groups] dev` block). `asyncio: mode=Mode.STRICT` in the
`--trace-config` header is therefore the plugin default, not a repo choice.

---

## 1. pytest 9.1.1 — fixtures

### 1.1 `@pytest.fixture` signature

Source: `.venv/Lib/site-packages/_pytest/fixtures.py`, function `fixture`:

```python
def fixture(
    fixture_function=None, *,
    scope="function",          # "function"|"class"|"module"|"package"|"session"
                               #  or callable (fixture_name, config) -> scope str
    params=None,               # iterable -> fixture runs once per param, value at request.param
    autouse=False,             # True -> active for every test that can see it
    ids=None,                  # sequence | callable, test-id labels for params
    name=None,                 # fixture name override (default: function name)
)
```

Semantics verified in the docstring: `return` gives the value; `yield`
splits setup/teardown (code after `yield` always runs, must yield exactly
once). `request.param` exists only on parametrized fixtures. Higher scopes
require all their dependencies to have equal-or-wider scope (a
`session` fixture cannot take a `function` fixture — pytest raises
`ScopeMismatch` at setup).

Our suite's only declared fixture (`tests/test_store.py:24`):

```python
@pytest.fixture          # function scope (default), no params, no autouse
def store():
    return JsonStore(filename=f"test-{next(_seq)}.json")
```

Each of the 16 async tests in that file gets a fresh `JsonStore` with a
unique filename; `test_records_survive_reload_isolated` skips the fixture
and builds its own instance instead.

### 1.2 Scope ladder and what each means here

| Scope | Lifetime | Use in this repo |
|---|---|---|
| `function` (default) | one test | `store` fixture; every `tmp_path` (see §4) |
| `class` | one test class | unused — suite has no test classes |
| `module` | one file | unused |
| `package` | one package dir | unused |
| `session` | whole run | `tmp_path_factory`, `pytestconfig`, `event_loop_policy`, `_asyncio_loop_factory` (all built-in, see below) |

Dynamic scope (callable form) is supported by the installed build
(`scope: ScopeName | Callable[[str, Config], ScopeName]`) but unused here.

### 1.3 `@pytest.mark.parametrize`

Registered marker text (`uv run pytest --markers`): *"call a test function
multiple times passing in different arguments in turn. argvalues generally
needs to be a list of values if argnames specifies only one name or a list
of tuples of values if argnames specifies multiple names."* Signature is
`(*args, **kwargs)` — i.e. `parametrize(argnames, argvalues, indirect=...,
ids=..., scope=...)`.

**Unused in the suite** — grep for `parametrize|usefixtures|pytestmark|
autouse|scope=` across `tests/*.py` returns zero hits. Where the suite
repeats cases (e.g. `test_wp_providers.py` AnimeOut/Kusonime cases, theme
round-trips) it uses plain separate `def test_...` functions and module
constants instead.

### 1.4 Marks registry relevant to the suite

From `uv run pytest --markers` (installed build):

- `@pytest.mark.asyncio` — *"mark the test as a coroutine, it will be run
  using an asyncio event loop"* (owned by pytest-asyncio, §2).
- `@pytest.mark.skip(reason=None)`, `@pytest.mark.skipif(condition, ...,
  reason=...)`, `@pytest.mark.xfail(..., reason=..., run=True, raises=None,
  strict=...)` — **unused** (only hit is the English word "skipped" in a
  comment in `test_store.py:223`).
- `@pytest.mark.parametrize(...)`, `@pytest.mark.usefixtures(...)`,
  `@pytest.mark.filterwarnings(...)` — available, **unused**.
- Unknown marks warn/error only under `strict_markers`; without that ini
  flag (our case) a typo'd mark is silently accepted.

### 1.5 conftest.py mechanics

`tests/conftest.py` is the entire conftest (5 lines — inserts `src/` onto
`sys.path`). Verified behavior from `--trace-config`:

- `tests/conftest.py` is registered as a plugin; `rootdir` is the repo
  root (`C:\Users\nwoki\ad-extensions\sources\animepahe-tv`).
- Discovery order: `rootdir/conftest.py` (absent) → `tests/conftest.py` →
  test modules. Fixtures defined in `tests/conftest.py` would be visible to
  the whole `tests/` tree; fixtures defined inside a `test_*.py` are local
  to that module only (hence `store` exists only for `test_store.py`).
- There is **no root `conftest.py`** and no `pytest.ini`/`tox.ini`/`setup.cfg`
  — `pyproject.toml` is the only config source, and it has no
  `[tool.pytest.ini_options]`, so `inifile` is unset and all ini values are
  plugin defaults.
- Two test modules also do their own `sys.path.insert` of `src/`
  (`test_wp_providers.py`, `test_cf_overlay.py`); the rest rely on the
  conftest insertion.

---

## 2. pytest core ini options the suite cares about

Because there is no `[tool.pytest.ini_options]`, these are all at their
installed defaults. The ones worth knowing:

- `asyncio_mode` — plugin-registered, default `"strict"` (§2.1).
- `asyncio_default_test_loop_scope` — default `"function"`.
- `asyncio_default_fixture_loop_scope` — default `None` (unset; on first
  configure the plugin emits `PytestDeprecationWarning:
  _DEFAULT_FIXTURE_LOOP_SCOPE_UNSET` — visible in `--trace-config` output
  as `asyncio_default_fixture_loop_scope=None`).
- `markers`, `filterwarnings`, `log_cli`, `log_level`, `addopts`,
  `testpaths`, `python_files` — all pytest-core ini keys, all unset here.
  `python_files` defaults to `test_*.py *_test.py`, which is how the 19
  `test_*.py` files are collected (112 items).

---

## 3. Built-in fixtures actually used (with verified signatures)

### `tmp_path: Path` — function-scoped temp dir

Source: `_pytest/tmpdir.py:291`. Docstring: *"Return a temporary directory
(as `pathlib.Path`) which is unique to each test function invocation."*
Session companion: `tmp_path_factory: TempPathFactory` (`_pytest/tmpdir.py:
276`, session scope). Used in `test_downloads.py:66`,
`test_store.py:196,253,274`, `test_theme_adaptive.py:41` — always paired
with `monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))` plus
`(tmp_path / "animepahe").mkdir(...)` because the store resolves its data
dir from that env var.

### `monkeypatch` — function-scoped undo log

Source: `_pytest/monkeypatch.py:36`; class `MonkeyPatch` methods (signatures
verified live):

```python
setattr(target, name, value=..., raising=True)
delattr(target, name=..., raising=True)
setenv(name: str, value: str, prepend: str | None = None)
delenv(name, raising=True)
setitem(dic, name, value) / delitem(dic, name, raising=True)
chdir(path) / syspath_prepend(path)
context() -> Generator[MonkeyPatch]   # manual scoped use
```

All changes auto-undo at test teardown. Suite usage: `setenv` (storage-dir
isolation, above) and `setattr("services.store._data_dir", lambda:
str(tmp_path), raising=False)` in `test_theme_adaptive.py:43`.

### `capsys` / `capfd` — stdout/stderr capture

Source: `_pytest/capture.py:1007` (`capsys`), `:1098` (`capfd`). Both yield
a `CaptureFixture` with exactly three public methods (verified live):
`readouterr()`, `close()`, `disabled()`. `capsys` captures Python-level
`sys.stdout/err`; `capfd` captures OS file descriptors. **Unused in the
suite** — no test reads process output.

### `caplog` — log-record capture

Source: `_pytest/logging.py:611`. Yields `LogCaptureFixture` with (verified
live): `records`, `record_tuples`, `messages`, `text`, `handler`,
`get_records(when)`, `set_level(level, logger=None)`, `at_level(level,
logger=None)`, `filtering`, `clear()`. **Unused in the suite** — the logger
tests (`test_logger.py`) assert on handler/formatter objects directly, not
on captured emission.

### `recwarn`, `pytestconfig`, `request`

`recwarn` (`_pytest/recwarn.py:37`, yields `WarningsRecorder`), `pytestconfig:
Config` (session, `_pytest/fixtures.py:1564`), and the `request:
FixtureRequest` object (`.param`, `.config`, `.getfixturevalue(name)`,
`.addfinalizer(fn)`) are all available and **unused** outside the plugin
internals.

---

## 4. pytest-asyncio 1.4.0 — the complete API as installed

Plugin file: `.venv/Lib/site-packages/pytest_asyncio/plugin.py`
(`__init__.py` re-exports only `fixture`, `is_async_test`, `version`).
Registered per `--trace-config`: `asyncio: mode=Mode.STRICT, debug=False,
asyncio_default_fixture_loop_scope=None,
asyncio_default_test_loop_scope=function`.

### 4.1 `asyncio_mode`: strict (default) vs auto

Source: `pytest_addoption` (`plugin.py:108`) + `_get_asyncio_mode`
(`plugin.py:222`) + `ASYNCIO_MODE_HELP`:

```python
parser.addini("asyncio_mode", default="strict")   # --asyncio-mode overrides ini
```

- **strict** (current effective mode): only items carrying the `asyncio`
  marker become `PytestAsyncioFunction`s. `_resolve_asyncio_marker`
  (`plugin.py:677`) returns the marker if present, else `None` — an
  unmarked `async def test_...` is **not** run as async (it would fail/skip
  as an un-awaited coroutine).
- **auto**: `_resolve_asyncio_marker` adds the `asyncio` marker to every
  collected coroutine/hypothesis async test automatically. Help text:
  *"'auto' - for automatically handling all async functions by the plugin;
  'strict' - for autoprocessing disabling (useful if different async
  frameworks should be tested together...)"*.
- Resolution order: `--asyncio-mode` CLI flag wins; else the
  `asyncio_mode` ini value; invalid values raise `pytest.UsageError`
  listing valid modes (`Mode` enum: `AUTO`/`STRICT`).

The suite runs in strict mode with 16 explicit `@pytest.mark.asyncio`
markers — consistent and correct; no unmarked async tests exist.

### 4.2 `@pytest.mark.asyncio` kwargs — `loop_scope`, `loop_factories`

Source: `_parse_asyncio_marker` + `_validate_asyncio_marker`
(`plugin.py:969-1006`):

```python
@pytest.mark.asyncio(loop_scope="function", loop_factories=["..."])
# loop_scope in {"function","class","module","package","session"}
# legacy kwarg `scope=` still read but emits PytestDeprecationWarning
#   (_MARKER_SCOPE_KWARG_DEPRECATION_WARNING); passing both raises UsageError
# loop_factories must be a non-empty sequence of strings (hook impl names);
#   anything else raises ValueError(_INVALID_LOOP_FACTORIES_KWARG)
```

Item classes (`plugin.py:506+`): collected `Function`s are converted by the
`pytest_pycollect_makeitem_convert_async_functions_to_subclass` hookwrapper
into `Coroutine` (coroutine fns), `AsyncStaticMethod`, `AsyncHypothesisTest`,
or `AsyncGenerator` (async-gen tests are collected then forced to
`xfail(run=False)` with a `PytestCollectionWarning` — async generator tests
are **not supported**). Each item's `_loop_scope` is the closest marker's
`loop_scope`, else the `asyncio_default_test_loop_scope` ini (`"function"`).
`runtest()` runs the coroutine via `_synchronize_coroutine` inside the
`_{scope}_scoped_runner` fixture's `asyncio.Runner`; `setup()` appends that
runner fixture to `fixturenames`.

Module/class scope interaction: `@pytest.mark.asyncio(loop_scope="module")`
on a test (or class) makes all such tests in the module share one
`asyncio.Runner`/loop via the `_module_scoped_runner` fixture — the
mechanism is per-item `fixturenames` injection, so mixing scopes in one
module is allowed (each item pulls its own runner). The suite uses no
`loop_scope` kwarg anywhere — all 16 async tests are function-scoped loops.

### 4.3 `event_loop` fixture — REMOVED; `event_loop_policy` deprecated

Verified by grepping the installed `plugin.py` (function/class index,
§“CHECK event_loop fixture”): **there is no `event_loop` fixture** in 1.4.0
— only these async-related fixtures exist:

```python
@pytest.fixture(scope="session", autouse=True)
def event_loop_policy() -> AbstractEventLoopPolicy: ...   # plugin.py:1076

@pytest.fixture(scope="session")
def _asyncio_loop_factory(request) -> LoopFactory | None: ...  # plugin.py:1071

# per-scope runners, created in a loop: _function_scoped_runner,
# _class_scoped_runner, _module_scoped_runner, _package_scoped_runner,
# _session_scoped_runner  (plugin.py:1023 + for scope in Scope loop)

@pytest.fixture
def unused_tcp_port() -> int: ...            # plugin.py:1094
@pytest.fixture
def unused_udp_port() -> int: ...            # plugin.py:1099
@pytest.fixture(scope="session")
def unused_tcp_port_factory() -> Callable[[], int]: ...  # plugin.py:1104
@pytest.fixture(scope="session")
def unused_udp_port_factory() -> Callable[[], int]: ...  # plugin.py:1123
```

Policy changes that matter:

- Overriding the `event_loop_policy` fixture (the pre-1.x customization
  point) now emits `PytestDeprecationWarning
  (_EVENT_LOOP_POLICY_FIXTURE_DEPRECATION_WARNING)` from the
  `pytest_fixture_setup` hook (`plugin.py:911`) — *"Use the
  `pytest_asyncio_loop_factories` hook to customize event loop creation."*
  The suite does not override it (verified: no `event_loop` reference in
  `tests/`).
- `asyncio.Runner` (stdlib) is the execution engine: `_scoped_runner`
  enters `Runner(debug=..., loop_factory=_asyncio_loop_factory)` under a
  temporary policy (`plugin.py:1023-1068`). Closing the loop inside a test
  triggers `_RUNNER_TEARDOWN_WARNING` (RuntimeWarning, future error).
- Strict-mode guard (`pytest_pyfunc_call`, `plugin.py:848`): an async test
  requesting a plain-`@pytest.fixture` async fixture warns
  `PytestDeprecationWarning: ... requested async @pytest.fixture ... in
  strict mode. You might want to use @pytest_asyncio.fixture ... This will
  become an error in future versions`. Verified live: `test_store.py` passes
  even with `-W error::pytest.PytestDeprecationWarning` (18 passed) because
  its `store` fixture is **sync** — the guard does not fire. A sync fixture
  feeding an async test is fully supported in strict mode.

### 4.4 `pytest_asyncio.fixture` signature

Source: `plugin.py:151` / re-exported at package root:

```python
@pytest_asyncio.fixture(fixture_function=None, *, loop_scope=None, **kwargs)
# loop_scope: "function"|"class"|"module"|"package"|"session"|None
#   (None -> asyncio_default_fixture_loop_scope ini -> else fixture scope)
# **kwargs forwarded to pytest.fixture (scope/params/autouse/ids/name)
```

`pytest_fixture_setup` (`plugin.py:911`) wraps async fixtures to run
setup/teardown inside the matching `_{loop_scope}_scoped_runner`, and holds
the runner open past fixture teardown via `addfinalizer`. **Unused in the
suite** — the only fixture is sync, which is why the suite is immune to the
strict-mode async-fixture warning above.

### 4.5 `asyncio.run(...)` pattern used by the suite

10 call sites (sync tests driving coroutines manually):
`test_downloads.py:96`, `test_store.py:271,289`,
`test_house_layer.py:65,73,87`, `test_player_error_card.py:158,205`,
`test_wp_providers.py:107` (via local `_run(coro)` helper),
`test_theme_adaptive.py:52`. Each creates a **fresh event loop per call**,
independent of the plugin's runners — no interaction with
`asyncio_mode`, `loop_scope`, or the deprecation paths. It works in both
modes and is the reason most provider/service tests need no marker at all.

---

## 5. What `pyproject.toml` should set — recommended `[tool.pytest.ini_options]`

The repo has none; the following pins current behavior explicitly so a
pytest-asyncio upgrade cannot silently change the suite. Every key verified
as a real ini/option in the installed builds (`pytest_addoption` for the
`asyncio_*` keys; pytest core for the rest):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "strict"
asyncio_default_test_loop_scope = "function"
asyncio_default_fixture_loop_scope = "function"
markers = [
    "asyncio: run the test in an asyncio event loop (pytest-asyncio, strict mode)",
]
filterwarnings = [
    "error::pytest.PytestDeprecationWarning",
]
log_cli = false
```

Why each line:

- `testpaths`: collection root is unambiguous (today bare `pytest` collects
  from rootdir anyway; this protects against stray `test_*.py` elsewhere).
- `asyncio_mode = "strict"`: documents the mode the 16 markers assume;
  without it a future plugin default flip to `auto` would silently start
  running any unmarked coroutine — behavior change with no diff.
- `asyncio_default_test_loop_scope = "function"`: pins the loop-per-test
  isolation the store tests rely on (each `JsonStore` test gets a fresh
  loop; verified default is already `"function"`).
- `asyncio_default_fixture_loop_scope = "function"`: **fixes a real
  latent warning** — the ini is currently unset (`None` in `--trace-config`)
  and `pytest_configure` emits `PytestDeprecationWarning
  (_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET)` on every run. Setting it silences the
  warning at the source and matches the sync-fixture reality. (No async
  fixtures exist yet; when one is added this decides its loop sharing.)
- `markers`: registers `asyncio` so `strict_markers`-style typos are caught
  if that flag is ever added; harmless documentation today.
- `filterwarnings = error::pytest.PytestDeprecationWarning`: verified live —
  the suite passes with it (`test_store.py`: 18 passed under
  `-W error::pytest.PytestDeprecationWarning`), so promoting the
  strict-mode async-fixture warning and the loop-scope warnings to errors
  locks the suite against the exact patterns pytest-asyncio says *"will
  become an error in future versions"*.
- `log_cli = false`: explicit no-op today (no `caplog` usage); keeps CI
  output stable if logging tests are added later.

Deliberately **not** recommended: `asyncio_mode = "auto"` (would make the 16
explicit markers redundant and auto-run any future stray coroutine, hiding
missing-marker bugs); `addopts = ["-W", ...]` (duplicates `filterwarnings`);
`log_cli = true` (no test asserts on log output — `test_logger.py` checks
handler objects directly).

---

## 6. qtpy 2.4.3 — Qt abstraction and what the desktop solver path needs

### 6.1 How qtpy resolves a binding (installed `__init__.py`)

`qtpy.API_NAME` verified live as `"PyQt6"`. Resolution order from the
installed source docstring + code: an already-imported binding wins;
otherwise the first importable of `PyQt5 → PySide2 → PyQt6 → PySide6`,
overridable with the `QT_API` env var (`pyqt6`/`pyside6`/…; invalid values
raise `PythonQtValueError`). Only `PyQt6 6.11.0` is installed here
(`PySide6` → `NOT INSTALLED`), so `PyQt6` is selected deterministically.
Error types shipped: `PythonQtError`, `PythonQtWarning`,
`QtBindingsNotFoundError` (no binding), `QtModuleNotFoundError` and its
`...NotInOSError` / `...NotInQtVersionError` subclasses.

### 6.2 What the repo's desktop CF path actually imports

`src/services/desktop_cf_solver.py` imports **only `webview` (pywebview
6.2.1)** — `import webview`, `webview.create_window(...)`,
`webview.start(check_cookies, window)`. No `qtpy`, `PyQt`, or `PySide`
import exists anywhere in `src/` or `tests/` (grep for
`qtpy|PyQt|PySide` hits only `webview_solver.py`'s docstring-free body —
actually zero hits outside this report; the single `webview` consumer is
`desktop_cf_solver.py`).

The Qt connection is indirect: `webview/__init__.py:190` documents
`gui="qt"` as a `create_window`/`start` backend choice, and the venv
provides the Qt stack that backend needs — `qtpy 2.4.3` (shim, resolves to
`PyQt6`), `PyQt6 6.11.0`, `PyQt6-WebEngine 6.11.0`. Verified live:
`from qtpy import QtWebEngineWidgets, QtWebEngineCore` imports cleanly.
So `qtpy` is a **transitive dev-environment dependency**: it is what makes
`webview.start(..., gui="qt")` viable on a dev desktop for manually driving
the Cloudflare Turnstile page that `desktop_cf_solver.check_cookies` polls
(`/120 × 1s/` loop waiting for `cf_clearance` + target-site markers in
`is_challenge_complete`). The shipped app path (`webview_solver.py`) uses
Flet/`flet-webview`/Android jnius instead — no Qt involved at runtime.

No test touches Qt, `webview`, or either solver module (no hits for
`webview|desktop_cf|WebViewSolver` in `tests/`), so qtpy needs no pytest
configuration — it only needs to stay in the `dev` dependency group.

---

## 7. ruff 0.15.20 — config relevant to this repo

### 7.1 Current state: no `[tool.ruff]`, defaults apply

`uv run ruff check --show-settings` resolves against
`pyproject.toml` with **zero ruff keys**, so these defaults govern:

- `line-length = 88` (also `pycodestyle.max_line_length = 88`).
- Default selected rules = **E4/E7/E9 subset + F** (verbatim from resolved
  settings: `E401,E402,E701,E702,E703,E711,E712,E713,E714,E721,E722,E731,
  E741,E742,E743,E902` + the full `F401–F901` pyflakes set). Notably **not**
  enabled: `E501` (line length unenforced!), `I` (import sorting), `UP`
  (pyupgrade), `B` (bugbear), `ASYNC`, `S` (bandit), `PT` (flake8-pytest-style).
- `target-version`: unset → inferred from `requires-python = ">=3.13"`.
- Formatter: default style (88 cols, double quotes); `ruff format --check`
  reports **36 files would be reformatted**, i.e. the tree is not
  format-clean today.

### 7.2 `ruff check src tests` today: 29 errors, all F-category

Bucketed from the live run (`Found 29 errors`, 24 auto-fixable):

| Rule | Count | Examples |
|---|---|---|
| `F401` unused import | ~14 | `asyncio` ×5 (async tests that grew `asyncio.run` elsewhere), `time`, `shutil`, `AnimeOutProvider`, `AppColors`, `AppState`, `SharedServices`, `flet.controls.context` |
| `F811` redefinition of unused | ~4 | `asyncio` re-imports, `card_focus_scale/button_style`, `attach_focus_zoom` |
| `F821` undefined name | 3 | `episode_title`, bare `asyncio`, `KWIK_USER_AGENT` — **real bugs or dead code paths, not style** |
| `F841` unused local | 2 | `log_count`, `episodes` |
| `F541` empty f-string placeholder | 1 | one f-string without `{}` |

The three `F821`s deserve human triage first — undefined names are either
broken references or leftovers guarding dead branches.

### 7.3 Minimal `[tool.ruff]` worth adding (all keys verified against 0.15.20 settings schema)

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "PT"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]
```

Rationale: `E` (keep `E501` off — the codebase has long URL/table literals;
formatter handles width), `I` (import order — test files currently mix
`sys.path` hacks with imports; `E402` already tolerates them but sorting
helps), `UP` (repo is 3.13-only; flags `typing.Optional`, of which 2 unused
imports already exist), `B`/`ASYNC` (cheap bug catchers for the async
provider code), `PT` (pytest-style: would flag `asyncio.run` in tests as
`PT...` candidates for native async tests — advisory, see §8.4).
`S101` for tests pre-allows `assert`s if `S` is ever added (not selected
above — asserts are the suite's only oracle, so `S101` must never fire on
`tests/`).

---

## 8. App improvement opportunities

Concrete, evidence-backed ways the pytest stack can improve the suite. Each
item cites the installed source + signature verified above; speculation is
quarantined in §8.6.

### 8.1 Add the `[tool.pytest.ini_options]` block from §5 — kills a real warning, pins two silent defaults

Evidence: `--trace-config` prints
`asyncio_default_fixture_loop_scope=None`, and `pytest_configure`
(`plugin.py:295`) warns `PytestDeprecationWarning(
_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET)` whenever that ini is unset — i.e. every
current run emits a deprecation warning the repo never sees because warnings
are not errors. Setting `asyncio_default_fixture_loop_scope = "function"`
removes it at the source. `asyncio_mode = "strict"` + the two scope pins
turn three today-silent plugin defaults into reviewed choices, so a
pytest-asyncio upgrade (e.g. a future default-mode flip) cannot change what
the 16 marked tests do without a diff. Cost: one TOML block, zero test
changes; verified the suite already satisfies it (§4.3 live check).

### 8.2 Promote `PytestDeprecationWarning` to an error — the suite already passes under it

Evidence: `pytest_fixture_setup` (`plugin.py:911`) and the marker parser
(`plugin.py:969`) emit `PytestDeprecationWarning` for exactly the patterns
the plugin announces as *"will become an error in future versions"*
(strict-mode plain-async fixtures; `scope=` kwarg; `event_loop_policy`
override). Live check: `pytest tests/test_store.py -W
error::pytest.PytestDeprecationWarning` → **18 passed**, because the only
fixture (`store`, `test_store.py:24`) is sync and no marker uses `scope=`.
Adding `filterwarnings = ["error::pytest.PytestDeprecationWarning"]` therefore
converts three future breaking changes into immediate, local failures at
zero current cost.

### 8.3 Triage the 3 `F821 undefined-name` ruff hits — probable dead code or real bugs

Evidence: live `ruff check src tests` reports `F821 Undefined name
episode_title`, `F821 Undefined name asyncio`, `F821 Undefined name
KWIK_USER_AGENT` (rule `F821` from the default-selected pyflakes set,
§7.2). Undefined names are not style — each is either a `NameError` waiting
for a code path to execute or a leftover reference. Recommended action:
locate each, either wire the missing import/definition or delete the dead
branch, then re-run `ruff check`. The ~14 `F401`s and 4 `F811`s in the same
report are safe auto-fixes (`ruff check --fix`) afterwards.

### 8.4 Convert the 10 `asyncio.run(...)` call sites to native `@pytest.mark.asyncio` tests

Evidence: strict mode runs any marked coroutine via the
`_function_scoped_runner` (`plugin.py:1023`, `Coroutine.runtest`,
`plugin.py:602`), and `pytest_pyfunc_call`'s strict guard only fires for
*async fixtures* (`plugin.py:848-880`) — async tests with sync fixtures are
fully supported, and the suite's only fixture is sync. The 10 sync wrappers
(`test_downloads.py:96`, `test_store.py:271,289`,
`test_house_layer.py:65,73,87`, `test_player_error_card.py:158,205`,
`test_wp_providers.py:107`, `test_theme_adaptive.py:52`) each spin a fresh
loop per call; as native async tests they would share the per-test runner
loop, get proper async teardown, and stop hiding coroutine errors behind a
sync frame. The `PT` ruff set (§7.3) flags exactly this pattern once
enabled. Migration is mechanical (`def test_...` → `async def test_...` +
marker, drop the `asyncio.run` shell) and keeps strict mode.

### 8.5 Enable `ruff` rule sets `I`, `UP`, `B`, `ASYNC`, `PT` for `src/` — matched to real code shapes

Evidence: rule codes verified in the resolved `--show-settings` rule list
(default = E4/E7/E9+F only); repo facts they map to: `sys.path` + import
mixing in test modules (`I`); `requires-python >= 3.13` with 2 stale
`typing.Optional` imports (`UP`); async provider code with manual loop
handling (`B`, `ASYNC`); 10 `asyncio.run`-in-test wrappers (`PT`). The
`[tool.ruff]` sketch in §7.3 selects exactly these while keeping `E501` off
(long URL/table literals are load-bearing) and pre-ignoring `S101` for
tests. First run will produce new findings — budget a triage pass, mostly
auto-fixable (`I`, `UP`) plus manual review (`B`, `ASYNC`).

### 8.6 Unverified — checked but not recommended (no speculation adopted)

- `asyncio_mode = "auto"`: would delete the 16 markers, but `_resolve_asyncio_marker` (`plugin.py:677`) would then silently async-run any future unmarked coroutine — strictly weaker typo protection than today's strict mode. Checked, rejected.
- `caplog`/`capsys` adoption for `test_logger.py`: fixtures verified available (`LogCaptureFixture` API, §3) but the tests assert on handler/formatter objects directly and pass; no failing behavior motivates the rewrite. Checked, not proposed.
- `parametrize` for provider tables: marker verified available and suite uses none; the table-style tests pass as written and splitting them buys sharding granularity only, which the 5.5 s suite does not need. Checked, not proposed.
- Qt/`webview` test coverage: `qtpy` resolves to `PyQt6` and `QtWebEngineWidgets/Core` import cleanly (§6), but no test imports either solver and `desktop_cf_solver` blocks on a live challenge page + GUI event loop — no pytest-stack change makes that unit-testable without a harness that does not exist. Checked, not proposed.
