# primp 1.3.1 — complete public API (installed venv build)

> **Version note (2026-10-15):** compiled against primp 1.3.1; installed is **primp 2.0.1** —
> install source wins, and the deltas are load-bearing: `AsyncClient` has **no** `aclose`/
> `close`/`is_closed` (cleanup is the context manager only), and `Response` has **no**
> `reason_phrase`/`history`. The swarm audit counted ~8 criticals across 5 files from trusting
> this doc's old surface (docs/swarm-audit-2026-10-13.md §1.1, §6). Full refresh in hybrid
> Phase 5.


> Reference compiled from the installed package (`.venv/Lib/site-packages/primp/`,
> `primp.pyd` ~9.8 MB Rust extension, maturin 1.13.3) — every signature verified
> live against the loaded module.

`Name: primp, Version: 1.3.1, Requires-Python: >=3.10, MIT, Author: deedy5`
"HTTP client that can impersonate web browsers." `__init__.py` is `from .primp import *`.

`__all__ = ['PrimpError','BuilderError','RequestError','ConnectError','TimeoutError',
'StatusError','RedirectError','BodyError','DecodeError','UpgradeError','Response',
'BytesIterator','TextIterator','LinesIterator','Client','AsyncClient','AsyncResponse',
'AsyncBytesIterator','AsyncTextIterator','AsyncLinesIterator','get','head','options',
'delete','post','put','patch','request','__version__']`

## Exceptions

```python
class PrimpError(Exception): ...


class BuilderError(PrimpError): ...  # client builder config


class RequestError(PrimpError): ...


class ConnectError(RequestError): ...


class TimeoutError(RequestError): ...  # verified live on a dead server


class StatusError(PrimpError): ...  # 4xx/5xx via raise_for_status()


class RedirectError(PrimpError): ...


class BodyError(PrimpError): ...


class DecodeError(PrimpError): ...


class UpgradeError(PrimpError): ...
```
MRO: `ConnectError->RequestError->PrimpError`; `TimeoutError->RequestError->PrimpError`.

## 1. Client / AsyncClient constructor (byte-identical signatures)

```python
(auth=None, auth_bearer=None, params=None, headers=None, cookie_store=True,
 referer=True, proxy=None, timeout=None, connect_timeout=None, read_timeout=None,
 impersonate=None, impersonate_os=None, follow_redirects=True, max_redirects=20,
 verify=True, ca_cert_file=None, https_only=False, http2_only=False,
 dns_resolver=None, base_url=None, cookies=None)
```

- Type aliases: all maps are `Mapping[str, str]` (headers/params/cookies); `files: Mapping[str, str]` is a path mapping, not httpx-style tuples.
- Mutable after construction (getset): `auth`, `auth_bearer`, `params`, `proxy`, `timeout`, `connect_timeout`, `read_timeout`, `base_url`, `headers` (+ `headers_update(new_headers)`).
- Read-only after construction (assignment raises `AttributeError`): `impersonate`, `impersonate_os`.
- `proxy: str | None` — single string only; no per-scheme dict, no per-request override.
- `cookie_store: bool = True` — persistent jar; `referer: bool = True` — auto-sends Referer (no httpx equivalent).
- Timeouts are plain `float | None` seconds; per-request overrides are limited to `timeout`/`read_timeout`/`follow_redirects`.
- `max_redirects: int = 20`; **no response `history` is exposed**.
- TLS/transport: `verify`, `ca_cert_file`, `https_only`, `http2_only`, `dns_resolver: str | list[str] | None`.
- Extra client methods: `get_cookies(url) -> dict[str, str]`, `set_cookies(url, cookies)`.
- `Client` is a sync context manager; `AsyncClient` an async one.
- Invalid `impersonate` does NOT raise: prints `Impersonate '<x>' does not exist, using 'random'` and keeps the string on `.impersonate`.

### Impersonate profiles (from METADATA — the shipped enumeration)

