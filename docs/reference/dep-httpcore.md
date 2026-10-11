# httpcore 1.0.9 — complete public API (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/httpcore/`, pure-Python, `py.typed` present,
> version `1.0.9` from `__init__.py:134` and `httpcore-1.0.9.dist-info/METADATA`).
> Every signature below was verified live via
> `uv run --project . python -c "import httpcore, inspect"` or by reading the
> installed source file cited. httpx wiring verified against installed
> `httpx 0.28.1` (`httpx/_transports/default.py`, `httpx/_config.py`).
> Transitive status: `httpx-0.28.1.dist-info/METADATA` contains
> `Requires-Dist: httpcore==1.*`; neither `httpcore` nor `httpx` is a direct
> dependency in `pyproject.toml` (direct HTTP dep is `primp>=1.3.1`) and no
> file under `src/` imports `httpcore`/`httpx` (only
> `src/services/hls_proxy.py` imports `primp`).

`__all__` (`__init__.py:73-132`, 51 names):
`request, stream, Origin, URL, Request, Response, Proxy,
AsyncHTTPConnection, AsyncConnectionPool, AsyncHTTPProxy,
AsyncHTTP11Connection, AsyncHTTP2Connection, AsyncConnectionInterface,
AsyncSOCKSProxy, HTTPConnection, ConnectionPool, HTTPProxy,
HTTP11Connection, HTTP2Connection, ConnectionInterface, SOCKSProxy,
SyncBackend, AnyIOBackend, TrioBackend, AsyncMockBackend, AsyncMockStream,
MockBackend, MockStream, AsyncNetworkStream, AsyncNetworkBackend,
NetworkStream, NetworkBackend, default_ssl_context, SOCKET_OPTION,
ConnectionNotAvailable, ProxyError, ProtocolError, LocalProtocolError,
RemoteProtocolError, UnsupportedProtocol, TimeoutException, PoolTimeout,
ConnectTimeout, ReadTimeout, WriteTimeout, NetworkError, ConnectError,
ReadError, WriteError`.
(`AnyIOBackend`/`TrioBackend` are stub classes raising `RuntimeError` if the
optional dep is missing — `__init__.py:49-70`.)

## 1. Top-level functions (`_api.py`)

```python
def request(
    method: bytes | str,
    url: URL | bytes | str,
    *,
    headers: HeaderTypes = None,
    content: bytes | typing.Iterator[bytes] | None = None,
    extensions: Extensions | None = None,
) -> Response: ...

@contextlib.contextmanager
def stream(
    method: bytes | str,
    url: URL | bytes | str,
    *,
    headers: HeaderTypes = None,
    content: bytes | typing.Iterator[bytes] | None = None,
    extensions: Extensions | None = None,
) -> typing.Iterator[Response]: ...
```

- `request()` opens a throwaway `ConnectionPool()`, sends, reads and closes
  (`_api.py:40-47`, via `RequestInterface.request` which does
  `response.read()` in `try/finally: response.close()` —
  `_sync/interfaces.py:37-50`). No pooling benefit; one pool per call.
- `stream()` yields the response inside `pool.stream(...)` (`_api.py:86-94`).
  Body is NOT pre-read; caller must `response.read()` or iterate
  (`_api.py:67-69`).

## 2. Models (`_models.py`)

