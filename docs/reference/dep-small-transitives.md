# Small transitive deps — repath / six / certifi / idna (installed venv build)

> **Version note (2026-10-15):** certifi is now **2026.7.22** (was 2026.6.17) and idna **3.20**
> (was 3.18); repath/six unchanged. The verdicts below are unaffected.


> Reference compiled from the installed package (`.venv/Lib/site-packages/`,
> `*.dist-info/METADATA`, `uv.lock`) — every statement verified against the
> installed source plus `grep` over dependents' source plus live introspection
> via `uv run python` from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.

Method (repro):

- `Read` each package's source (`repath.py`, `six.py`, `certifi/core.py` +
  `__init__.py`, `idna/__init__.py`).
- `grep -rn` over `.venv/Lib/site-packages/flet/`, `httpx/`, `httpcore/`,
  `anyio/`, `requests/`, `urllib3/`, `primp/` and over `src/`.
- `Requires-Dist` lines from each `*.dist-info/METADATA`; package pins from
  `uv.lock`; live checks via `uv run python -c "import repath,six,certifi,idna…"`.

## 0. Position in the graph

| Pkg | Version (source of truth) | Declares dep on | Required by (METADATA) | Chain to this app |
|---|---|---|---|---|
| repath | 0.9.0 (`repath-0.9.0.dist-info/METADATA` `Name/Version`; module has **no** `__version__` — `getattr(repath,'__version__','n/a')` → `'n/a'` live) | `six>=1.9.0` (`repath-0.9.0.dist-info/METADATA` `Requires-Dist`) | `flet` (`flet-0.85.3.dist-info/METADATA:16` `Requires-Dist: repath>=0.9.0`) | `flet → repath` (unconditional, not extra-gated) |
| six | 1.17.0 (`six.py:40` `__version__ = "1.17.0"`; `six-1.17.0.dist-info/METADATA`; live `six.__version__` → `1.17.0`) | nothing | `repath` (`Requires-Dist: six (>=1.9.0)`); `python-dateutil` (`python_dateutil-2.9.0.post0.dist-info/METADATA` matched `Requires-Dist: six`) | `flet → repath → six`; second path `flet-cli → cookiecutter → arrow → python-dateutil → six` (`arrow-1.4.0.dist-info/METADATA` `Requires-Dist: python-dateutil>=2.7.0`; `cookiecutter-2.7.1.dist-info/METADATA` requires `arrow`; `flet_cli-0.85.3.dist-info/METADATA` requires `cookiecutter>=2.6.0`) |
| certifi | 2026.6.17 (`certifi-2026.6.17.dist-info/METADATA` `Version: 2026.6.17`; `certifi/__init__.py` `__version__ = "2026.06.17"` — note `.` vs `0` formatting; live `certifi.__version__` → `2026.06.17`) | nothing | `httpcore`, `httpx`, `requests` (each `*.dist-info/METADATA` matched `Requires-Dist: certifi`); `primp` lists it **only** as `Requires-Dist: certifi ; extra == 'dev'` — not installed at runtime | `flet → httpx → certifi`, `flet → httpx → httpcore → certifi`. `uv.lock` pins `certifi 2026.6.17` (registry, sha256 `024c88ee…`) |
| idna | 3.18 (`idna-3.18.dist-info/METADATA` `Name/Version/Summary: Internationalized Domain Names in Applications (IDNA)`; live `idna.__version__` → `3.18`) | nothing | `httpx` (`Requires-Dist: idna`, unpinned), `anyio` (`Requires-Dist: idna>=2.8`), `requests` (`Requires-Dist: idna<4,>=2.5`) — all verified in respective `METADATA` | `flet → httpx → idna`; `flet → httpx → anyio → idna` |

App's own pins (`pyproject.toml`): `flet==0.85.3`, `primp>=1.3.1`,
`requires-python = ">=3.13"`. None of the four is a direct dependency.

## 1. repath 0.9.0 — Express-style route-path → regex

What it is (`repath-0.9.0.dist-info/METADATA` Summary/Description): "Generate
regular expressions form [sic] ExpressJS path patterns" — "A port of the
pathToRegexp node module to Python. Parses express-style paths to PCRE regular
expression patterns, taking advantage of Python's named capture groups."
Single-module package: `.venv/Lib/site-packages/repath.py` (297 lines).

Public API (`repath.py`, in order): `escape_string` (:64), `escape_group`
(:72), `parse` (:76), `tokens_to_template` (:134), `tokens_to_pattern` (:197),
`compile` (:239), `match` (:252), `pattern` (:266), `template` (:288).

