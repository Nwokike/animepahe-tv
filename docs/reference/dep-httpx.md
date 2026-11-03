# httpx 0.28.1 — complete public API (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/httpx/`, pure-Python, `py.typed` present).
> Every signature below was verified live via
> `.venv/Scripts/python.exe -c "import httpx, inspect"` or by reading the
> installed source file cited.

`__version__.py`: `__title__ = "httpx"`, `__version__ = "0.28.1"`,
`__description__ = "A next generation HTTP client, for Python 3."`

`__all__` (`__init__.py:29-99`, 70 names) includes:
`ASGITransport, AsyncBaseTransport, AsyncByteStream, AsyncClient,
AsyncHTTPTransport, Auth, BaseTransport, BasicAuth, ByteStream, Client,
CloseError, codes, ConnectError, ConnectTimeout, CookieConflict, Cookies,
create_ssl_context, DecodingError, delete, DigestAuth, get, head, Headers,
HTTPError, HTTPStatusError, HTTPTransport, InvalidURL, Limits,
LocalProtocolError, main, MockTransport, NetRCAuth, NetworkError, options,
patch, PoolTimeout, post, ProtocolError, Proxy, ProxyError, put, QueryParams,
ReadError, ReadTimeout, RemoteProtocolError, request, Request, RequestError,
RequestNotRead, Response, ResponseNotRead, stream, StreamClosed,
StreamConsumed, StreamError, SyncByteStream, Timeout, TimeoutException,
TooManyRedirects, TransportError, UnsupportedProtocol, URL,
USE_CLIENT_DEFAULT, WriteError, WriteTimeout, WSGITransport`.
(`_auth.FunctionAuth` exists in `_auth.py` but is NOT re-exported in `__all__`.)

## 1. Client / AsyncClient constructor (verified live `inspect.signature`)

Signatures are identical except `trust_env` position (see note). Source:
`_client.py:639` (`Client.__init__`), `_client.py:1353` (`AsyncClient.__init__`).

```python
Client(
    *,
    auth: AuthTypes | None = None,
    params: QueryParamTypes | None = None,
    headers: HeaderTypes | None = None,
    cookies: CookieTypes | None = None,
    verify: ssl.SSLContext | str | bool = True,
    cert: CertTypes | None = None,
    trust_env: bool = True,          # AsyncClient: same name, listed after `transport`
    http1: bool = True,
    http2: bool = False,             # requires `h2` package, else ImportError (_client.py:~http2 check)
    proxy: ProxyTypes | None = None,
    mounts: Mapping[str, BaseTransport | None] | None = None,       # Async: AsyncBaseTransport
    timeout: TimeoutTypes = Timeout(timeout=5.0),
    follow_redirects: bool = False,
    limits: Limits = Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0),
    max_redirects: int = 20,
    event_hooks: Mapping[str, list[EventHook]] | None = None,
    base_url: URL | str = "",
    transport: BaseTransport | None = None,                          # Async: AsyncBaseTransport | None
    default_encoding: str | Callable[[bytes], str] = "utf-8",
) -> None
```

Parameter notes (source evidence):

- `auth: AuthTypes` (`_types.py:62`): `tuple[user, pass] | Callable[[Request], Request] | Auth`.
  Concrete classes: `BasicAuth(username: str | bytes, password: str | bytes)`,
  `DigestAuth(username, password)` (same signature, verified live),
  `NetRCAuth(file: str | None = None)` (verified live), `Auth` base
  (`_auth.py`, `auth_flow(request)` generator protocol — `inspect.getsource(Auth)[:800]`
  shows `def auth_flow`). Per-request `auth=` overrides client auth
  (`_build_request_auth`, `_client.py:457`).
- `verify` (`_config.py:23` `create_ssl_context(verify=True, cert=None, trust_env=True)`):
  `True` → `ssl.create_default_context(cafile=certifi.where())`, honouring
  `SSL_CERT_FILE`/`SSL_CERT_DIR` env when `trust_env=True`; `False` → unverified
  context; `str` → deprecated, treated as cafile/capath (warns `DeprecationWarning`);
  `SSLContext` instance used directly. `cert=` is deprecated — use an `SSLContext`
  with `.load_cert_chain()`.