```python
class Origin:  # _models.py:161
    def __init__(self, scheme: bytes, host: bytes, port: int) -> None
    # equality is (scheme, host, port); str() -> "scheme://host:port"

class URL:  # _models.py:182
    def __init__(
        self,
        url: bytes | str = "",
        *,
        scheme: bytes | str = b"",
        host: bytes | str = b"",
        port: int | None = None,
        target: bytes | str = b"",
    ) -> None
    @property
    def origin(self) -> Origin  # fills default port per scheme

class Request:  # _models.py:316
    def __init__(
        self,
        method: bytes | str,
        url: URL | bytes | str,
        *,
        headers: HeaderTypes = None,
        content: bytes | typing.Iterable[bytes] | typing.AsyncIterable[bytes] | None = None,
        extensions: Extensions | None = None,
    ) -> None

class Response:  # _models.py:366
    def __init__(
        self,
        status: int,
        *,
        headers: HeaderTypes = None,
        content: ... | None = None,
        extensions: Extensions | None = None,
    ) -> None
    # sync: read() -> bytes, iter_stream(), close()
    # async: aread(), aiter_stream(), aclose()
    # .content raises RuntimeError until read/aread has run (_models.py:402-415)

class Proxy:  # _models.py:496
    def __init__(
        self,
        url: URL | bytes | str,
        auth: tuple[bytes | str, bytes | str] | None = None,
        headers: ... | None = None,
        ssl_context: ssl.SSLContext | None = None,
    )
```

- Verified live: `inspect.signature(httpcore.Request.__init__)` and
  `inspect.signature(httpcore.Response.__init__)` match the above.
- `URL(url)` string form parses via `urllib.parse.urlparse`; empty path
  becomes `b"/"`, query preserved (`_models.py:267-274`). Explicit
  `scheme/host/port/target` form supports targets unexpressible as strings
  (`OPTIONS *`, absolute-URI proxy targets — `_models.py:204-237`).
- `URL.origin` default ports (`_models.py:282-293`):
  `http 80, https 443, ws 80, wss 443, socks5/socks5h 1080`.
- `Request` accepts `extensions["target"]` to override the URL target
  (`_models.py:354-360`). `extensions["sni_hostname"]` overrides the TLS SNI
  hostname (`_sync/connection.py:107,151-152`).
- `extensions["timeout"]` is a dict with keys `connect/read/write/pool`
  (produced by `httpx.Timeout.as_dict()` — `httpx/_config.py:132-137`; consumed
  per §8). `extensions["trace"]` is a callback invoked as
  `trace("group.name", info)` for each traced event (`_trace.py:30-47`;
  sync callback must be a plain function, async must be a coroutine —
  `_trace.py:32-39,71-78`).
- `Proxy(auth=(user, pass))` prepends a `Proxy-Authorization: Basic ...`
  header (`_models.py:508-514`). `HTTPProxy` does the same from
  `proxy_auth` (`_sync/http_proxy.py:137-144`).
- Header/method/url coercion: `str` args must be ASCII-only or `TypeError`
  (`enforce_bytes`, `_models.py:19-38`).

## 3. ConnectionPool — sync + async (`_sync/connection_pool.py`, `_async/connection_pool.py`)

Verified live (`inspect.signature` on both):

```python
ConnectionPool(
    self,
    ssl_context: ssl.SSLContext | None = None,
    proxy: Proxy | None = None,                        # Proxy MODEL, not a URL
    max_connections: int | None = 10,
    max_keepalive_connections: int | None = None,
    keepalive_expiry: float | None = None,
    http1: bool = True,
    http2: bool = False,
    retries: int = 0,
    local_address: str | None = None,
    uds: str | None = None,
    network_backend: NetworkBackend | None = None,     # async: AsyncNetworkBackend | None
    socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
) -> None
```

(`AsyncConnectionPool.__init__` is identical except the `network_backend`
type; both pool files are 420 lines and structurally identical —
`AsyncConnectionPool` verified live, same defaults.)

Parameter semantics (source: `_sync/connection_pool.py:63-126`):

- `max_connections=10`: cap on total connections. `None` → `sys.maxsize`.
  A request beyond the cap stays queued until a connection frees
  (`_assign_requests_to_connections`, §3.1 case 3).
- `max_keepalive_connections=None` → `sys.maxsize`, then
  `min(max_connections, max_keepalive_connections)` (`:97-104`). Cap on
  **idle** connections; surplus idle connections are closed on every
  assign pass (`:292-299`).