The function flet uses — `pattern()` (`repath.py:266-285`):

```python
def pattern(path, **options):
    if isinstance(path, REGEXP_TYPE):
        return path.pattern
    if isinstance(path, list):
        parts = [pattern(p, **options) for p in path]
        return '(?:%s)' % '|'.join(parts)
    return tokens_to_pattern(parse(path), **options)
```

`tokens_to_pattern(tokens, end=True, strict=False)` (`repath.py:197-236`):
named params become `(?P<name>…)` groups (:217-218); default atom is
`[^<delim>]+?`; `*` → `.*`; suffixes `? * +` map through `PATTERNS`
(`repath.py:57-61` `REPEAT/OPTIONAL/REQUIRED`); non-strict appends
`(?:/(?=$))?`; `end=True` appends `$`, `end=False` appends `(?=/|$)`.

Syntax supported (`PATH_REGEXP`, `repath.py:21-55`; header table :13-19):
`:name`, `:name?` (optional), `:name*` / `:name+` (repeat),
`:name(\d+)` (custom capture), unnamed `(…)` groups, bare `*` splat,
`\:`-style escapes. `template()`/`tokens_to_template` builds URLs back from a
param dict (raises `KeyError`/`ValueError`/`TypeError` on missing/mismatched
values, :154-189) — flet never calls it (grep: no `repath.template` in flet).

Exactly how flet uses it — two files, six call sites, all `pattern()`:

1. `flet/components/router.py:16` — `import repath`. Then in
   `_try_match()`:
   - `:191` index route: `pattern = repath.pattern(full_path)` +
     `re.match(pattern, pathname)`; params = `m.groupdict()`,
     resolved = `m.group(0)` (:192-201).
   - `:228` recursive-route prefix: `repath.pattern(full_path, end=False)`
     + `re.match` → `consumed = prefix_m.group(0)`; remainder drives
     child-first-then-self-recursion (:246-257).
   - `:265` parent-with-children prefix: `repath.pattern(full_path, end=False)`
     → `parent_params = prefix_m.groupdict()` (:266-270).
   - `:287` parent-with-component exact fallback:
     `repath.pattern(full_path)` + `re.match` (:287-288).
   - `:302` leaf exact: `leaf_pattern = repath.pattern(full_path)` +
     `re.match` (:302-303).
2. `flet/controls/template_route.py:3` — `import repath`; `:44`
   `pattern = repath.pattern(route_template)` then
   `re.match(pattern, self.route)`; on hit, `match.groupdict()` is stored
   and also set as attributes (`self.user_id`-style, :47-51); previous
   params are cleared to `None` before each attempt (:40-41). Docstring
   (:27, :34) names `repath.pattern()` explicitly.

Live behaviour (verified `uv run python` from project root):

- `repath.pattern('/products/:pid')` →
  `'^/products/(?P<pid>[^/]+?)(?:/(?=$))?$'`
- `repath.pattern('/about', end=False)` → `'^/about(?:/(?=$))?(?=/|$)'`
- `repath.pattern('/files/:name*')` →
  `'^/files(?:/(?P<name>[^/]+?(?:/[^/]+?)*))?(?:/(?=$))?$'`
- `repath.match('/products/:pid', '/products/42').groupdict()` →
  `{'pid': '42'}`

What our app could ever touch: `flet.Router`/`Route(path="…")` route trees
(`flet/components/router.py:593-638`, params via `use_route_params()`,
`is_route_active()`) and `flet.TemplateRoute(route).match(template)`
(`flet/controls/template_route.py:19-52`). Evidence of current state: grep
over `src/` for `import repath`, `TemplateRoute`, `ft.Router`, `flet.*Router`,
`page.route`, `on_route_change` returns **nothing** — the app does not use
flet URL routing today (its own `src/services/router.py` `ProviderRouter` is
an unrelated provider-failover/circuit-breaker, :107-199). So repath runs
only if/when the app adopts flet routing; there is no app code to update for
repath upgrades beyond what flet requires.

## 2. six 1.17.0 — Python 2/3 shims

What it is (`six.py:31` docstring): "Utilities for writing code that runs on
Python 2 and 3". Single-module package, `__author__ = "Benjamin Peterson"`.
No entry points, no data files.

What flet still imports from it: **nothing**. `grep -rn "six"
.venv/Lib/site-packages/flet/ --include="*.py"` returns empty. Flet's only
contact with six is second-hand through repath.