- `trust_env: bool = True` — when true AND `transport is None`, proxy config is read
  from the environment (`_client.py`: `allow_env_proxies = trust_env and transport is None`;
  `get_environment_proxies` in `_utils.py`). Setting `trust_env=False` disables
  env-proxy pickup. Same flag gates `SSL_CERT_FILE`/`SSL_CERT_DIR` in `create_ssl_context`.
- `http1=True, http2=False`. `http2=True` without the `h2` package raises
  `ImportError("Using http2=True, but the 'h2' package is not installed...")`.
- `proxy: ProxyTypes` (`_types.py:59`): `URL | str | Proxy`. `Proxy(url, *, ssl_context=None,
  auth=(user, pass) | None, headers=None)` (`_config.py:201`, signature verified live).
  Accepted schemes: `http`, `https`, `socks5`, `socks5h` (else `ValueError`).
  Credentials embedded in the URL are stripped into `proxy.auth`.
  A single `proxy=` is expanded to a mount table via `_get_proxy_map`
  (`_client.py:239`); `mounts=` entries are applied on top and win
  (`_client.py` mounts-handling block: `self._mounts.update(...)`, then sorted).
- `mounts`: `Mapping[str, BaseTransport | None]` keyed by URL pattern
  (`URLPattern`, `_utils.py`). A value of `None` means "no transport" for that
  pattern. Resolution: `_transport_for_url(url)` (`_client.py:760` sync /
  `:1474` async). Keys are sorted (`dict(sorted(self._mounts.items()))`).
- `timeout: TimeoutTypes` (`_types.py:54`): `float | None | tuple[c,r,w,p] | Timeout`.
  `Timeout(timeout=UNSET, *, connect, read, write, pool)` (`_config.py:86`).
  `Timeout(5.0)` sets all four to 5.0; `Timeout(None)` disables all;
  `Timeout(None, connect=5.0)` enables connect only. Defaults:
  `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)` (`_config.py:246`).
  Per-request `timeout=` overrides (`USE_CLIENT_DEFAULT` sentinel = inherit client).
  `timeout=None` explicitly disables. Extensions dict always carries
  `timeout.as_dict()` (`_client.py:371-377`).
- `limits: Limits(*, max_connections=None, max_keepalive_connections=None,
  keepalive_expiry=5.0)` (`_config.py:173`, verified live).
  Default: `DEFAULT_LIMITS = Limits(max_connections=100,
  max_keepalive_connections=20)` (`_config.py:247`).
- `follow_redirects: bool = False` client default; per-request override allowed.
  `max_redirects: int = 20` (`DEFAULT_MAX_REDIRECTS`, `_config.py:248`); exceeding
  raises `TooManyRedirects` (`_send_handling_redirects`, `_client.py:964`:
  `if len(history) > self.max_redirects`). Redirect chain recorded on
  `response.history` (see §3).
- `event_hooks`: keys are exactly `"request"` and `"response"`
  (`_client.py:215-217`, `267-268`). `EventHook = Callable[..., Any]`
  (`_client.py`, `EventHook = typing.Callable[..., typing.Any]`). Request hooks run
  at `_client.py:976`, response hooks at `:981` (sync; async `:1691`/`:1696`).
- `base_url: URL | str = ""`. Merge rule (`_merge_url`, `_client.py:391`): only
  relative-URL arguments are merged — base gets a forced trailing `/`, the merge
  path is left-stripped of `/`, then concatenated
  (`merge_raw_path = base.raw_path + merge_url.raw_path.lstrip(b"/")`).
  Absolute request URLs ignore `base_url`. Verified: `Client(base_url=".../subpath")`
  + `build_request("GET", "/path").url` → `.../subpath/path`.
- `transport=`: inject any `BaseTransport` / `AsyncBaseTransport`. When set,
  env proxies are NOT auto-applied (`allow_env_proxies = trust_env and transport is None`).