- `keepalive_expiry=None` means **no time-based idle expiry** — `_expire_at`
  is only ever set `if self._keepalive_expiry is not None`
  (`_sync/http11.py:246-248`). Idle connections then live until the server
  disconnects (detected via readability probe, §5) or the idle cap / pool
  close kills them. Contrast httpx's default `keepalive_expiry=5.0` (§9).
- `http1=True, http2=False`. `http2=True` requires the `h2` package;
  **`h2` is NOT installed in this venv** (verified: `importlib.util.find_spec("h2") is None`),
  so constructing an HTTP/2 connection here raises `RuntimeError("Attempted
  to use http2 support, but the \`h2\` package is not installed...")`
  (`_sync/__init__.py:33-41`).
- `retries=0`: connect retries on `ConnectError`/`ConnectTimeout` with
  backoff factor `RETRIES_BACKOFF_FACTOR = 0.5` → delays `0, 0.5, 1, 2, 4…s`
  (`_sync/connection.py:19,110-165`).
- `local_address`: `"0.0.0.0"` forces IPv4, `"::"` forces IPv6
  (docstring `:83-86`, passed to `connect_tcp` `:119`).
- `uds`: unix-domain-socket path used *instead of* TCP (`:127-138`).
- `network_backend=None` → `SyncBackend()` (async: `AutoBackend`, §7).
- `proxy=Proxy(...)`: per-origin dispatch in `create_connection`
  (`_sync/connection_pool.py:128-166`): `socks5/socks5h` → `Socks5Connection`;
  `http` origin → `ForwardHTTPConnection`; anything else (https/ws/wss) →
  `TunnelHTTPConnection`.

Core methods (`RequestInterface`, `_sync/interfaces.py:20-84`):

```python
def request(self, method, url, *, headers=None, content=None, extensions=None) -> Response
def stream(self, method, url, *, headers=None, content=None, extensions=None) -> Iterator[Response]  # contextmanager
def handle_request(self, request: Request) -> Response
@property
def connections(self) -> list[ConnectionInterface]   # live pool inspection
def close(self) -> None                                # also __enter__/__exit__
def create_connection(self, origin: Origin) -> ConnectionInterface
```

### 3.1 Pool internals — how reuse works (`_sync/connection_pool.py:199-339`)

1. `handle_request` rejects schemes outside `http/https/ws/wss` with
   `UnsupportedProtocol` (empty scheme also rejected — `:205-213`).
2. Pool timeout: `timeout = request.extensions.get("timeout", {}).get("pool", None)`
   (`:215-216`); the request waits on its `PoolRequest` event with that timeout
   (`:232`) — expiry raises `PoolTimeout` from the synchronization layer
   (`_synchronization.py`, `map_exceptions` → `PoolTimeout`).
3. Each assign pass (`_assign_requests_to_connections`, `:270-339`):
   - drop `is_closed()` connections; close + drop `has_expired()` ones;
     close surplus idle beyond `max_keepalive_connections`;
   - for each queued request, keyed strictly by `request.url.origin`:
     1. reuse first `can_handle_request(origin) and is_available()`
        connection ("reusing existing connection");
     2. else if `len(connections) < max_connections`: create
        (`create_connection(origin)`);
     3. else if any idle connection exists (different origin): close it and
        create a new one for this origin. Otherwise the request keeps waiting.
4. The response is wrapped in `PoolByteStream` (`:261-268`). **The pool slot
   is released only when the stream is closed**: `PoolByteStream.close()`
   closes the inner stream, removes the `PoolRequest` from the queue and
   re-runs assignment (`:409-420`). `RequestInterface.request()` guarantees
   this via `try/finally: response.close()`; streaming callers must close
   (or exhaust + close) the response themselves or the connection leaks out
   of the pool until GC/`pool.close()`.

## 4. HTTPConnection — per-origin wrapper (`_sync/connection.py`, `_async/connection.py`)