Who actually executes six code in this venv:

- `repath.py:3-4` — `import six` + `from six.moves.urllib import parse as urllib`.
  Usages (`grep -n "six" repath.py`): `:144`
  `isinstance(token, six.string_types)`, `:174`/`：185`
  `six.text_type(…)` (incl. `value.encode('utf8')` quoting at :191),
  `:204`/`:207` `isinstance(…, six.string_types)`. On Python 3 these are
  `str` and `urllib.parse.quote` — pure aliases.
- `dateutil/` — 8 modules (`rrule.py`, `relativedelta.py`,
  `parser/_parser.py`, `parser/isoparser.py`, `tz/_common.py`, `tz/_factories.py`,
  `tz/win.py`, `tz/z.py` all match `^import six|^from six`). dateutil is
  dev-tooling-only here (via `arrow ← cookiecutter ← flet-cli`), not app runtime.

What our app could ever touch: nothing. `grep -rn "import six\|from six"
src/` is empty; `pyproject.toml` floor is `>=3.13`, so every `six.*` alias
is a no-op `str`/`urllib.parse` on all supported interpreters. six exists
solely to satisfy `repath`'s `Requires-Dist: six (>=1.9.0)` and dateutil's.
Safe to ignore except as reinstall weight (~35 KB sdist per `uv.lock`).

## 3. certifi 2026.6.17 — Mozilla CA bundle

What it is: a versioned snapshot of Mozilla's root certificates plus two
accessors. Installed layout: `certifi/__init__.py`, `certifi/core.py`,
`certifi/cacert.pem`, `certifi/py.typed`.

- `certifi/__init__.py`: `from .core import contents, where`;
  `__all__ = ["contents", "where"]`.
- `certifi/core.py:21-44` — `where() -> str`: lazily resolves
  `cacert.pem` via `importlib.resources.as_file(files("certifi")…)`,
  caches in `_CACERT_PATH`, registers `atexit` cleanup; returns the path.
- `certifi/core.py:46-47` — `contents() -> str`: reads the PEM as ASCII text.
- Live: `certifi.where()` →
  `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\.venv\Lib\site-packages\certifi\cacert.pem`.

How httpx / httpcore consume it (the only runtime consumers on the app's
import path):

- `httpx/_config.py:22-27` —
  `create_ssl_context(verify: ssl.SSLContext | str | bool = True, cert…,
  trust_env: bool = True) -> ssl.SSLContext`; `:31` `import certifi`
  (function-local); `:36-40`: if `verify is True` and neither `SSL_CERT_FILE`
  nor `SSL_CERT_DIR` is set, `ctx = ssl.create_default_context(cafile=
  certifi.where())`. `verify=False` builds an unverified `SSLContext`;
  `verify=<str>` is deprecated in favour of passing a prebuilt context.
- `httpcore/_ssl.py:3,8` — `import certifi`;
  `default_ssl_context()`: `ssl.create_default_context()` then
  `context.load_verify_locations(certifi.where())`.
- Flet reaches both via `flet → httpx → {httpx._config, httpcore._ssl}`:
  `flet-0.85.3.dist-info/METADATA` has
  `Requires-Dist: httpx>=0.28.1; platform_system != "Emscripten"`;
  `httpx-0.28.1.dist-info/METADATA` has `Requires-Dist: certifi`,
  `httpcore`, `idna`; `httpcore-1.0.9.dist-info/METADATA` has
  `Requires-Dist: certifi`, `h11`. Flet's own `import httpx` sites are lazy
  and OAuth-scoped only: `flet/auth/authorization_service.py:119,207,245`,
  `flet/auth/providers/github_oauth_provider.py:41,74`.

Does primp use certifi at all? **No — not at runtime.** Evidence:

- `primp-1.3.1.dist-info/METADATA` `Requires-Dist` block is five lines, every
  one gated on `extra == 'dev'`; the certifi line reads
  `Requires-Dist: certifi ; extra == 'dev'`. A default `pip install primp`
  / `uv sync` therefore never pulls certifi for primp.
- `primp/__init__.py` is `from .primp import *` — the implementation is the
  compiled Rust extension `primp/primp.pyd` (~9.8 MB). `grep -rn "certifi"
  primp/ --include="*.py"` finds nothing; there is no `import certifi` in
  the Python shim.
