# msgpack 1.2.1 — public API reference (installed venv build)

> Compiled from the installed package
> (`.venv/Lib/site-packages/msgpack/`, version `1.2.1`, `Requires-Python: >=3.10`,
> Apache-2.0). Package ships a C extension (`_cmsgpack.cp313-win_amd64.pyd`) plus a
> pure-Python fallback (`fallback.py`). Every signature/behavior below verified
> against the installed source and live introspection via `uv run python`.

## Module layout / import dispatch

`__init__.py` (lines 11–17):

```python
if os.environ.get("MSGPACK_PUREPYTHON"):
    from .fallback import Packer, Unpacker, unpackb
else:
    try:
        from ._cmsgpack import Packer, Unpacker, unpackb
    except ImportError:
        from .fallback import Packer, Unpacker, unpackb
```

So `MSGPACK_PUREPYTHON=1` forces the pure-Python implementation; otherwise the C
extension is preferred. Verified live: C ext present (`import msgpack._cmsgpack`
succeeds), `type(msgpack.Packer).__module__ == 'builtins'`.

## Top-level API (`__init__.py`, lines 20–55)

```python
def pack(o, stream, **kwargs)      # Packer(**kwargs).pack(o) -> stream.write(...)
def packb(o, **kwargs)             # Packer(**kwargs).pack(o) -> bytes
def unpack(stream, **kwargs)       # unpackb(stream.read(), **kwargs); raises ExtraData on trailing bytes
load = unpack;  loads = unpackb    # aliases for pickle/simplejson compat
dump = pack;    dumps = packb
```

`unpackb` itself is imported from `_cmsgpack` (C) or `fallback` — the fallback
version (`fallback.py:72–94`): feeds `packed` into `Unpacker(None,
max_buffer_size=len(packed))`, raises `ValueError("Unpack failed: incomplete
input")` on truncation, `ExtraData(unpacked, extra)` on trailing bytes,
`FormatError` on invalid bytes, `StackError` on over-nesting.

Also exported: `Packer`, `Unpacker`, `ExtType`, `Timestamp`, and everything from
`exceptions.py`; `version = (1, 2, 1)`, `__version__ = "1.2.1"`.

## Packer (`fallback.py:610–939`; C version same options)

```python
Packer(*, default=None, use_single_float=False, autoreset=True,
       use_bin_type=True, strict_types=False, datetime=False,
       unicode_errors=None, buf_size=None)
```

| Option | Default | Meaning (source) |
|---|---|---|
| `default` | `None` | Callable converting unknown types to packable builtins (simplejson-style). Must be callable or `TypeError`. Called at most once per object (`default_used` flag, `fallback.py:796`). |
| `use_single_float` | `False` | Pack `float` as 4-byte `float32` (`0xCA`) instead of 8-byte `float64` (`0xCB`). |
| `autoreset` | `True` | `pack()` returns `bytes` and clears the buffer. If `False`, use `.bytes()` / `.getbuffer()` to read and `.reset()` to clear. |
| `use_bin_type` | `True` | `bytes` → bin family (`0xC4/0xC5/0xC6`); `str` may use str8 (`0xD9`). If `False`, bytes fall back to legacy raw headers (`_pack_bin_header` → `_pack_raw_header`, line 911–913). |
| `strict_types` | `False` | Exact-type checking: subclasses of serializable types go to `default`, and `tuple` is NOT packed as list (only `list` is). |
| `datetime` | `False` | tz-aware `datetime` → Timestamp ext (`-1`) via `Timestamp.from_datetime`. Naive datetime raises `ValueError("Cannot serialize ... where tzinfo=None")` when `datetime=True` (line 801–802). |
| `unicode_errors` | `'strict'` | Error handler for `str.encode('utf-8', ...)`. |
| `buf_size` | `None` | Internal buffer size; C implementation only (ignored by fallback). |

Methods: `.pack(obj)`, `.pack_map_pairs(pairs)`, `.pack_array_header(n)`,
`.pack_map_header(n)`, `.pack_ext_type(typecode, data)` (`typecode` 0–127,
`data: bytes`), `.bytes()`, `.reset()`, `.getbuffer()`.
Nesting beyond `DEFAULT_RECURSE_LIMIT = 1024` raises `ValueError("recursion limit
exceeded")`. `int` outside uint64/int64 range (without `default`) raises
`OverflowError("Integer value out of range")`; anything else unserializable
raises `TypeError(f"Cannot serialize {obj!r}")`.