```python
HTTPConnection(  # _sync/connection.py:39
    self,
    origin: Origin,
    ssl_context: ssl.SSLContext | None = None,
    keepalive_expiry: float | None = None,
    http1: bool = True,
    http2: bool = False,
    retries: int = 0,
    local_address: str | None = None,
    uds: str | None = None,
    network_backend: NetworkBackend | None = None,
    socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
) -> None
```

- Lazily connects on first `handle_request`; negotiates HTTP version by ALPN:
  `h2` selected (or `http2 and not http1`) → `HTTP2Connection`, else
  `HTTP11Connection` (`:77-98`). `is_available()` before connect returns True
  only if the result *could* be HTTP/2 (`:175-185`) — an HTTP/1.1-destined
  unconnected wrapper is not pool-reusable (second concurrent request raises
  `ConnectionNotAvailable` and the pool retries on another connection —
  `:236-246`).
- TLS: `default_ssl_context()` when `ssl_context is None`; ALPN set to
  `["http/1.1", "h2"]` iff `http2` else `["http/1.1"]` (`:140-147`).
- `ConnectionInterface` surface (`_sync/interfaces.py:87-137`):
  `handle_request, close, info, can_handle_request(origin),
  is_available, has_expired, is_idle, is_closed`, plus `__enter__/__exit__`
  for direct use (`_sync/connection.py:213-222`).

## 5. HTTP11Connection — single-flight keepalive (`_sync/http11.py`)

- Depends on `h11` (installed — `find_spec("h11")` true; `httpcore` metadata
  requires `h11>=0.16`).
- States `NEW=0, ACTIVE=1, IDLE=2, CLOSED=3` (`HTTPConnectionState`,
  `_sync/http11.py:36-41`). `READ_NUM_BYTES = 64*1024`,
  `MAX_INCOMPLETE_EVENT_SIZE = 100*1024` (`:44-45`).
- **One request at a time**: `is_available()` is `state == IDLE` only
  (`:267-272`; a `NEW` connection is usable by its creator but never
  acquired from the pool). Concurrent second request → `ConnectionNotAvailable`.
- Reuse path: `_response_closed()` returns the connection to `IDLE` (and
  calls `h11.Connection.start_next_cycle()`) **only if both sides are
  `h11.DONE`**; sets `_expire_at = monotonic() + keepalive_expiry` when
  configured; otherwise closes (`:238-250`).
- `has_expired()` (`:274-286`): time expiry (`now > _expire_at`) **or**
  server-initiated disconnect detected by `network_stream.get_extra_info("is_readable")`
  on an idle connection (readable ⇒ peer sent EOF ⇒ about to return `b""`).
- `info()` e.g. `'https://example.com:443', HTTP/1.1, IDLE, Request Count: 9`
  (`:294-299`); `pool.connections` exposes these for debugging.
- Timeouts consumed from `request.extensions["timeout"]`
  (`_sync/http11.py:141-142,153-154,173-174,199-200`): `write` for request
  send, `read` for response receive. Write errors while sending are swallowed
  to allow reading a pre-emptive error response (`:89-95`).

## 6. HTTP2Connection — multiplexed (`_sync/http2.py`, `_async/http2.py`)

Read from source (not importable here — `h2` absent):

- States `ACTIVE=1, IDLE=2, CLOSED=3` — no `NEW` (`_sync/http2.py:36-40`).
- `is_available()` while `ACTIVE or IDLE` unless stream-ID space exhausted or
  connection error (`_sync/interfaces.py:97-113` docstring; raises
  `ConnectionNotAvailable` past `get_next_available_stream_id()` —
  `_sync/http2.py:131-139`). Concurrency throttled by a semaphore seeded
  from the server's `max_concurrent_streams` (`:119-131`).
- Connection init (client preface + settings) sent once under `_init_lock`
  (`:104-117`); response extensions include `"http_version": b"HTTP/2"` and
  `"stream_id"` (`:155-163`).
- **Not usable in this venv**: `import httpcore._sync.http2` raises
  `ModuleNotFoundError: No module named 'h2'` (verified live); public import
  falls back to the `RuntimeError` stub (`_sync/__init__.py`).

