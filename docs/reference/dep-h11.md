# h11 0.16.0 — public API reference (installed venv build)

> Compiled from the installed package
> (`.venv/Lib/site-packages/h11/`, version `0.16.0`, pure-Python, no networking code).
> Transitive dependency via `httpcore 1.0.9` (which is used by `httpx 0.28.1`).
> Every signature/behavior below verified against the installed source
> (`_connection.py`, `_events.py`, `_state.py`, `_readers.py`, `_writers.py`,
> `_headers.py`, `_receivebuffer.py`, `_util.py`) and live introspection via
> `uv run python` from `C:\Users\nwoki\ad-extensions\sources\animepahe-tv`.

## What h11 is / is not

`__init__.py:1-7`: "A highish-level implementation of the HTTP/1.1 wire protocol
(RFC 7230), containing no networking code at all". You feed it bytes via
`receive_data()` and pull events via `next_event()`; you push events via `send()`
and it returns bytes to write to the socket. All socket I/O lives in httpcore.

Public surface (`__init__.py:38-62`, `__all__`):

```python
Connection, NEED_DATA, PAUSED
ConnectionClosed, Data, EndOfMessage, Event, InformationalResponse, Request, Response
(
    CLIENT,
    CLOSED,
    DONE,
    ERROR,
    IDLE,
    MUST_CLOSE,
    SEND_BODY,
    SEND_RESPONSE,
    SERVER,
)
SWITCHED_PROTOCOL  # (MIGHT_SWITCH_PROTOCOL intentionally NOT re-exported)
ProtocolError, LocalProtocolError, RemoteProtocolError
PRODUCT_ID = "python-h11/0.16.0"
```

## Connection (`_connection.py:151-659`)

```python
Connection(our_role, max_incomplete_event_size=16384)
# verified live: inspect.signature -> (our_role: Type[Sentinel], max_incomplete_event_size: int = 16384) -> None
```

* `our_role` must be `h11.CLIENT` or `h11.SERVER`, else `ValueError`
  (`_connection.py:174-175`). httpcore always passes `h11.CLIENT`
  (`httpcore/_sync/http11.py:60-63`).
* `max_incomplete_event_size` (default `DEFAULT_MAX_INCOMPLETE_EVENT_SIZE = 16*1024`,
  `_connection.py:69`): cap on buffered bytes for an incomplete head
  (request/response line + headers). Exceeded → `RemoteProtocolError("Receive buffer
  too long", error_status_hint=431)` from `next_event()` (`_connection.py:484-490`).
* Key attributes: `our_role / their_role`, `our_state / their_state / states`
  (`{CLIENT: ..., SERVER: ...}`), `their_http_version: Optional[bytes]`,
  `client_is_waiting_for_100_continue: bool`,
  `they_are_waiting_for_100_continue` property, `trailing_data -> (bytes, bool)`.

Core methods (verified signatures live):

```python
def receive_data(self, data: bytes) -> None   # buffer inbound; b"" means EOF/closed
def next_event(self) -> Event | NEED_DATA | PAUSED
def send(self, event: Event) -> Optional[bytes]   # bytes, or None for ConnectionClosed
def send_with_data_passthrough(self, event) -> Optional[List[bytes]]
def start_next_cycle(self) -> None   # DONE+DONE -> IDLE+IDLE, else LocalProtocolError
def send_failed(self) -> None        # force our_state -> ERROR
```

* `receive_data(b"")` sets `_receive_buffer_closed = True`; passing non-empty data
  afterwards raises `RuntimeError` (`_connection.py:403-408`).
* `send(ConnectionClosed()) -> None`; all other events return `b"".join(...)`
  (`_connection.py:517-542`).
* `send_with_data_passthrough` preserves the exact `Data.data` object in the
  returned list for zero-copy `sendfile(2)` (`_connection.py:544-575`,
  `_writers.py:78-83`).
* Error effect: `send()` failure sets `our_state = ERROR`; `next_event()` failure
  sets `their_state = ERROR` (`_connection.py:496-501, 573-575`). Once `ERROR`,
  further `send`/`next_event` in that direction raises
  `LocalProtocolError("Can't send...")` / `RemoteProtocolError("Can't receive...")`.