Type mapping (verified live roundtrip: `{'a':1,'s':'héllo','bin':b'\x00\xff'}`
→ 30 bytes with a datetime field): `None→nil`, `bool→bool`, `int→int family`,
`float→double`, `str→raw/str`, `bytes/bytearray/memoryview→bin`,
`list/tuple→array`, `dict→map`, `ExtType/Timestamp→ext`.

## Unpacker — streaming (`fallback.py:130–607`)

```python
Unpacker(file_like=None, *, read_size=0, use_list=True, raw=False,
         timestamp=0, strict_map_key=True, object_hook=None,
         object_pairs_hook=None, list_hook=None, unicode_errors=None,
         max_buffer_size=100*1024*1024, ext_hook=ExtType,
         max_str_len=-1, max_bin_len=-1, max_array_len=-1,
         max_map_len=-1, max_ext_len=-1)
```

(Live signature printed by `inspect.signature(fallback.Unpacker.__init__)` —
identical to the above.)

| Option | Default | Meaning (source) |
|---|---|---|
| `file_like` | `None` | Object with `.read(n)`; when given, the unpacker pulls from it and `.feed()` is unusable (`_feeding=False`). `None` = feed mode. |
| `read_size` | `0` → `min(max_buffer_size, 16*1024)` | Chunk size for `file_like.read()`. `ValueError` if `read_size > max_buffer_size`. |
| `use_list` | `True` | Array → `list`; `False` → `tuple`. |
| `raw` | `False` | `True`: raw bytes stay `bytes`. `False` (default): decoded to `str` via UTF-8. Verified live: `unpackb(packb('hi'), raw=True) == b'hi'`. |
| `timestamp` | `0` | Ext `-1` decodes as: `0` → `Timestamp`, `1` → `float` (epoch seconds, `to_unix()`), `2` → `int` (epoch nanos, `to_unix_nano()`), `3` → `datetime.datetime` UTC (`to_datetime()`). Other values → `ValueError`. Verified: `timestamp=3` yields tz-aware UTC datetime. |
| `strict_map_key` | `True` | Only `str`/`bytes` allowed as map keys, else `ValueError("<type> is not allowed for map key")`. `str` keys are `sys.intern`ed. |
| `object_hook` | `None` | Callable applied to each unpacked dict. Mutually exclusive with `object_pairs_hook` (`TypeError` if both). |
| `object_pairs_hook` | `None` | Callable applied to the key-value-pair generator (e.g. `OrderedDict`). |
| `list_hook` | `None` | Callable applied to each unpacked array. Must be callable or `TypeError`. |
| `unicode_errors` | `'strict'` | Error handler for raw→UTF-8 decode; use for data with invalid UTF-8. |
| `max_buffer_size` | `100*1024*1024` (100 MiB) | Cap on buffered-but-undecoded bytes; exceeding raises `BufferFull`. `0` means 2**31-1. Set this for untrusted input. |
| `ext_hook` | `ExtType` | `callable(code, data) -> object` for ext types (except `-1`/timestamp). Must be callable. |
| `max_str_len` / `max_bin_len` / `max_array_len` / `max_map_len` / `max_ext_len` | `-1` → derived from `max_buffer_size` (`max_map_len` defaults to `max_buffer_size // 2`) | Per-type length caps; exceeding raises `ValueError("<n> exceeds max_*_len(...)")`. `max_str_len`/`max_bin_len`/`max_ext_len` are deprecated in favor of `max_buffer_size`. |

Streaming pattern (from the class docstring, lines 202–217):

```python
unpacker = Unpacker()                       # or Unpacker(file_like)
while True:
    buf = sock.recv(1024**2)
    if not buf: break
    unpacker.feed(buf)                      # raises BufferFull if over max_buffer_size
    for o in unpacker:                      # __next__ consumes; StopIteration on OutOfData
        process(o)
```

Other methods: `.unpack()` (single object), `.skip()` (discard next object),
`.read_array_header()` / `.read_map_header()` (return element counts for manual
looping), `.read_bytes(n)`, `.tell()` (stream offset).

## ExtType / Timestamp (`ext.py`)

```python
class ExtType(namedtuple("ExtType", "code data"))  # code: int 0..127, data: bytes
class Timestamp:  # immutable-ish; __slots__ = ["seconds", "nanoseconds"]
    Timestamp(seconds: int, nanoseconds: int = 0)   # ns must satisfy 0 <= ns < 10**9
    Timestamp.from_unix(sec: int|float) / .to_unix() -> float
    Timestamp.from_unix_nano(ns: int)   / .to_unix_nano() -> int
    Timestamp.from_datetime(dt)         / .to_datetime() -> UTC datetime
    Timestamp.from_bytes(b)             / .to_bytes()     # 4/8/12-byte payloads, ext code -1
```