- primp's TLS surface is its own (`primp/__init__.pyi`,
  `Client.__init__` :259-281, byte-identical on `AsyncClient` :464+):
  `verify: bool = True` and `ca_cert_file: str | None = None`
  (plus `https_only`, `http2_only`, `dns_resolver`, `proxy`). No
  `SSL_CERT_FILE`/`SSL_CERT_DIR` env handling, no `cafile=certifi.where()`
  default — unlike `httpx/_config.py:36-40`.
- Binary marker scan (`primp.pyd` read as bytes, exact-substring counts):
  `rustls` 143, `webpki` 13, `rustls-native` 1, `native-certs` 1,
  `ca_cert_file` 19, `certifi` 48. The rustls/webpki/native-certs markers
  corroborate a Rust-TLS stack independent of OpenSSL+certifi; the 48
  `certifi` substrings are **uninterpreted** (embedding reason unverified —
  see §5) and change none of the above: no Python-level import, no runtime
  metadata dependency.

What our app could ever touch: `certifi.where()` as an argument to
`primp.AsyncClient(…, ca_cert_file=…)` — and today it passes nothing:
all 8 `primp.AsyncClient(…)` call sites
(`services/ddos_solver.py:65`, `services/downloads.py:134`,
`services/kwik_resolver.py:55`, `services/hls_proxy.py:167`,
`services/update_service.py:17`, `services/providers/animeout.py:63,325`,
`services/providers/anikato.py:190`) use defaults
(`verify=True`, `ca_cert_file=None`) plus `impersonate="chrome"`/timeouts.
`grep -rn "verify=" src/` and `grep -rn "ca_cert\|SSL_CERT\|certifi|cacert"
src/` are both empty. So: app TLS = primp defaults; certifi updates only
affect flet's httpx OAuth path, never streaming traffic.

## 4. idna 3.18 — IDNA / UTS-46 domain encoding

What it is: implementation of Internationalized Domain Names in Applications
(IDNA 2008 + UTS-46 tightening). Installed layout: `idna/__init__.py`,
`core.py`, `codec.py`, `compat.py`, `uts46data.py`, `idnadata.py`,
`intranges.py`, `package_data.py` (holds `__version__`), `cli.py`.
`idna/__init__.py:1-38` re-exports `encode`, `decode`, `alabel`, `ulabel`,
`check_*`, `valid_*`, `IDNAError`/`IDNABidiError`/`InvalidCodepoint*`.

Exact call sites in dependents (all verified by grep + surrounding read):

- `httpx/_urlparse.py:25` `import idna`; `:390-391`
  `return idna.encode(host.lower()).decode("ascii")` inside
  `except idna.IDNAError:` — host normalisation when building request URLs.
- `httpx/_urls.py:6` `import idna`; `:191` `host = idna.decode(host)` —
  display/decoding path for `URL.host`.
- `anyio/_core/_sockets.py:648-654` — inside the async `getaddrinfo` wrapper:
  `host.encode("ascii")` tried first; on `UnicodeEncodeError` only,
  `import idna; encoded_host = idna.encode(host, uts46=True)` before
  delegating to the backend's `getaddrinfo`. (`Requires-Dist: idna>=2.8`.)
- `requests/models.py:472-477` — `_get_idna_encoded_host()`:
  `import idna; host = idna.encode(host, uts46=True).decode("utf-8")`
  guarded by `except idna.IDNAError`; called at `:528` during prepared-URL
  serialisation. (Note `:15` is `import encodings.idna` — stdlib codec, not
  this package.) `requests` needs `idna<4,>=2.5`.
- `urllib3/util/url.py:432-443` — `_idna_encode()`:
  `import idna; return idna.encode(name.lower(), strict=True, std3_rules=True)`
  guarded by `except idna.IDNAError`. urllib3/requests reach this venv only
  via dev tooling (`cookiecutter`, `pytest`, `markdown-it` METADATA chains),
  not via flet or the app.

What our app could ever touch: nothing directly. `grep -rn "import idna"
src/` is empty; every provider/upstream host the app contacts is ASCII, so
the anyio `UnicodeEncodeError` branch and the httpx encode path are dormant
by construction. If a non-ASCII (e.g. user-entered or mirror) hostname ever
appears, httpx/anyio already call `idna.encode(…, uts46=True)` internally —
no app code needed.

## App improvement opportunities

Scope note: each item cites the verified source + signature it rests on.
A trailing "Explicitly unverified" list separates what was observed but not
proven. Checked and deliberately excluded: app routing files, all
`primp.AsyncClient(` call sites, `verify=`/`ca_cert`/`certifi` mentions in
`src/`, flet `Router`/`TemplateRoute` adoption, non-ASCII hosts.