## 7. Proxy transports

### 7.1 HTTPProxy (`_sync/http_proxy.py`, `_async/http_proxy.py`)

Verified live:

```python
HTTPProxy(  # _sync/http_proxy.py:59
    self,
    proxy_url: URL | bytes | str,
    proxy_auth: tuple[bytes | str, bytes | str] | None = None,
    proxy_headers: HeadersAsMapping | HeadersAsSequence | None = None,
    ssl_context: ssl.SSLContext | None = None,
    proxy_ssl_context: ssl.SSLContext | None = None,
    max_connections: int | None = 10,
    max_keepalive_connections: int | None = None,
    keepalive_expiry: float | None = None,
    http1: bool = True,
    http2: bool = False,
    retries: int = 0,
    local_address: str | None = None,
    uds: str | None = None,
    network_backend: NetworkBackend | None = None,
    socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
) -> None
```

- Subclasses `ConnectionPool`; `create_connection` dispatches **per origin**
  (`:146-166`): `http` origin → `ForwardHTTPConnection` (absolute-URI
  request line sent to `proxy_origin`, proxy headers merged with
  per-request headers winning — `:191-206`); other schemes →
  `TunnelHTTPConnection` (`CONNECT host:port` with `Host`+`Accept` merged
  with proxy headers, non-2xx → `ProxyError("status reason")` (`:265-297`),
  then `start_tls` to the remote origin with ALPN + h2/1.1 selection
  (`:299-340`)).
- `proxy_ssl_context` with an `http://` proxy URL raises `RuntimeError`
  (`:127-132`).
- `AsyncHTTPProxy` mirrors with `AsyncNetworkBackend`.

### 7.2 SOCKSProxy / Socks5Connection (`_sync/socks_proxy.py`)

```python
SOCKSProxy(  # _sync/socks_proxy.py:110 (same pool knobs as HTTPProxy minus proxy_headers/proxy_ssl_context)
    self, proxy_url, proxy_auth=None, ssl_context=None,
    max_connections=10, max_keepalive_connections=None, keepalive_expiry=None,
    http1=True, http2=False, retries=0, ...)
```

- SOCKS5 handshake (`_init_socks5_connection`, `:42-102`): auth-method
  negotiation → optional username/password → `CONNECT`; failures raise
  `ProxyError` (method mismatch, bad credentials, non-zero reply code with
  `REPLY_CODES` text). Requires `socksio==1.*`; **not installed here**
  (verified `find_spec("socksio") is None`) so `SOCKSProxy(...)` raises
  `RuntimeError(... pip install httpcore[socks] ...)` (`_sync/__init__.py`).
- Pool-level `proxy=Proxy(...)` with `socks5/socks5h` scheme routes to
  `Socks5Connection` per origin (`connection_pool.py:130-142`).

## 8. Network backends (`_backends/`)

Interface (`_backends/base.py`):

```python
SOCKET_OPTION = Union[Tuple[int,int,int], Tuple[int,int,Union[bytes,bytearray]], Tuple[int,int,None,int]]
class NetworkStream:
    def read(self, max_bytes: int, timeout: float | None = None) -> bytes
    def write(self, buffer: bytes, timeout: float | None = None) -> None
    def close(self) -> None
    def start_tls(self, ssl_context, server_hostname=None, timeout=None) -> NetworkStream
    def get_extra_info(self, info: str) -> Any   # "ssl_object" (ALPN), "is_readable" (server-EOF probe)
class NetworkBackend:
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None) -> NetworkStream
    def connect_unix_socket(self, path, timeout=None, socket_options=None) -> NetworkStream
    def sleep(self, seconds: float) -> None      # time.sleep
# AsyncNetworkStream / AsyncNetworkBackend mirror with async read/write/aclose/start_tls/sleep/connect_*.
```

Implementations:

