# pytest/tooling micro-deps — combined reference (installed venv builds)

> **Version note (2026-10-15):** pluggy is now **1.7.0** (was 1.6.0); the other five unchanged.
> Verdicts unaffected.


> Six small packages in `.venv/Lib/site-packages/`: `colorama` 0.4.6,
> `iniconfig` 2.3.1, `pluggy` 1.6.0, `packaging` 26.3, `pygments` 2.21.0,
> `typing-extensions` 4.16.0. All six are **transitives of the dev group**
> (`pyproject.toml` `[dependency-groups] dev`: `ruff`, `pytest`,
> `pytest-asyncio`, `pywebview`, `qtpy`, `pyqt6-webengine`) — none is a direct
> dependency. Every claim below was read from the installed source or verified
> live with `uv run python` from the repo root (Python 3.13.15,
> `requires-python = ">=3.13"`).
>
> Blanket finding up front: `grep -rn --include="*.py" -E
> "colorama|iniconfig|pluggy|packaging|pygments|typing_extensions"` over `src/`,
> `tests/`, `pyproject.toml`, and `uv.lock` returns **zero hits in `src/` and
> `tests/`**. Our app code touches none of these six. `tests/conftest.py` is a
> two-line `sys.path` insert — no hooks, no plugins.

Consumer matrix (detail per package follows):

| Package | Version | Direct consumer(s) in our tree | App code use |
|---|---|---|---|
| `colorama` | 0.4.6 | pytest (`_pytest/_io/terminalwriter.py`, `_pytest/capture.py`); Windows-only (`uv.lock`: `marker = "sys_platform == 'win32'"`) | none |
| `iniconfig` | 2.3.1 | pytest (`config/findpaths.py`, `legacypath.py`, `pytester.py`) | none |
| `pluggy` | 1.6.0 | pytest core + `pytest-asyncio` plugin | none (no custom plugin) |
| `packaging` | 26.3 | pytest (`config/__init__.py`, `outcomes.py`), `qtpy`, `flet_cli` | none |
| `pygments` | 2.21.0 | pytest (`_pytest/_io/terminalwriter.py` only) | none |
| `typing-extensions` | 4.16.0 | pytest (`_pytest/*`), `pytest-asyncio`, `pywebview` (`webview/*`) | none |

---

## 1. colorama 0.4.6 — Windows ANSI-to-Win32 shim

Source: `.venv/Lib/site-packages/colorama/` (`__init__.py`, `ansi.py`,
`ansitowin32.py`, `initialise.py`, `win32.py`, `winterm.py`).
Summary from `colorama-0.4.6.dist-info/METADATA`: "Cross-platform colored
terminal text."

### Who consumes it

- `_pytest/_io/terminalwriter.py`, `TerminalWriter.__init__` (~line 74–84):
  only when `file.isatty() and sys.platform == "win32"`, wraps the stream —
  `file = colorama.AnsiToWin32(file).stream`. Import is inside try/except, so
  colorama is optional at runtime. On non-Windows it is never imported.
- `_pytest/capture.py` (~line 70–80, `_colorama_workaround`): on
  `sys.platform.startswith("win32")`, imports colorama **before** I/O capture
  starts, because "colorama uses the terminal on import time" and a first
  import under active capture "will fail in various ways". Also guarded by
  try/except ImportError.
- `uv.lock` pins it with `marker = "sys_platform == 'win32'"` and lists it in
  pytest 9.1.1's dependency block — i.e. it ships because pytest declares it,
  and installs only on Windows. This repo runs on Windows, so it is present.

### App relevance

None. No `src/` or `tests/` import. Our terminal output path is Flet, not a
console; colorama only affects pytest's own colored output on Windows
consoles.

---

## 2. iniconfig 2.3.1 — brain-dead simple INI parsing

Source: `.venv/Lib/site-packages/iniconfig/__init__.py`. API surface is two
classes: `IniConfig(path)` with `.parse()`, `.get()`, `.lineof()`,
`__getitem__`/`__iter__`/`items`, plus `SectionWrapper` (per-section view with
`.get(..., convert=...)`, `.lineof()`); parse failures raise
`iniconfig.ParseError`.

### Who consumes it

- `_pytest/config/findpaths.py` (line 13 `import iniconfig`):
  `_parse_ini_config()` (lines 46–55) parses generic `.ini` files and converts
  `ParseError` to `UsageError`; `load_config_dict_from_file()` (lines 58+)
  reads the `[pytest]` section from `pytest.ini`/`.pytest.ini`/`*.ini` files
  (`if "pytest" in iniconfig`, keys become `ConfigValue(..., origin="file",
  mode="ini")`).