- Mutable after construction (get/set properties, `_client.py:254-337`):
  `timeout`, `event_hooks`, `auth`, `base_url` (re-enforces trailing slash),
  `headers`, `cookies`, `params`. `is_closed`, `trust_env` are read-only properties.

Context-manager use: `Client` is a sync CM (`__enter__/__exit__`, `_client.py:1275`);
`AsyncClient` an async CM. `close()` / `await aclose()`. `ClientState`
(`_client.py:125`): `UNOPENED / OPENED / CLOSED`.

## 2. Request options

Top-level one-shot API (`_api.py:39+`): `request, stream, get, options, head,
post, put, patch, delete`. One-shot `request()` signature (verified live):

```python
httpx.request(method, url, *, params=None, content=None, data=None, files=None,
    json=None, headers=None, cookies=None, auth=None, proxy=None,
    timeout=Timeout(timeout=5.0), follow_redirects=False,
    verify=True, trust_env=True) -> Response
httpx.get(url, *, params=None, headers=None, cookies=None, auth=None, proxy=None,
    follow_redirects=False, verify=True, timeout=Timeout(timeout=5.0),
    trust_env=True) -> Response
```

Client verbs (verified live on `Client`; `AsyncClient` identical but `async`):

```python
Client.request(method, url, *, content=None, data=None, files=None, json=None,
    params=None, headers=None, cookies=None,
    auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
    follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    timeout: TimeoutTypes | UseClientDefault = USE_CLIENT_DEFAULT,
    extensions: RequestExtensions | None = None) -> Response
Client.get(url, *, params=None, headers=None, cookies=None,
    auth=USE_CLIENT_DEFAULT, follow_redirects=USE_CLIENT_DEFAULT,
    timeout=USE_CLIENT_DEFAULT, extensions=None) -> Response
# post/put/patch/delete/options/head: same as get, plus
#   content=None, data=None, files=None, json=None
Client.build_request(method, url, *, content=None, data=None, files=None, json=None,
    params=None, headers=None, cookies=None,
    timeout=USE_CLIENT_DEFAULT, extensions=None) -> Request
Client.send(request, *, stream=False,
    auth=USE_CLIENT_DEFAULT, follow_redirects=USE_CLIENT_DEFAULT) -> Response
Client.stream(method, url, *, <same as request>) -> Iterator[Response]  # context manager
# AsyncClient.stream(...) -> AsyncIterator[Response]
```

- `USE_CLIENT_DEFAULT` (`_client.py:94-114`): the "unset" sentinel. Omitting the
  parameter inherits the client default; passing `None` explicitly disables
  (e.g. `timeout=None` = no timeout, `auth=None` = no auth).
- Body forms (`Request.__init__` verified live):
  `Request(method, url, *, params=None, headers=None, cookies=None, content=None,
  data=None, files=None, json=None, stream=None, extensions=None)`.
  `content: str | bytes | Iterable[bytes] | AsyncIterable[bytes]`;
  `data: Mapping[str, Any]` (form-encoded); `files: Mapping | Sequence`
  of `FileTypes` (`_types.py:75-85`: bare content, `(filename, content)`,
  `(filename, content, content_type)`, `(filename, content, content_type, headers)`).
- `extensions: RequestExtensions = Mapping[str, Any]` (`_types.py:87`) — per-request
  transport hints; client always injects `extensions["timeout"] = timeout.as_dict()`.
- `Request` surface (verified `dir()`): only `.content`, `.read()`, `.aread()`
  beyond dunders; `.method: str`, `.url: URL`, `.headers: Headers`,
  `.extensions: dict` (set at `_models.py:401`), `.stream`. Default headers on a
  manually built request include `Host` (verified live: `Request('GET',
  'https://example.org/x').headers == {'host': 'example.org'}`); omitting `Host`
  and calling `send()` directly can raise `LocalProtocolError`.
- Client merge order: client-level `params/headers/cookies` merged with
  per-request values (`_merge_cookies/_merge_headers/_merge_queryparams`,
  `_client.py:413-433`).

## 3. Response surface (`_models.py:515+`, constructor verified live)