`NEED_DATA` / `PAUSED` (`_connection.py:51-56`): `Sentinel` singletons (so
`type(x) is x` holds). `next_event()` returns `NEED_DATA` when more socket bytes
are needed, `PAUSED` when the peer is `DONE` but you haven't called
`start_next_cycle()` yet, or when in `MIGHT_SWITCH_PROTOCOL`/`SWITCHED_PROTOCOL`
(`_connection.py:410-436, 438-460`). Verified live: `NEED_DATA NEED_DATA`.

## Events (`_events.py`)

All frozen dataclasses, unhashable (`__hash__ = None`). Do not subclass.

```python
Request(*, method: bytes|str, target: bytes|str, headers, http_version=b"1.1")
InformationalResponse(*, headers, status_code: int in [100,200), http_version=b"1.1", reason=b"")
Response(*, headers, status_code: int in [200,1000), http_version=b"1.1", reason=b"")
Data(data: bytes, chunk_start=False, chunk_end=False)
EndOfMessage(*, headers=None)   # trailers; must be empty unless chunked
ConnectionClosed()              # no fields; EOF / half-close signal
```

* `headers` is `Headers` (sequence of `(lowercased-name, value)` byte pairs) or a
  list of `(str|bytes, str|bytes)` pairs; auto-`bytesify`d (ascii) unless
  `_parsed=True` (parser-internal path).
* `Request` enforces: HTTP/1.1 requires exactly one `Host` header
  (`Missing mandatory Host: header` / `Found multiple Host: headers`,
  `_events.py:112-119`); method/target validated against ABNF regexes
  (`Illegal method characters`, `Illegal target characters`).
* `InformationalResponse` rejects status outside `[100,200)`;
  `Response` rejects outside `[200,1000)` — both raise `LocalProtocolError`
  (`_events.py:206-211, 247-256`).
* `Data.chunk_start/chunk_end` are only meaningful on **received** events; they are
  ignored on `send()` (`_events.py:273-280`). Verified live on a chunked body:
  single `Data` arrived with `chunk_end=True`.
* Writers only ever send `HTTP/1.1` on the wire regardless of the event's
  `http_version` attribute; sending with `http_version != b"1.1"` raises
  `LocalProtocolError("I only send HTTP/1.1")` (`_writers.py:36-40, 44-48`).
  `Host` is always emitted first (`_writers.py:22-33`).

## State machine (`_state.py`)

Roles: `CLIENT`, `SERVER`. Per-role states: `IDLE`, `SEND_RESPONSE` (server only),
`SEND_BODY`, `DONE`, `MUST_CLOSE`, `CLOSED`, `ERROR`, plus
`MIGHT_SWITCH_PROTOCOL` / `SWITCHED_PROTOCOL` (CONNECT/Upgrade only).

Event-triggered table (`_state.py:196-227`), exactly as installed:

```
CLIENT: IDLE -> Request => SEND_BODY; ConnectionClosed => CLOSED
        SEND_BODY -> Data => SEND_BODY; EndOfMessage => DONE
        DONE/MUST_CLOSE/CLOSED -> ConnectionClosed => CLOSED
SERVER: IDLE -> ConnectionClosed => CLOSED; Response => SEND_BODY;
               (Request, CLIENT) => SEND_RESPONSE   # server observes client's Request
        SEND_RESPONSE -> InformationalResponse => SEND_RESPONSE; Response => SEND_BODY;
               (InformationalResponse, _SWITCH_UPGRADE) => SWITCHED_PROTOCOL;
               (Response, _SWITCH_CONNECT) => SWITCHED_PROTOCOL
        SEND_BODY -> Data => SEND_BODY; EndOfMessage => DONE
        DONE/MUST_CLOSE/CLOSED -> ConnectionClosed => CLOSED
```

State-triggered overlays (`_state.py:316-365` + table lines 235-246):

* `pending_switch_proposals` non-empty + client `DONE` → `MIGHT_SWITCH_PROTOCOL`
  (takes priority over `MUST_CLOSE`).