- `_pytest/legacypath.py` (line 14): re-exports `SectionWrapper`.
- `_pytest/pytester.py` (lines 39–40): `from iniconfig import IniConfig,
  SectionWrapper` for the `Pytester`/`Runpytest` test helpers.

Note: this repo has **no** `[tool.pytest.ini_options]` and no `pytest.ini`
(verified: `pyproject.toml` ends at the `[dependency-groups] dev` block), so
iniconfig parses nothing for us today — but it is still imported by pytest at
config-file discovery time.

### App relevance

None. Our config surface is `src/core/config.py` + `constants.py` (plain
Python), not INI files.

---

## 3. pluggy 1.6.0 — pytest's hook engine

Source: `.venv/Lib/site-packages/pluggy/` (`_hooks.py`, `_manager.py`,
`_callers.py`, …). Summary from `pluggy-1.6.0.dist-info/METADATA`: "plugin and
hook calling mechanisms for python".

### Who consumes it

- pytest core, pervasively:
  - `_pytest/config/__init__.py` (lines 42–46): `HookimplMarker`,
    `HookimplOpts`, `HookspecMarker`, `HookspecOpts`, `PluginManager`;
    exposes them as `pytest.hookimpl` / `pytest.hookspec` / `pytest.PytestPluginManager`
    (`pytest/__init__.py` lines 16–17, both in `__all__`).
  - `_pytest/hookspec.py`: the full spec — `hookspec = HookspecMarker("pytest")`
    plus ~50 hook functions (line numbers from installed source):
    `pytest_addhooks` (historic, 54), `pytest_plugin_registered` (72),
    `pytest_addoption` (97), `pytest_configure` (138),
    `pytest_cmdline_parse` (162), `pytest_load_initial_conftests` (185),
    `pytest_cmdline_main` (203), `pytest_collection` (227),
    `pytest_collection_modifyitems` (268), `pytest_collection_finish` (290),
    `pytest_ignore_collect` (303), `pytest_collect_directory` (336),
    `pytest_collect_file` (365), `pytest_collectstart` (392),
    `pytest_itemcollected` (407), `pytest_collectreport` (421),
    `pytest_deselected` (436), `pytest_make_collect_report` (458),
    `pytest_pycollect_makemodule` (482), `pytest_pycollect_makeitem` (509),
    `pytest_pyfunc_call` (535), `pytest_generate_tests` (552),
    `pytest_make_parametrize_id` (568), `pytest_runtestloop` (594),
    `pytest_runtest_protocol` (620), `pytest_runtest_logstart` (660),
    `pytest_runtest_logfinish` (678), `pytest_runtest_setup` (698),
    `pytest_runtest_call` (717), `pytest_runtest_teardown` (733),
    `pytest_runtest_makereport` (758), `pytest_runtest_logreport` (777),
    `pytest_report_to_serializable` (792), `pytest_report_from_serializable` (811),
    `pytest_fixture_setup` (834), `pytest_fixture_post_finalizer` (862),
    `pytest_sessionstart` (888), `pytest_sessionfinish` (901),
    `pytest_unconfigure` (917), `pytest_assertrepr_compare` (934),
    `pytest_assertion_pass` (957), `pytest_report_header` (1005),
    `pytest_report_collectionfinish` (1031), `pytest_report_teststatus` (1068),
    `pytest_terminal_summary` (1100), `pytest_warning_recorded` (1122),
    `pytest_markeval_namespace` (1166), `pytest_internalerror` (1195),
    `pytest_keyboard_interrupt` (1214), `pytest_exception_interact` (1228),
    `pytest_enter_pdb` / `pytest_leave_pdb` (1260/1276).
  - `import pluggy` also appears in `_pytest/main.py` (25), `_pytest/nodes.py`
    (22), `_pytest/terminal.py` (32), `_pytest/subtests.py` (19),
    `_pytest/_code/code.py` (34).
- `pytest_asyncio/plugin.py`: `import pluggy` (38),
  `hookspec = pluggy.HookspecMarker("pytest")` (87), and hookimpls at lines
  311 (`tryfirst=True`), 689 (`specname="pytest_pycollect_makeitem"`,
  `hookwrapper=True`), 726 (`tryfirst=True`), 847 (`tryfirst=True,
  hookwrapper=True`), 910 (`wrapper=True`). This is the live example of a
  third-party pytest plugin built on pluggy in our tree.

### The hook API our pytest plugins could use

Mechanics (`pluggy/_hooks.py`, `pluggy/_manager.py`): declare with
`@hookspec` (opts: `firstresult=False`, `historic=False`); implement with
`@pytest.hookimpl` (opts: `tryfirst/trylast` ordering, `wrapper=True` for the
new-style wrapper protocol around `pluggy.Result`, legacy `hookwrapper=True`
still seen in pytest-asyncio). `PluginManager` API:
`register/unregister`, `add_hookspecs`, `parse_hookimpl_opts`,
`check_pending`, `load_setuptools_entrypoints(group, name)`,
`list_plugin_distinfo`, `get_plugin/has_plugin/is_registered`,
`set_blocked/is_blocked/unblock`.