```python
Response(status_code: int, *, headers=None, content=None, text=None, html=None,
    json=None, stream=None, request=None, extensions=None, history=None,
    default_encoding: str | Callable[[bytes], str] = "utf-8")
```

- Plain attributes (`_models.py:531-541`): `.status_code: int`, `.headers: Headers`,
  `.extensions: dict` (`{}` if None), `.history: list[Response]` (`[]` if None),
  `.next_request: Request | None` (set when `follow_redirects=False` and a redirect
  arrives), `.default_encoding`, `.is_closed`, `.is_stream_consumed`.
- Properties: `.url -> URL` (via `request.url`, `:629`); `.request` with setter
  (raises `RuntimeError` if unset, `:596-608`); `.elapsed: timedelta` — raises
  `RuntimeError` unless the response was read/closed (`:578-593`; hit live in
  probing: `RuntimeError: '.elapsed' may only be accessed after the response
  has been read or closed`); `.http_version: str` (from
  `extensions["http_version"]`, default `"HTTP/1.1"`, `:610-617`);
  `.reason_phrase: str` (from `extensions["reason_phrase"]`, else
  `codes.get_reason_phrase(status_code)`, `:619-627`); `.content: bytes` (raises
  `ResponseNotRead` if streaming and unread, `:635-640`); `.text: str`
  (charset detection via headers → apparent encoding → `default_encoding`,
  `:641-675`); `.encoding` (get/set); `.charset_encoding`;
  `.cookies: Cookies` (parsed from headers, `:834`); `.links` (parsed
  `Link` header, `:841`); `.num_bytes_downloaded: int` (`:855`).
- Status predicates (`:724-772`): `is_informational (100-199)`, `is_success (200-299)`,
  `is_redirect (300-399, ``has_redirect_location`` checks `location`, `:771`),
  `is_client_error (400-499)`, `is_server_error (500-599)`, `is_error` (400+).
  `repr`: `<Response [200 OK]>` (`:860`).
- `.raise_for_status() -> Response` (`:794`, signature `(self) -> Response` verified
  live): raises `HTTPStatusError` with MDN link in message (`:810-817`); no-op on <400.
- `.json(**kwargs) -> Any` (`:831`, kwargs forwarded to `json.loads`).
- Read/iterate (sync, `_models.py:876-973`):
  `.read() -> bytes`, `.iter_bytes(chunk_size=None)`, `.iter_text(chunk_size=None)`,
  `.iter_lines() -> Iterator[str]`, `.iter_raw(chunk_size=None)`, `.close() -> None`.
  Async mirrors: `.aread()`, `.aiter_bytes(chunk_size=None)`,
  `.aiter_text(chunk_size=None)`, `.aiter_lines()`, `.aiter_raw(chunk_size=None)`,
  `.aclose()`. Misuse raises `StreamConsumed` (double-stream), `StreamClosed`
  (read after close), `ResponseNotRead` (access `.content` before `read()` on a
  streamed response) — see §4.
- Streaming + context managers: `client.stream(...)` yields a `Response` usable as
  `with client.stream(...) as r:` (sync) / `async with` (async); or
  `client.send(req, stream=True)`. The streaming body must be consumed
  (`read()/aread()` or iteration) or closed (`close()/aclose()`).
  `Response(content=...)` auto-reads (`_models.py:545-552` — `self.read()` when the
  stream is a plain `ByteStream`); `Response(stream=...)` does not add
  content headers (comment at `_models.py:553-567`).
- `history`: on redirect-following sends, intermediate responses accumulate in
  `history` (`_send_handling_redirects`, `_client.py:930-971`:
  `history=history`, `response.history = list(history)`, `history.append(response)`).
  Verified live with `MockTransport`: no-redirect response has `history == []`.

## 4. Exception hierarchy (`_exceptions.py:1-32`, verbatim)

```
* HTTPError
  x RequestError
    + TransportError
      - TimeoutException
        · ConnectTimeout · ReadTimeout · WriteTimeout · PoolTimeout
      - NetworkError
        · ConnectError · ReadError · WriteError · CloseError
      - ProtocolError
        · LocalProtocolError · RemoteProtocolError
      - ProxyError
      - UnsupportedProtocol
    + DecodingError
    + TooManyRedirects
  x HTTPStatusError