### 1. certifi — document (don't change) the two-store TLS reality [VERIFIED, recommended]

Finding: app traffic is verified by primp's compiled-in Rust store
(`primp/__init__.pyi` `Client.__init__:259-281`
`verify: bool = True, ca_cert_file: str | None = None`; binary markers
`rustls`×143 `webpki`×13 `rustls-native`×1 `native-certs`×1), while
`certifi.where()` (`certifi/core.py:21-44`) only feeds flet's httpx OAuth
path (`httpx/_config.py:31,40`, `httpcore/_ssl.py:3,8`). All 8 app
`primp.AsyncClient(` sites accept the defaults; `grep verify= src/` is empty.
Operational consequence, verified from the metadata above: upgrading certifi
(e.g. `uv lock --upgrade-package certifi`) patches OAuth TLS only — it
cannot patch streaming/download TLS. Recommendation: add a one-line comment
at one representative call site (e.g. `src/services/hls_proxy.py:167-170`)
stating "TLS roots = primp-bundled (rustls), not certifi; see
`primp/__init__.pyi:259-281`" so a future TLS failure isn't mis-triaged as a
stale CA bundle. Cost ~zero, prevents a real misdiagnosis. `ca_cert_file=
certifi.where()` exists as an escape hatch for pinning both stacks to one
bundle (signature verified same lines), but do **not** set it by default —
it swaps an audited default for a maintenance burden with no failing case on
record (no `verify`/`ca_cert` hits in `src/` to motivate it).

### 2. repath — no change now; one real trick banked for later [VERIFIED]

Finding: flet exposes the full Express grammar through two wrappers the app
doesn't call (`flet/components/router.py:191,228,265,287,302`,
`flet/controls/template_route.py:44`; `grep TemplateRoute|ft.Router|
on_route_change src/` empty; app's `services/router.py` is provider
failover, unrelated). The unused-but-available tricks, verified live in §1:
optional segments (`:name?`), splats (`:name*`), and regex-constrained params
(`:name(\d+)`, `repath.py:21-55`) with `end=False` prefix semantics for
layout routes (`router.py:228,265`). Recommendation: none — the app navigates
via an explicit view/screen stack (`src/main.py:253` references `page.views`;
no `page.go`/`render_views` in `src/`), so adopting `Router` would add
machinery with no deep-link requirement. If deep links (e.g. `/watch/:id`,
`/search/:query?`) are ever needed, prefer `TemplateRoute.match()` over
hand-rolled splits — the grammar and `groupdict()` attribute assignment are
already tested above.

### 3. six — no opportunity [VERIFIED, stated plainly]

Checked: `grep -rn "six" flet/ --include="*.py"` empty (flet imports nothing
from six); `repath.py:3-4,144,174,185,204,207` uses only `six.string_types`
(= `str`), `six.text_type` (= `str`), `six.moves.urllib.parse.quote`
(= `urllib.parse.quote`); `pyproject.toml` floor is `>=3.13`; `src/` has no
six import. There is no improvement to extract — six is inert weight kept
alive by `repath`'s `Requires-Dist: six (>=1.9.0)`.

### 4. idna — no opportunity [VERIFIED, stated plainly]

Checked: all five call sites (`httpx/_urlparse.py:390-391`,
`httpx/_urls.py:191`, `anyio/_core/_sockets.py:651-653`,
`requests/models.py:472-477,528`, `urllib3/util/url.py:432-443`) trigger
only on non-ASCII hosts or display decoding; every app upstream host is
ASCII and `src/` never imports idna. UTS-46 handling is already automatic
(`uts46=True` at both encode sites), so internationalised mirror domains
would just work. No code, config, or pin change recommended.

### Explicitly unverified (observed, not claimed)

- The 48 `certifi` byte-substrings inside `primp.pyd` (same scan that
  produced the rustls/webpki counts in §3): embedding reason unknown —
  could be bundled fallback strings, debug/error text, or coincidence. Not
  evidence of runtime `certifi` consumption (contradicted at the Python and
  metadata layers); would need primp's Rust source or a TLS-intercept test
  to interpret.
- Whether primp's default store is webpki-bundled roots vs. OS-native roots
  (`native-certs`×1 vs `webpki`×13 both present): the binary contains markers
  for both hypotheses; `__init__.pyi` documents neither. No claim made.
- Any performance/correctness delta from passing
  `ca_cert_file=certifi.where()` to primp: mechanism verified, benefit not
  measured — no test performed, so not recommended.