Verified live: `unpackb(packb(ExtType(5, b'xy')))` → `ExtType(code=5, data=b'xy')`.

## Exceptions (`exceptions.py`)

```python
class UnpackException(Exception)        # base; NOTE: unpack may raise non-UnpackException errors too
class BufferFull(UnpackException)       # max_buffer_size exceeded
class OutOfData(UnpackException)        # truncated input (streaming path)
class FormatError(ValueError, UnpackException)  # invalid bytes, incl. "Unknown header: 0x.."
class StackError(ValueError, UnpackException)   # too nested (also from RecursionError)
class ExtraData(ValueError):            # one-shot unpack with trailing bytes; .unpacked / .extra attrs
UnpackValueError = ValueError           # deprecated alias
PackException = Exception; PackValueError = ValueError; PackOverflowError = OverflowError  # deprecated aliases
```

## Why flet depends on it

`flet-0.85.3.dist-info/METADATA` declares:

```
Requires-Dist: msgpack>=1.1.0
```

msgpack is flet's **Python ↔ Dart client wire protocol** (binary MessagePack
frames over socket / Pyodide bridge), in `flet/messaging/`:

* `flet/messaging/protocol.py:6` — `import msgpack`; `configure_encode_object_for_msgpack(control_cls)`
  builds the `default=` callback for `packb`: dataclasses → pruned dicts (sparse
  non-default props, `on_*` handlers → `True`), `Enum` → `.value`, naive
  datetimes localized then normalized to UTC → `ExtType(1, isoformat)`,
  `datetime.time` → `ExtType(2, "HH:MM")`, `Duration` → `ExtType(3, microseconds)`,
  callables rejected. `decode_ext_from_msgpack(code, data)` reverses codes 1–4
  (4 = plain UTF-8 string); unknown codes returned as `ExtType`.
* `flet/messaging/flet_socket_server.py:258` — `unpacker =
  msgpack.Unpacker(ext_hook=decode_ext_from_msgpack)` in `__receive_loop`, fed
  with 1 MiB `reader.read()` chunks and iterated per message; `:399` —
  `msgpack.packb([message.action, message.body], default=...)` in `send_message`.
* `flet/messaging/pyodide_connection.py:79,180` — same pair for the Pyodide/JS
  bridge: `msgpack.unpackb(data.to_py(), ext_hook=...)` inbound,
  `msgpack.packb([message.action, message.body], ...)` outbound.
* Frame shape: `[action_code, body]` where `action_code` is `ClientAction`
  (`protocol.py:225`: 1 REGISTER_CLIENT, 2 PATCH_CONTROL, 3 CONTROL_EVENT,
  4 UPDATE_CONTROL_PROPS, 5 INVOKE_METHOD, 6 SESSION_CRASHED, 7 PYTHON_OUTPUT);
  the enum docstring notes values must stay in sync with Dart `MessageAction`.

Correction to the assignment premise: flet's **pub-sub is NOT msgpack** —
`flet/pubsub/pubsub_hub.py` imports only `asyncio/inspect/logging/threading/...`
(no msgpack); it is an in-process hub. msgpack covers the client↔server
transport (socket server + Pyodide connection), not the pub-sub channel.

## What our app could use it for

* **Binary cache payloads**: `packb`/`unpackb` are already on the dependency
  tree (transitive via flet, no new requirement). Any dict/list/str/bytes/int
  cache entries (e.g. scraped episode lists, search results) serialize smaller
  and faster than JSON, with native `bytes` support (`use_bin_type=True`
  default) — useful for disk/memory caches of HTTP bodies or thumbnails.
* **Ext types for domain objects**: `ExtType` + `ext_hook` (same pattern as
  flet's codes 1–4) can round-trip datetimes/durations without string munging;
  `Packer(default=...)` / `Unpacker(object_hook=...)` give custom-class hooks.
* **Streaming socket/file decode**: `Unpacker.feed` + iteration, or
  `read_array_header`/`read_map_header` for large arrays without materializing
  everything, with `max_buffer_size` as the untrusted-input guard.
* Caveats: msgpack is **not** a security boundary — still validate unpacked
  data; keep `strict_map_key=True` and set `max_buffer_size` when unpacking
  anything from the network. C extension is present here, but code must also
  work under `MSGPACK_PUREPYTHON` (same API, slower).