* InvalidURL
* CookieConflict
* StreamError
  x StreamConsumed x StreamClosed x ResponseNotRead x RequestNotRead
```

- `HTTPError(message)` carries `.request` (get raises `RuntimeError` if unset,
  `:96-104`). `RequestError(message, *, request=None)`; client attaches the request
  via the `request_context` CM (`:366-379`).
- `HTTPStatusError(message, *, request, response)` — from `raise_for_status()`.
- `TimeoutException(TransportError)`; note the alias `Timeout` in `__all__` is the
  **config class**, not the exception — the timeout *exception* base is
  `TimeoutException` (name pair `Timeout`/`TimeoutException` both exported).
- `StreamError(RuntimeError)` — pure programming errors, not network failures.
- Practical catch: `except httpx.HTTPError` covers both transport failures and
  `raise_for_status()` errors (docstring example at `_exceptions.py:82-89`).

## 5. Transports / mounts customization (`_transports/`)

Files: `base.py, default.py, mock.py, wsgi.py, asgi.py`.

- `BaseTransport` (`base.py:14`): `handle_request(request) -> Response`,
  `close()`, sync CM support. `AsyncBaseTransport` (`base.py:65`):
  `handle_async_request(request)`, `aclose()`, async CM support.
- `HTTPTransport(verify=True, cert=None, trust_env=True, http1=True, http2=False,
  limits=Limits(100, 20, 5.0), proxy=None, uds=None, local_address=None,
  retries=0, socket_options=None)` (verified live) and `AsyncHTTPTransport`
  (same shape). `uds` = Unix-domain socket path; `local_address` = source bind IP.
- `MockTransport(handler)` (verified live `MockTransport(handler: SyncHandler |
  AsyncHandler)`; `mock.py:15` implements both sync and async base classes).
  Handler receives a `Request`, returns a `Response`. **Yes — fake transports can
  be injected for tests**, verified live end-to-end:
  ```python
  def h(req):
      return httpx.Response(200, json={"hello": "world"}, request=req)


  with httpx.Client(transport=httpx.MockTransport(h), base_url="https://example.org") as c:
      r = c.get("/x")  # 200 {'hello': 'world'}, history == []
  ```
  Sync handler in a sync `Client` works; in an `AsyncClient` the handler may be a
  plain or `async` function (`mock.py:29-43`: non-`Response` result is awaited).
  A sync function returning a `Response` also works in `AsyncClient`.
- `WSGITransport(app, raise_app_exceptions=True, script_name="",
  remote_addr="127.0.0.1", wsgi_errors=None)` and
  `ASGITransport(app, raise_app_exceptions=True, root_path="",
  client=("127.0.0.1", 123))` (both verified live) — route requests to in-process
  apps via `transport=` or `mounts=`.
- Custom transports: subclass `BaseTransport`/`AsyncBaseTransport` and implement
  `handle_request` / `handle_async_request`. Mount per-host:
  `Client(mounts={"https://provider-a.example": custom_transport})`.
  Mount keys are `URLPattern`s, sorted longest-first-ish (`dict(sorted(...))`).

## 6. Event hooks

```python
def on_request(request: httpx.Request): ...  # mutate/inspect before send
def on_response(response: httpx.Response): ...  # inspect after receive