* `keep_alive == False` + role in `DONE` → `MUST_CLOSE` (both roles).
* Half-close coupling: `(CLOSED, DONE/IDLE/ERROR) -> SERVER=MUST_CLOSE`,
  `(DONE/IDLE/ERROR, CLOSED) -> CLIENT=MUST_CLOSE`.
* `start_next_cycle()` requires exactly `{CLIENT: DONE, SERVER: DONE}`, else
  `LocalProtocolError("not in a reusable state...")`; resets to `IDLE/IDLE`.

Verified live client flow (GET, keep-alive response `Content-Length: 5`):

```
IDLE/IDLE -> send(Request) -> SEND_BODY/SEND_RESPONSE
          -> send(EndOfMessage) -> DONE/SEND_RESPONSE
          -> next_event()=Response, Data, EndOfMessage -> DONE/DONE
          -> start_next_cycle() -> IDLE/IDLE
```

## Body framing (`_connection.py:93-141`, `_readers.py:235-250`, `_writers.py:136-145`)

`_body_framing(request_method, event)` returns one of
`("content-length", (n,))`, `("chunked", ())`, `("http/1.0", ())`:

1. Empty-body responses ignore headers: `204`, `304`, `HEAD` requests, and
   `CONNECT` with `2xx` → `("content-length", (0,))`.
2. `Transfer-Encoding` present (must be exactly `chunked`, else rejected at
   header-validation time) beats `Content-Length` → `("chunked", ())`.
3. `Content-Length` present → `("content-length", (int(...),))`.
4. Fallback: `Request` with no framing headers → length 0; `Response` with no
   framing headers → `("http/1.0", ())` i.e. body lasts until EOF.

Reader/writer pairs per framing:

| Framing | Reader (`_readers.py`) | Writer (`_writers.py`) |
|---|---|---|
| `content-length` | `ContentLengthReader`: yields `Data` until `n` bytes, then `EndOfMessage`; premature EOF → `RemoteProtocolError` via `read_eof` | `ContentLengthWriter`: overrun → `LocalProtocolError("Too much data...")`; short + `EndOfMessage` → `"Too little data..."`; any trailer → `"Content-Length and trailers don't mix"` |
| `chunked` | `ChunkedReader`: parses hex size line, yields `Data(chunk_start/chunk_end)`, `0`-size chunk + trailer lines → `EndOfMessage(headers=trailers)`; premature EOF → `RemoteProtocolError` | `ChunkedWriter`: each non-empty `Data` → `hexlen CRLF data CRLF`; `EndOfMessage(headers)` → `0 CRLF trailers CRLF` |
| `http/1.0` | `Http10Reader`: every `receive_data` yields `Data`; EOF (`read_eof`) yields `EndOfMessage` | `Http10Writer`: raw passthrough; trailers → `LocalProtocolError` |

Client relevance: requests with no body (plain GET) take the `("content-length",(0,))`
path, so `send(Request); send(EndOfMessage())` with no `Data` is the normal pattern
(httpcore `_send_request_body` always terminates with `EndOfMessage`,
`httpcore/_sync/http11.py:152-161`).

## Header rules & limits (`_headers.py`, `_abnf.py`)

* `Headers` stores `(raw_name, lower_name, value)` triples; iteration yields
  `(lower_name, value)`; `raw_items()` preserves original casing
  (`_headers.py:77-124`). httpcore uses `event.headers.raw_items()` to forward
  server casing (`httpcore/_sync/http11.py:190`).
* Validation on construction (`normalize_and_validate`, `_headers.py:152-206`):
  names/values ascii-validated; `Content-Length` must be digits, ≤20 digits
  (`CONTENT_LENGTH_MAX_DIGITS = 20`), all repeated values identical or
  `LocalProtocolError("conflicting Content-Length headers")`; at most one
  `Transfer-Encoding` header and its value must be exactly `chunked`
  (else `LocalProtocolError`, hint 501); obs-fold continuation lines merged.
* Only tuning knob: `Connection(max_incomplete_event_size=N)` — caps the
  request/response head buffer (line 59-69). No per-header-count or body-size cap
  exists in h11 itself.

## Keep-alive (`_connection.py:72-90, 299-308`)