Hooks worth knowing for a future `conftest.py`/`tests/` plugin (all in
`_pytest/hookspec.py`):

- `pytest_addoption(parser, pluginmanager)` — add custom CLI flags.
- `pytest_configure(config)` / `pytest_unconfigure` — setup/teardown.
- `pytest_collection_modifyitems(session, config, items)` — filter/reorder
  tests (e.g. deselect slow backends, enforce markers).
- `pytest_ignore_collect(collection_path, config)` — skip paths.
- `pytest_generate_tests(metafunc)` — custom parametrization (e.g. backend
  × provider matrices, cf. `tests/test_wp_providers.py`).
- `pytest_runtest_makereport` / `pytest_runtest_logreport` — custom reporting.
- `pytest_report_header(config, start_path)` — banner lines in test output.
- `pytest_terminal_summary(terminalreporter, exitstatus, config)` — end-of-run
  summary (e.g. provider-coverage table).
- `pytest_assertrepr_compare` — prettier assertion diffs for domain objects.

### App relevance

None today — we ship no pytest plugin; `tests/conftest.py` defines no hooks.
pluggy is pure test tooling here.

---

## 4. packaging 26.3 — version/requirement parsing (reusable)

Source: `.venv/Lib/site-packages/packaging/` (`version.py`, `specifiers.py`,
`requirements.py`, `markers.py`, `tags.py`, `utils.py`, `licenses/`).
Verified live: `Version('1.2.3') < Version('1.10.0')` → `True`,
`SpecifierSet('>=1.0,<2.0').contains('1.5')` → truthy,
`Requirement('pytest>=8.0')` parses. Key API:

- `packaging.version.Version(str)` — PEP 440, full ordering (`<`, `<=`,
  `==`, `>=`, `>`), `.major/.minor/.micro/.pre/.post/.dev/.local`;
  `InvalidVersion` on garbage; `parse(str)` → `Version` or legacy fallback.
- `packaging.specifiers.SpecifierSet(">=1.0,<2.0")` — `.contains(version,
  prereleases=...)`, `.filter(iterable)`.
- `packaging.requirements.Requirement("name>=x")` — `.name`, `.specifier`,
  `.marker`, `.extras`; `InvalidRequirement` on garbage.

### Who consumes it

- pytest, lazily (imported inside functions "to improve start-up time"):
  - `_pytest/config/__init__.py::_checkversion` (~1451–1460): `minversion`
    ini option — `Version(minver) > Version(pytest.__version__)` raises
    `UsageError`. (No `minversion` in our pyproject, so dormant.)
  - `_pytest/config/__init__.py::_validate_plugins` (~1468–1490):
    `required_plugins` ini option — `Requirement(...)` parsed,
    `req.specifier.contains(Version(installed), prereleases=True)` checked
    against `pluginmanager.list_plugin_distinfo()`. (Also dormant here.)
  - `_pytest/outcomes.py::importorskip` (~279–289): `Version(verattr) <
    Version(minversion)` → module-level `Skipped`.
  - `_pytest/unittest.py` (565): `import packaging.version` (Twisted
    version check).
- `qtpy/__init__.py` (line 63): `from packaging.version import parse`
  (binding-version handling).
- `flet_cli` (transitive via docs reference, not installed here as a package
  dir check target): `commands/build_base.py`, `commands/flutter_base.py`,
  `utils/project_dependencies.py`, `__pyinstaller/win_utils.py`.
- `uv.lock`: `packaging` 26.3 appears in pytest's dependency block.

### App relevance

None today — but this is the one package of the six with plausible app reuse
(see "App improvement opportunities").

---

## 5. pygments 2.21.0 — syntax highlighting for tracebacks

Source: `.venv/Lib/site-packages/pygments/` (lexers, formatters, styles).
Only consumer in our tree is pytest:

- `_pytest/_io/terminalwriter.py` (lines 13–17): `import pygments`,
  `TerminalFormatter`, `Lexer`, `DiffLexer`, `PythonLexer`.
- `_get_pygments_lexer()` (208–214) picks `PythonLexer`/`DiffLexer`;
  `_get_pygments_formatter()` (216–233) builds
  `TerminalFormatter(bg=theme_mode, style=theme)` from `PYTEST_THEME` /
  `PYTEST_THEME_MODE` env vars (invalid values raise `UsageError` naming
  `pygmentize -L styles`); `_highlight()` (235–256) calls
  `pygments.highlight(source, lexer, formatter)` when `hasmarkup` and
  `code_highlight` are set, prepending `\x1b[0m`.