client = httpx.Client(event_hooks={"request": [on_request], "response": [on_response]})
```

- Only the two keys `"request"` / `"response"` are kept
  (`_client.py:215-217`); anything else is silently dropped.
- Hooks are `EventHook = Callable[..., Any]`; sync clients call them plainly,
  async clients `await` them if awaitable (invoke sites `_client.py:976/981`,
  async `:1691/1696`). Request hooks can mutate the `Request` in place
  (e.g. inject headers); response hooks observe the `Response`.
- Mutable post-construction: `client.event_hooks = {...}` (setter re-normalises
  both keys, `_client.py:266-268`).

## 7. Auth / cookies / ancillary models

- `Cookies(cookies=None)` (`_models.py:1084`); accepts `Cookies | CookieJar |
  dict[str,str] | list[tuple]` (`CookieTypes`, `_types.py:52`). Methods
  (`_models.py:1101-1233`): `extract_cookies(response)`, `set_cookie_header(request)`,
  `set(name, value, domain="", path="/")`, `get(name, default=None, domain=None,
  path=None)` (raises `CookieConflict` on ambiguity), `delete(...)`,
  `clear(domain=None, path=None)`, `update(...)`, plus `__set/get/delitem__`.
  Client jar persists across requests; per-request `cookies=` merges
  (`_merge_cookies`).
- `Headers` (`_models.py:144+`): case-insensitive multi-dict; `get_list(key,
  split_commas=False)`, `multi_items()`, `encoding` get/set.
- `URL(url)` / `QueryParams` (`_urls.py`): `URL.copy_with(...)`,
  `is_relative_url`, `join()` semantics used by `_merge_url`.
- `codes` (`_status_codes.py`): `codes.OK == 200`, `codes.NOT_FOUND == 404`,
  `int(codes.ok) == 200` (all verified live); `codes.get_reason_phrase(200)`.
- `create_ssl_context(verify=True, cert=None, trust_env=True) -> SSLContext`
  (public, in `__all__`).
- Top-level `httpx.stream(...)` (`_api.py:124`) is a context manager mirroring
  `request()` args one-shot (no client reuse).

## 8. What httpx does that primp cannot

Context: primp 1.3.1 (`docs/reference/dep-primp.md`) is a Rust-backed client whose
exclusive value is browser TLS/HTTP2 fingerprint + header-order impersonation
(`impersonate='chrome_146'` etc.). Everything below is verified in the installed
httpx 0.28.1 sources and absent from the primp reference.

1. **Pluggable transports + `MockTransport` for fixture tests.**
   `MockTransport(handler)` (`_transports/mock.py:15`, signature verified live)
   works in both `Client` and `AsyncClient` and was exercised end-to-end (§5).
   primp has no `transport=` parameter at all — its constructor takes only
   scalar config (`verify`, `proxy: str`, timeouts…), so hermetic unit tests need a
   hand-rolled fake wrapper. httpx needs none.
2. **Per-provider routing via `mounts=` / `_transport_for_url`.**
   `mounts: Mapping[str, BaseTransport | None]` (`Client.__init__` signature,
   `_client.py:760`) with `URLPattern` keys, applied over the proxy map and sorted.
   primp supports exactly one global `proxy: str | None` and no per-request
   override — per-host routing is impossible.
3. **Redirect history.** httpx records every hop on `response.history`
   (`_models.py:541`, `_client.py:953-956`); primp exposes **no** `history`
   (dep-primp.md §1: "`max_redirects: int = 20`; **no response `history` is exposed**").
4. **Streaming iteration API.** `iter_bytes/iter_text/iter_lines/iter_raw` (+ async)
   with `close()/aclose()` and `client.stream()` CM (`_models.py:876-1073`).
   primp has only `stream: bool` on request and eager `bytes()/text()/json()` —
   no incremental iterators.
5. **Request/response event hooks.** `event_hooks={"request": [...], "response": [...]}`
   (`_client.py:215-217`) for header injection, logging, metrics. primp has no hook
   mechanism (only `headers_update()`).
6. **Structured timeout + pool limits.** `Timeout(connect, read, write, pool)`
   (`_config.py:86`) always propagated in `extensions["timeout"]`
   (`_client.py:377`); `Limits(max_connections, max_keepalive_connections,
   keepalive_expiry)` (`_config.py:173`). primp timeouts are flat floats
   (`timeout/connect_timeout/read_timeout`) with no pool concept.
7. **In-process app transports.** `WSGITransport`/`ASGITransport` (signatures §5)
   let tests or embedded use-cases serve requests without sockets. No primp equivalent.
8. **Environment proxy + `trust_env` semantics.** httpx reads `HTTP(S)_PROXY` /
   `ALL_PROXY` + `NO_PROXY` via `get_environment_proxies` (`_utils.py`) unless
   `trust_env=False` or an explicit `transport=` is given. primp takes only an
   explicit `proxy` string.

Conversely, httpx has **no** browser impersonation: no `impersonate=`,
no TLS-fingerprint control beyond `verify`/`SSLContext`, no `referer` auto-header,
no cookie-store toggle, no `https_only`/`dns_resolver` knobs. Keep primp for
fingerprint-sensitive fetches; use httpx for everything test-shaped,
routing-shaped, or streaming-shaped.

## App improvement opportunities

Every item cites the installed source + signature verified above. "Unverified"
means: not checked against the app codebase in this pass — flagged, not asserted.

1. **Replace any hand-rolled `FakeClient` with `MockTransport`. (Verified —
   viable.)** `MockTransport(handler: SyncHandler | AsyncHandler)`
   (`_transports/mock.py:15`) serves canned `httpx.Response(200, json=..., request=req)`
   through a real `Client`, exercising URL merging, cookie/auth merging, redirect
   handling, and `raise_for_status()` paths — proven working in the §5 live probe.
   If the app has a bespoke fake HTTP layer for fixture tests, delete it in favour
   of `Client(transport=MockTransport(handler))`. (Unverified: whether such a fake
   currently exists in the app — grep for it before acting.)
2. **Per-provider routing with `mounts=`. (Verified — viable.)** Anime sources fan
   out to multiple origins; `mounts={"https://host-a": transport_a, ...}`
   (`Client.__init__`, `_client.py:760` `_transport_for_url`) routes each host to
   its own transport (own proxy, limits, or mock) inside ONE client with ONE cookie
   jar and ONE `base_url` fallback. primp cannot do this (single global `proxy: str`).
   (Unverified: current provider count and whether per-host proxying is needed.)
3. **Streaming downloads via `client.stream()` + `iter_bytes`. (Verified — viable.)**
   `Client.stream(method, url, ...) -> Iterator[Response]` plus
   `Response.iter_bytes(chunk_size=None)` / `aiter_bytes` (`_models.py:884-1006`)
   allow chunk-wise writes for large media/artwork payloads instead of buffering
   full bodies. primp offers only `stream: bool` + eager readers. (Unverified:
   current max payload sizes / whether OOM or TTFB is a real problem.)
4. **Redirect-chain auditing with `response.history`. (Verified — viable.)**
   Each hop is a full `Response` (`_models.py:541`, `_client.py:953-956`); log or
   assert on chain length / landing host for providers that bounce through
   shorteners or consent pages. primp exposes no history at all. Cheap to add wherever
   `follow_redirects=True` is already used. (Unverified: whether any provider flow
   currently misbehaves across redirects.)
5. **Caching/retry/logging layers as transports or hooks. (Verified — viable.)**
   A `BaseTransport` wrapper (implement `handle_request`, `base.py:28`) or
   `event_hooks={"request": [...], "response": [...]}` (`_client.py:215-217`)
   composes caching, retry, or timing without touching call sites. `extensions`
   (`Mapping[str, Any]`, `_types.py:87`) can carry per-request cache keys / trace IDs
   (`_client.py:371-377` shows the timeout-injection pattern to copy).
   (Unverified: whether the app already has a cache layer worth reusing.)
6. **Deterministic offline tests with `WSGITransport`/`ASGITransport`. (Verified —
   viable.)** `WSGITransport(app, ...)` / `ASGITransport(app, ...)` (signatures §5)
   serve in-process apps through the real client stack. Only pays off if the app
   owns a WSGI/ASGI surface. (Unverified: it likely does not — treat as parked.)

What was checked and found **not** significant: `Proxy` per-scheme objects (covered
by `mounts=` instead), `create_ssl_context` (only matters if custom CA pinning is
needed — no evidence for that), `trust_env=False` hardening (one-line change, not
"significant"), top-level one-shot `httpx.get/post/...` (convenience only, no client
reuse — prefer a shared `Client`).