```python
def _keep_alive(event) -> bool:  # _connection.py:84-90
    if b"close" in get_comma_header(event.headers, b"connection"):
        return False
    if getattr(event, "http_version", b"1.1") < b"1.1":
        return False
    return True
```

* Either side's `Connection: close`, or either side speaking `< 1.1`, latches
  `ConnectionState.keep_alive = False` (one-way latch via
  `process_keep_alive_disabled()`), forcing `DONE -> MUST_CLOSE` so the socket
  must close instead of being reused. HTTP/1.0 is therefore never reused
  (comment lines 80-83). Verified live: `Connection: close` response ends in
  `{CLIENT: MUST_CLOSE, SERVER: MUST_CLOSE}`.
* Response-side fixups (`_clean_up_response_headers_for_sending`, server role
  only): auto-adds `Transfer-Encoding: chunked` for unknown-length bodies to
  HTTP/1.1 peers, strips framing for HTTP/1.0 peers, and injects
  `Connection: close` when `keep_alive` is off.

## 100-continue, Upgrade/CONNECT

* `client_is_waiting_for_100_continue` set on `Request` with `Expect: 100-continue`
  (HTTP/1.1+ only, `_headers.py:275-282`), cleared on any
  `InformationalResponse`/`Response` or on client `Data`/`EndOfMessage`
  (`_connection.py:310-316`). Verified live: `True` after such a `Request`,
  `False` after `100 Continue`.
* `CONNECT` method or `Upgrade` request header registers `_SWITCH_CONNECT` /
  `_SWITCH_UPGRADE` proposals; server `101` or `2xx`-to-`CONNECT` moves to
  `SWITCHED_PROTOCOL`, after which h11 goes `PAUSED` and `trailing_data` exposes
  unconsumed bytes for the new protocol (`_connection.py:260-269, 354-362`).
  httpcore handles exactly these two cases by wrapping the socket in
  `HTTP11UpgradeStream` (`httpcore/_sync/http11.py:116-120, 351-368`).

## Errors (`_util.py:12-81`)

```python
class ProtocolError(Exception):  # abstract; .error_status_hint default 400
class LocalProtocolError(ProtocolError)    # raised by send() / event constructors
class RemoteProtocolError(ProtocolError)   # raised by next_event(); mapped by httpcore
```

Internally everything raises `LocalProtocolError`; `next_event()` converts via
`_reraise_as_remote_protocol_error()` (in-place `__class__` swap +
re-raise). httpcore maps them: `h11.LocalProtocolError -> httpcore.LocalProtocolError`
on send, `h11.RemoteProtocolError -> httpcore.RemoteProtocolError` on receive
(`httpcore/_sync/http11.py:144, 213`), with one special case: EOF before any
response bytes (`their_state == SEND_RESPONSE`) is re-raised as
`RemoteProtocolError("Server disconnected without sending a response.")`
(lines 229-231).

## How httpcore drives h11 (`httpcore/_sync/http11.py`, `httpcore 1.0.9`)

`HTTP11Connection` (`READ_NUM_BYTES = 64*1024`, `MAX_INCOMPLETE_EVENT_SIZE =
100*1024`, lines 44-45) owns `self._h11_state = h11.Connection(our_role=h11.CLIENT,
max_incomplete_event_size=100*1024)` (lines 60-63):

1. Send: `h11.Request(method, target=url.target, headers)` → `_send_event`
   (`send()` + `network_stream.write()`); stream each `request.stream` chunk as
   `h11.Data`; finish with `h11.EndOfMessage()` (lines 140-166).
2. Receive head: loop `_receive_event()` (i.e. `next_event()`, feeding
   `network_stream.read(64*1024)` on `NEED_DATA`) until `h11.Response`, skipping
   `1xx` except breaking on `101` (lines 170-194).
3. Receive body: `_receive_response_body` yields `bytes(event.data)` per `h11.Data`
   until `EndOfMessage` or `PAUSED` (lines 196-207).