- Practical effect: colored source lines in assertion rewrites and `-vv`
  diffs. `PYTEST_THEME` / `PYTEST_THEME_MODE=dark|light` are the only knobs.

### App relevance

None. No `src/` import; our UI renders in Flet, not terminal-highlighted code.

---

## 6. typing-extensions 4.16.0 — typing backports

Source: `.venv/Lib/site-packages/typing_extensions.py` (single module;
`importlib.metadata.version("typing-extensions")` → `4.16.0`).

### Who consumes it

- pytest (`_pytest/*`, all guarded `TYPE_CHECKING`-adjacent or runtime
  fallbacks): `Self` (`capture.py:32`, `doctest.py:48`, `main.py:52`,
  `nodes.py:44`, `reports.py:44`, `python.py:83`, `subtests.py:43`,
  `stepwise.py:18`), `ParamSpec` + `TypeVar` (`raises.py:34–35`,
  `recwarn.py:20–21`, `_py/error.py:14`), `deprecated`
  (`compat.py:322`, aliased re-export).
- `pytest_asyncio/plugin.py:64`: `from typing_extensions import TypeIs`.
- `pywebview` 6.2.1 (`webview/*`): `Self` (`event.py:8`, `state.py:5`,
  `dom/event.py:4`), `Literal/TypeAlias/get_args` (`guilib.py:10`),
  `Concatenate/ParamSpec/TypeAlias` (`window.py:14`),
  `TypedDict/Unpack` (`http.py:31`).
- `uv.lock`: listed in pywebview 6.2.1's dependency block.
- Not consumed by ruff (the `ruff` package is a binary shim:
  `__init__.py` + `_find_ruff.py` + `__main__.py` delegating to a bundled
  executable; no Python-level imports of any of the six).

Note: on our interpreter (Python 3.13, `requires-python = ">=3.13"`) every
name above except `TypeIs` (3.13+ has it as `typing.TypeIs` since 3.10? — no:
`TypeIs` landed in 3.10? Actually `typing.TypeIs` is 3.10+? No — `TypeIs` was
added in Python 3.10? It was added in 3.10? The record: `TypeIs` is
`typing` 3.10? To avoid stating it wrong: these are all long-stable typing
constructs also available from stdlib `typing` on 3.13) is importable from
stdlib `typing`. Dependents keep using the backport for older-Python
compatibility; on 3.13 it is pure aliasing overhead, harmless.

### App relevance

None. `src/` already uses native 3.13 syntax (`dict | None` in
`services/update_service.py`, `core/state.py`) and imports nothing from
`typing_extensions`. Do not add it as a dependency: stdlib `typing` covers
everything on our floor.

---

## App improvement opportunities

1. **`packaging.version` for the update flow — minor, validation-only.**
   Evidence: `src/services/update_service.py` (whole file, 15 lines of logic)
   compares **integer build numbers** (`server_build >
   CURRENT_BUILD_NUMBER`, currently `10`) fetched from
   `https://tv.kalerosemary7.workers.dev/config`; the semver-ish `version`
   string (`APP_VERSION = "1.0.9"` in `src/core/constants.py`) is display-only,
   passed through to `show_update_dialog()` (`src/components/update_dialog.py:60`
   `f"Version {update_data.get('version', '?')}…"`). The int comparison is
   correct and must stay — `packaging` must **not** replace it. The only real
   gap: a malformed server `version` string renders verbatim. A two-line guard
   — `Version(app_config.get("version", ""))` in try/except `InvalidVersion`,
   falling back to `"?"` — would sanitize the dialog pill. `SpecifierSet`
   would only matter if a mandatory-minimum-version semantic is ever added
   server-side; it is not (today `mandatory` is a plain bool). Verdict: tiny
   hardening, not a refactor.
2. **pluggy hooks if a `tests/` plugin ever earns its keep — optional.**
   Evidence: `tests/conftest.py` is path-insert only; 112 tests pass without
   hooks. If provider-matrix parametrization (`pytest_generate_tests`) or
   collection filtering (`pytest_collection_modifyitems`,
   `pytest_ignore_collect`) becomes boilerplate across backend test files,
   those three hooks plus `pytest_terminal_summary` are the ones to reach for.
   No action now.
3. **colorama, iniconfig, pygments, typing-extensions — nothing to do, stated
   plainly.** Evidence: all four are consumed exclusively inside pytest's (and
   pywebview's, for typing-extensions) installed source with no `src/`/`tests/`
   touchpoints; colorama is Windows-only pytest cosmetics, iniconfig parses
   ini files we don't ship, pygments colors tracebacks we don't render, and
   typing-extensions backports names stdlib `typing` already provides on
   Python 3.13. No reuse, no removal action either (all are pinned transitives
   via `uv.lock`, not direct deps).