- `SyncBackend` / `SyncStream` (`_backends/sync.py:120-...`): stdlib sockets;
  `socket.timeout` → `ReadTimeout`/`WriteTimeout`/`ConnectTimeout`,
  `OSError` → `ReadError`/`WriteError`/`ConnectError` via `map_exceptions`
  (`:9-20`). `TLSinTLSStream` (`:23-...) handles TLS-over-TLS (proxy CONNECT
  + https) via `MemoryBIO`. `start_tls` honours the `connect` timeout.
- `AutoBackend` (`_backends/auto.py`): async default; lazily picks
  `TrioBackend` vs `AnyIOBackend` via `sniffio.current_async_library()`
  (`_synchronization.py:current_async_library`). `anyio` IS installed,
  `trio` is NOT (verified via `find_spec`).
- `MockBackend(buffer, http2=False)` / `MockStream`
  (`_backends/mock.py:24-79`): scripted byte buffers for tests; `http2=True`
  fakes ALPN `h2` via `MockSSLObject`.
- `default_ssl_context()` (`_ssl.py:6-9`): `ssl.create_default_context()`
  + `certifi.where()` (certifi installed, verified).
- Sync pool thread-safety: pool mutation under `ThreadLock`
  (`connection_pool.py:126,218-232`); per-connection request locks; async
  uses `AsyncLock`/`AsyncEvent`/semaphores backed by anyio-or-trio
  (`_synchronization.py`).

## 9. Exception hierarchy (`_exceptions.py`)

```text
Exception
├── ConnectionNotAvailable          # pool/conn busy (NOT mapped by httpx — retried internally)
├── ProxyError                      # CONNECT rejected, SOCKS failure
├── UnsupportedProtocol             # bad/missing scheme
├── ProtocolError
│   ├── RemoteProtocolError         # peer violation, incl. "Server disconnected without sending a response"
│   └── LocalProtocolError          # our violation
├── TimeoutException
│   ├── PoolTimeout                 # waited > extensions["timeout"]["pool"] for a connection
│   ├── ConnectTimeout              # TCP/TLS establish
│   ├── ReadTimeout                 # response wait/read
│   └── WriteTimeout                # request send
└── NetworkError
    ├── ConnectError                # refused/DNS/unreachable (+ retryable per §3)
    ├── ReadError
    └── WriteError
```

(`_exceptions.py:18-81`.) `map_exceptions(mapping)` context manager
re-raises as the mapped type chaining `from exc` (`:7-15`).

## 10. Limits: what the knobs do, and httpx's plug-in

httpcore pool defaults (verified live §3): `max_connections=10`,
`max_keepalive_connections=None` (= unbounded up to `max_connections`),
`keepalive_expiry=None` (= never expire by age).

httpx overrides them (`httpx/_config.py:159-...`, verified live):

```python
Limits(self, *, max_connections: int | None = None,
       max_keepalive_connections: int | None = None,
       keepalive_expiry: float | None = 5.0) -> None
DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0)
DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)   # all four legs 5s
```

httpx→httpcore wiring (`httpx/_transports/default.py:135-259`, `300-...` async mirror):

- `HTTPTransport(verify, cert, trust_env, http1=True, http2=False,
  limits=DEFAULT_LIMITS, proxy=None, uds, local_address, retries=0,
  socket_options)` — `proxy is None` → `httpcore.ConnectionPool(...)`;
  scheme `http/https` → `httpcore.HTTPProxy(proxy_url=URL(scheme, host, port,
  target), proxy_auth, proxy_headers, ssl_context, proxy_ssl_context, ...pool
  knobs...)`; `socks5/socks5h` → `httpcore.SOCKSProxy(...)` (requires
  `socksio`, else `ImportError`); else `ValueError`. `trust_env=False` (or an
  explicit `transport=`) disables environment-proxy pickup (`httpx/_client.py`).
- Per request, httpx builds `httpcore.Request(method, URL(scheme, host, port,
  target), headers, content, extensions)` and passes its extensions through
  (`:237-248`) — including `timeout=Timeout(...).as_dict()` =
  `{"connect","read","write","pool"}` (`httpx/_client.py:371-377,584-591`;
  `httpx/_config.py:132-137`).
- Exception translation (`:74-118`): every httpcore error except
  `ConnectionNotAvailable` maps 1:1 to the same-named `httpx.*` error, most
  specific first (e.g. `httpcore.ReadTimeout` → `httpx.ReadTimeout`, not the
  generic `TimeoutException`).
- Response path wraps `resp.stream` in an httpx `ResponseStream` that re-maps
  errors on iteration (`:121-132`); extensions (`http_version`,
  `reason_phrase`, `network_stream`) are passed through (`:254-259`).
- httpx pins `httpcore==1.*` (`httpx-0.28.1.dist-info/METADATA`).

Timeout-leg consumption (httpcore side): `pool` → `PoolRequest.wait_for_connection`
(`connection_pool.py:215-216,232`); `connect` → `connect_tcp`/`connect_unix_socket`
+ `start_tls` (`connection.py:106-108,116-157`; proxy `http_proxy.py:266-267`);
`write` → h11/h2 send (`http11.py:141-154`); `read` → h11/h2 receive
(`http11.py:173-174,199-200`).

## 11. What matters for this app today

- **No direct dependency.** `src/` never imports `httpcore`/`httpx`; upstream
  media fetching uses `primp.AsyncClient(impersonate="chrome", timeout=20.0)`
  (`src/services/hls_proxy.py:167-170`) because stream hosts 403 plain-httpx
  clients. `httpcore` ships only as `httpx`'s transitive engine
  (`httpcore==1.*` pin). Everything below applies when/if httpx (hence
  httpcore) is used — e.g. metadata/API calls — not to the current primp
  media path.
- **Connection reuse for many small API calls.** Reuse is per-`Origin`
  (scheme+host+port) and pool-scoped (§3.1): same-origin sequential calls
  reuse one IDLE HTTP/1.1 connection; distinct origins each hold their own
  connection; concurrency beyond `max_connections` queues (bounded only by
  the `pool` timeout). One shared client/transport = one pool = reuse;
  a pool (or httpx client) per request = zero reuse.
- **HTTP/1.1 is single-flight** (`is_available` ⇔ IDLE, §5): N concurrent
  same-origin requests need N connections (up to `max_connections`), then queue.
- **Keepalive defaults differ by layer**: raw `ConnectionPool` never expires
  idle connections by age (`keepalive_expiry=None`, §3); httpx applies
  `keepalive_expiry=5.0` + idle cap 20 (§10). Stale-idle risk on a raw pool
  is mitigated only by the server-EOF readability probe (`has_expired`, §5).
- **Proxy shape** is pool-level, one proxy per pool (`HTTPProxy(proxy_url,
  proxy_auth, proxy_headers, proxy_ssl_context)`; `Forward` for http origins,
  `CONNECT`-tunnel for everything else, §7.1; SOCKS additionally needs
  `socksio`, absent here, §7.2). httpx adds per-scheme `mounts` on top.
- **Timeouts are a 4-leg dict** (`connect/read/write/pool`, §10) carried in
  `request.extensions["timeout"]`; each leg is enforced at a different layer.
  A single float (httpx `Timeout(5.0)`) sets all four.

## 12. App improvement opportunities

Each item cites the verified source + signature it rests on. "Unverified"
items are listed separately with what would be needed to verify.

1. **Share one httpx client (one pool) for provider API calls instead of
   per-call clients.** Reuse only happens inside a single pool's assign pass
   (`_sync/connection_pool.py:270-339`, case 1 "reusing existing connection",
   keyed by `request.url.origin`); `httpcore.request()`-style throwaway pools
   (`_api.py:40-47`) or a new `httpx.Client` per call can never hit case 1.
   With several small metadata calls per screen, one long-lived client turns
   N handshakes into ~1 per origin (plus spares under concurrency).
2. **Set explicit `Limits` / `keepalive_expiry` rather than raw-pool defaults.**
   `ConnectionPool.__init__` defaults `keepalive_expiry=None`
   (`_sync/connection_pool.py:48-62`, verified live) and `_expire_at` is only
   set `if self._keepalive_expiry is not None`
   (`_sync/http11.py:246-248`), so a directly-used pool keeps idle sockets
   indefinitely (server-EOF probe aside — `_sync/http11.py:274-286`).
   httpx's `Limits(max_connections=100, max_keepalive_connections=20,
   keepalive_expiry=5.0)` (`httpx/_config.py`, verified live
   `DEFAULT_LIMITS`) is the sane template: idle cap + 5 s expiry bounds stale
   sockets when fanning out over providers.
3. **Always fully read or explicitly close responses (or use
   `client.stream()` as a context manager).** The pool slot frees only in
   `PoolByteStream.close()` — removes the `PoolRequest`, re-runs assignment
   (`_sync/connection_pool.py:409-420`); `RequestInterface.request()`
   guarantees it via `try/finally: response.close()`
   (`_sync/interfaces.py:37-50`), but streaming callers that abandon a
   response starve the pool (queued requests pile up behind
   `max_connections`). Lint for unclosed streamed responses on the
   provider-call path.
4. **Give the fan-out a `pool` timeout so overload fails fast instead of
   hanging.** Queue wait uses `request.extensions["timeout"]["pool"]`
   (`_sync/connection_pool.py:215-216,232`); without it (or httpx
   `Timeout(pool=None)`) a burst past `max_connections` blocks forever.
   httpx default `Timeout(timeout=5.0)` sets all four legs including `pool`
   (verified live `DEFAULT_TIMEOUT_CONFIG`); keep an explicit `pool=...`
   when raising the other legs.
5. **Do not enable `http2=True` here.** It requires the `h2` package, which
   is not installed (`import httpcore._sync.http2` → `ModuleNotFoundError`,
   verified live; stub raises `RuntimeError` — `_sync/__init__.py:33-41`),
   and multiplexing only helps concurrent same-origin load
   (`HTTP2Connection` semaphore/available logic — `_sync/http2.py:119-139`).
   Small sequential provider calls over HTTP/1.1 keepalive gain nothing from it.
6. **If a proxy is ever needed, model it as one pool per proxy URL.**
   `HTTPProxy.__init__(proxy_url, proxy_auth, proxy_headers,
   proxy_ssl_context, ...pool knobs...)` (`_sync/http_proxy.py:59-76`,
   verified live) with `ForwardHTTPConnection` for `http` origins
   (`:146-155`) and `CONNECT`-tunnel + `ProxyError` on non-2xx for the rest
   (`:156-166,292-297`); `proxy_ssl_context` with an `http://` proxy URL is
   rejected (`:127-132`). httpx scheme dispatch + `trust_env` env-proxy rules
   sit on top (`httpx/_transports/default.py:155-215`, `httpx/_client.py`).
   SOCKS is unavailable without adding `socksio` (verified absent; stub —
   `_sync/__init__.py`).

Unverified (explicitly NOT claimed — would need app-side measurement):

- Provider fan-out shape (origins, concurrency, call sizes): `src/` was only
  spot-checked (`hls_proxy.py`); the "5 providers" call pattern was not
  audited, so no sizing (pool size, per-host caps) is recommended here.
- Whether `primp` (the actual media client) pools/TLS-caches like httpcore:
  primp is a separate engine, out of scope for this reference; its reuse
  behavior was not studied.
- Provider server idle timeouts: the right `keepalive_expiry` below httpx's
  5 s default depends on the servers' keepalive, which needs live probing.
- Nothing else significant found: `retries` (connect-only,
  `_sync/connection.py:110-165`), `local_address`/`uds`/`socket_options`
  plumbing, `MockBackend` test hooks (`_backends/mock.py`), and the
  `trace` extension (`_trace.py`) offer no further leverage for this app's
  traffic shape.