4. Reuse: `_response_closed()` (lines 238-250) — only if
   `our_state is DONE and their_state is DONE` does it `start_next_cycle()` and
   mark pool-`IDLE` (setting `_expire_at = now + keepalive_expiry`); otherwise
   `close()`. Pool reuse additionally gated by `is_available()` (IDLE),
   `has_expired()` (keepalive timeout or server-initiated disconnect readable),
   `can_handle_request(origin)` (lines 268-286).
5. The async copy (`httpcore/_async/http11.py`) is structurally identical.

## App improvement opportunities

Scope: this app is an **app-level httpx/httpcore consumer** — it never touches h11
directly. Checked for exposed knobs: `h11.Connection.__init__`
(`_connection.py:167-171`), `HTTP11Connection` constants + `__init__`
(`httpcore/_sync/http11.py:44-63`), `ConnectionPool.__init__`
(`httpcore/_sync/connection_pool.py:52-54`), `httpx.Client.__init__` /
`httpx.Limits` (live signature). Findings:

1. **Tune keep-alive reuse via `httpx.Limits`, not h11.** h11's keep-alive logic
   (`_keep_alive`, `_connection.py:84-90`) and `start_next_cycle()`
   (`_state.py:356-365`) are fully automatic — no app knob. The reachable knobs are
   one layer up, and they are exposed: live `httpx.Client.__init__` defaults to
   `limits = Limits(max_connections=100, max_keepalive_connections=20,
   keepalive_expiry=5.0)`, which maps to `ConnectionPool.__init__(...,
   max_connections=10, max_keepalive_connections=None, keepalive_expiry=None, ...)`
   (`httpcore/_sync/connection_pool.py:52-54`) and per-connection
   `HTTP11Connection.__init__(origin, stream, keepalive_expiry)`
   (`httpcore/_sync/http11.py:47-52`). For a scraper issuing bursts of requests to
   the same origin, raising `keepalive_expiry` above the 5 s httpx default and
   ensuring `max_keepalive_connections` covers the concurrency level avoids a
   TCP+TLS handshake per burst. Evidence: `_response_closed()` only reuses when
   both h11 states reach `DONE` (`httpcore/_sync/http11.py:240-248`).
2. **Always fully consume or explicitly close response streams.** Reuse requires
   the body loop to run to `EndOfMessage`/`PAUSED`
   (`_receive_response_body`, `httpcore/_sync/http11.py:196-207`) followed by
   `_response_closed()` taking the `IDLE + start_next_cycle()` branch
   (lines 238-250). Abandoning a streamed response without `close()` forces the
   `else: self.close()` branch — the socket is discarded even though the server
   sent `keep-alive`. Concretely: use `with client.stream(...)` / read to EOF.
3. **Do not attempt to tune h11 framing or header limits from the app — they are
   hardcoded shut.** `max_incomplete_event_size` defaults to 16384 in h11
   (`_connection.py:69,167-171`) but httpcore hardcodes `100*1024` when
   constructing its `h11.Connection` (`httpcore/_sync/http11.py:44-45,60-63`)
   with no passthrough from `httpx.Limits` (live signature has only
   `max_connections / max_keepalive_connections / keepalive_expiry`). Likewise
   `READ_NUM_BYTES = 64*1024` (line 44) and the chunked/content-length/HTTP-1.0
   reader selection (`_readers.py:245-250`, `_writers.py:140-145`) have no public
   switch. If oversized-head failures (`431 Receive buffer too long`,
   `_connection.py:488-490`) ever appear in logs, the only fix is patching /
   subclassing the httpcore transport, not a supported option. Saying so
   explicitly: no header-limit knob is reachable from `httpx.Client`.
4. **Unverified (explicitly not claimed):** the async transport path
   (`httpcore/_async/http11.py`, `httpx.AsyncClient`) was read structurally but
   not live-exercised; proxy/CONNECT and `101 Upgrade` flows
   (`HTTP11UpgradeStream`, lines 351-368) were not probed against a live server;
   no throughput measurement was done, so no quantitative Keep-Alive saving is
   asserted. No other significant h11-level improvement exists for an app-level
   consumer — chunked encoding, `Host`-first emission, `100-continue` tracking,
   and `Connection: close` handling are all automatic inside h11/httpcore with no
   safe override.