| Browser | Values |
|---|---|
| Chrome | `chrome_144` … `chrome_148`, `chrome` |
| Safari | `safari_18.5`, `safari_26`, `safari_26.3`, `safari` |
| Edge | `edge_144` … `edge_148`, `edge` |
| Firefox | `firefox_140`, `firefox_146` … `firefox_148`, `firefox` |
| Opera | `opera_126` … `opera_131`, `opera` |
| Random | `random` |

`impersonate_os`: `android`, `ios`, `linux`, `macos`, `windows`, `random` (default None).

Observed default header set for `impersonate='chrome_146'`: full Chrome client-hint set
(`sec-ch-ua`, `sec-fetch-*`, `priority`, UA `Chrome/146.0.0.0`, `accept-encoding: gzip, deflate, br, zstd`)
— TLS + HTTP/2 fingerprint AND header order match the browser.

## 2. Request options

```python
def request(self, method, url, params=None, headers=None, cookies=None,
    content: bytes | None = None, data=None, json=None, files=None, auth=None,
    auth_bearer=None, timeout=None, read_timeout=None, follow_redirects=None,
    stream: bool = False) -> Response
# get/head/options/delete/post/put/patch: same minus `method`
```

Per-request overridables: ONLY `timeout`, `read_timeout`, `follow_redirects` (None = inherit).
No per-request proxy/impersonate/verify/max_redirects.

Module-level one-shots (`primp.get(...)` etc.) additionally accept `connect_timeout`,
`impersonate`, `impersonate_os`, `verify`, `ca_cert_file` — but NOT `proxy`,
`cookie_store`, `referer`, `max_redirects`, `https_only`, `http2_only`, `dns_resolver`, `base_url`.

## 3. Response

```python
class Response:
    url: str
    status_code: int
    content: bytes        # property
    encoding: str         # property, settable
    headers: dict[str, str]
    cookies: dict[str, str]
    text: str
    text_markdown: str    # HTML->markdown conversion
    text_plain: str
    text_rich: str
    def json(self) -> Any
    def raise_for_status(self) -> None
    def read(self) -> bytes
    def iter_bytes(self, chunk_size=None) / iter_text / iter_lines
    def next(self) -> bytes | None
    def close(self) -> None
```

No `history`, `request`, `elapsed`, `http_version`, or `extensions`. Async mirrors with
`aread/aiter_*/anext/aclose` plus undocumented `content_async`, `text_async`, `json_async`.
`AsyncResponse` note from stubs: "All property access is synchronous but may block."

## 4. Anti-bot surface (the reason this package is load-bearing)

- Full browser TLS + HTTP/2 fingerprint impersonation (rustls 0.23.40 with preconfigured
  fingerprints, GREASE/ECH strings in the binary), matching header order + client hints.
- NO challenge solver: no `cloudflare`/`turnstile`/`ja3`/`fingerprint` strings anywhere.
  What passes with primp: TLS-fingerprint-gated hosts (the kwik CDN: httpx 403, primp 200).
  What does NOT pass: JS challenges (animeout's public.animeout.xyz: httpx AND primp both 403).

## 5. Async

`AsyncClient` methods are pyo3 futures — `inspect.iscoroutinefunction` reports False, but
they return awaitables (`asyncio.Future`). Pattern:
`async with AsyncClient(impersonate="chrome_146") as client: resp = await client.get(...)`.

## 6. What we're not using yet (opportunities)

- `http2_only` — force HTTP/2 where a CDN prefers it.
- `dns_resolver` — custom DNS (e.g. DoH) if a host resolves badly on some networks.
- `get_cookies/set_cookies(url, ...)` — direct jar manipulation for cf_clearance persistence
  (currently done through the store).
- `stream=True` + `aiter_bytes` — chunked download streaming (the downloads feature).
- `base_url` — per-provider base URLs for cleaner request code.
- `text_markdown` — cheap HTML→text for synopses (no bs4 needed).
- `impersonate_os='android'` — Android-shaped requests where a CDN cares.
