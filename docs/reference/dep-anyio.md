# anyio 4.14.1 — complete public API for asyncio apps (installed venv build)

> Reference compiled from the installed package
> (`.venv/Lib/site-packages/anyio/`, `anyio-4.14.1.dist-info/METADATA`) —
> every statement verified against the installed source. Backend covered is
> `asyncio` (`anyio/_backends/_asyncio.py`); trio backend present but out of scope.

## 0. Version, install position, dependencies

`Name: anyio, Version: 4.14.1, Requires-Python: >=3.10 (classifiers list 3.10–3.13), MIT`
(`anyio-4.14.1.dist-info/METADATA` lines 1–6).

`Requires-Dist` (verified live via `importlib.metadata.requires('anyio')`):
`exceptiongroup>=1.0.2; python_version < "3.11"`, `idna>=2.8`,
`typing_extensions>=4.5; python_version < "3.13"`, `trio>=0.32.0; extra == "trio"`.

Dependency chain (verified live):
`requires('flet')` contains `httpx>=0.28.1; platform_system != "Emscripten"`;
`requires('httpx')` contains `anyio`. So in this project anyio is **transitive via
flet → httpx → anyio**.

Notable environment fact (verified live in project venv):
`sniffio` is **NOT installed** (`.venv/Scripts/python.exe -c "import sniffio"` →
`ModuleNotFoundError`). Consequence — `anyio/_core/_eventloop.py:211-227`
`current_async_library()` takes the `sniffio is None` branch and assumes
`asyncio` if `asyncio.get_running_loop()` succeeds, else `None`. `get_async_backend()`
with no running loop raises `NoEventLoopError`. `set_current_async_library` /
`reset_current_async_library` are no-ops without sniffio.

`BACKENDS = "asyncio", "trio"` (`_core/_eventloop.py:29`). `get_all_backends()`,
`get_available_backends()` (added 4.12), `run(func, *args, backend="asyncio",
backend_options=None)` — `run()` raises `RuntimeError` if a loop already runs in
this thread, `LookupError` for unknown/unavailable backend.

Package layout (installed): `__init__.py`, `lowlevel.py`, `to_thread.py`,
`from_thread.py`, `to_process.py`, `to_interpreter.py`, `functools.py`,
`itertools.py`, `pytest_plugin.py`, `_core/` (14 modules), `_backends/
(_asyncio.py, _trio.py)`, `abc/`, `streams/`.

Two names the assignment mentions that **do not exist** in this package
(verified by grep + `dir(anyio)`):

- `anyio.Queue` — `hasattr(anyio, 'Queue')` is `False`; `grep -rn "class.*Queue"
  anyio/` returns nothing. The queue equivalent is
  `anyio.create_memory_object_stream()` (section 9).
- `ShieldCancellation` exception — `grep -rn "ShieldCancellation" anyio/` returns
  nothing. Shielding is a **boolean flag** `CancelScope(shield=...)`, not an
  exception type. On asyncio the cancellation exception is always
  `asyncio.CancelledError` (`cancelled_exception_class()` returns `CancelledError`,
  `_backends/_asyncio.py:2446-2448`).

## 1. Task groups

Factory: `anyio.create_task_group() -> TaskGroup` (`_core/_tasks.py:194-204`).
Dispatches to `get_async_backend().create_task_group()`; raises `NoEventLoopError`
with no running loop. On asyncio returns `TaskGroup()` (`_asyncio.py:2511-2513`).

`TaskGroup` ABC (`abc/_tasks.py:75-209`): attribute `cancel_scope: CancelScope`
inherited by all child tasks. Methods:

```python
tg.cancel(reason: str | None = None) -> None          # 4.14.0; shortcut for tg.cancel_scope.cancel()
tg.create_task(coro, *, name=None, context=None) -> TaskHandle  # 4.14.0 abstract; coro must be a Coroutine (TypeError + coro.close() otherwise)
tg.start_soon(func, *args, name=None) -> TaskHandle    # 4.14.0 now returns a handle
await tg.start(func, *args, name=None, return_handle=False) -> Any | TaskHandle
async with create_task_group() as tg: ...
```

Rules enforced by the asyncio implementation (`_asyncio.py:755-967`):

- `async with` entry twice → `RuntimeError("TaskGroup cannot be entered more than once")`.
- `create_task` / `start` on a non-entered or already-exited group (or after its
  `cancel_scope` deactivated) → closes the coro and raises
  `RuntimeError("This task group is not active; no new tasks can be started.")`.
- `start()` requires the target to accept a `task_status` keyword; if the child
  exits without calling `task_status.started()` the starter gets
  `RuntimeError("Child exited without calling task_status.started()")`.
  `started()` called twice → `RuntimeError("called 'started' twice on the same
  task status")`. `start()` failure path cancels the child and waits for it inside
  `with CancelScope(shield=True)` before re-raising (`_asyncio.py:952-961`).
- Child tasks are real `asyncio.Task`s wrapping `TaskHandle._run_coro()`, registered
  in `_task_states[task] = TaskState(parent_id, cancel_scope=self.cancel_scope)`
  and `cancel_scope._tasks`. `task_done` callback removes them from both sets,
  resolves the `_on_completed_fut`, and appends non-cancellation exceptions to
  `self._exceptions`; any child failure cancels the group scope unless already
  effectively cancelled (`_asyncio.py:826-907`).
- `__aexit__`: a body exception cancels the scope and is appended (unless
  `CancelledError`); then waits for children under an inner `CancelScope()` wait
  scope which is **set to `shield=True` after the first external cancellation**
  (comment `#695` — further cancels are not productive, `_asyncio.py:784-789`).
  With no children it still runs one `cancel_shielded_checkpoint()`. Non-empty
  `self._exceptions` → `raise BaseExceptionGroup("unhandled errors in a
  TaskGroup", self._exceptions) from None` (chaining deliberately broken); else the
  original `exc_val` is re-raised; the return value is the group scope's
  `__exit__` suppression decision (only AnyIO cancellations, section 3).

`start_soon` name default: `get_callable_name(func, name)` → `module.qualname`.

### TaskHandle (new in 4.14.0, `_core/_tasks.py:206-415`)

Returned by `create_task` / `start_soon` / `start(..., return_handle=True)`.
Each handle owns a private `CancelScope()` (`__init__`, line 262) and its
`_run_coro()` runs `await self._coro` **inside `with self._cancel_scope`**,
recording `_return_value` / `_exception`, setting `_finished_event`, then `del
self` to break the cycle (lines 273-286). `handle.cancel()` calls
`self._cancel_scope.cancel()` unless already finished (lines 288-300).

```python
handle.status -> Status.PENDING | FINISHED | CANCELLING | CANCELLED | FAILED
handle.name -> str
handle.coro -> Coroutine
handle.exception -> BaseException | None   # TaskNotFinished / TaskCancelled per state table
handle.return_value -> T                    # TaskNotFinished / TaskCancelled / TaskFailed
handle.start_value -> T                     # RuntimeError if not created via tg.start()
await handle.wait() -> None                 # returns however the task finished
await handle -> T                           # waits on the event, then return_value semantics
```

`status` mapping (lines 310-333): unfinished + `cancel_called` → `CANCELLING`,
else `PENDING`; finished with no exception → `FINISHED`; finished with the
backend cancelled class → `CANCELLED`; else `FAILED`. `exception` returns the raw
exception for `FAILED`, `None` for `FINISHED`, raises `TaskCancelled` (chained
from the original for `CANCELLED`) otherwise. `return_value` raises `TaskFailed`
chained from the original for `FAILED`.

Exceptions (`_core/_exceptions.py:159-178`): `TaskFailed(Exception)`,
`TaskCancelled(TaskFailed)`, `TaskNotFinished(Exception)`.

`TASK_STATUS_IGNORED` (`_core/_tasks.py:40-45`): a `TaskStatus` whose `started()`
is a no-op.

## 2. Cancel scopes — constructors and deadline helpers

`CancelScope` (`_core/_tasks.py:48-129`) is a factory: `__new__` returns
`get_async_backend().create_cancel_scope(shield=..., deadline=...)`; all real
behavior lives in `_backends/_asyncio.py:382-695`.

```python
CancelScope(*, deadline: float = math.inf, shield: bool = False)
scope.cancel(reason: str | None = None) -> None
scope.deadline -> float                        # writable; setter re-arms an active scope
scope.cancel_called -> bool
scope.cancelled_caught -> bool                 # True only if THIS scope suppressed its own cancellation
scope.shield -> bool                           # writable; unshielding restarts parent cancellation
with scope: ...
```

Deadline helpers (`_core/_tasks.py:132-191`):

```python
with anyio.fail_after(delay: float | None, shield=False) as scope: ...
# on exit: if scope.cancelled_caught and now >= scope.deadline: raise TimeoutError
with anyio.move_on_after(delay: float | None, shield=False): ...   # returns a CancelScope; no exception on timeout
anyio.current_effective_deadline() -> float    # nearest deadline over effective scopes;
                                               # inf = none, -inf = currently cancelled
```

`fail_after(None)` / `move_on_after(None)` → `deadline=math.inf` (disabled).
`_timeout()` (`_asyncio.py:573-579`): if `loop.time() >= deadline` cancel
immediately with reason `"deadline exceeded"`, else `loop.call_at(deadline,
self._timeout)`. `cancel()` builds `_cancel_reason =
f"Cancelled via cancel scope {id(self):x} [by {task}][; reason: {reason}]"`
(lines 646-661) — this message prefix is what `is_anyio_cancellation()` matches
(line 363-379, walks `__context__` chains because third-party code sometimes
re-raises `CancelledError`).

`deadline` setter (`_asyncio.py:667-675`): stores `float(value)`, cancels the old
timer, re-arms if active and not already cancel-called. `shield` setter
(lines 689-694): on `True→False` calls `_restart_cancellation_in_parent()` so a
pending outer cancellation resumes.

## 3. THE CANCEL-SCOPE RULES (must never be violated)

Why scopes are bound to one task: `CancelScope.__enter__` records
`self._host_task = current_task()`, adds it to `self._tasks`, and links
`self._parent_scope = <host's current scope>` / `task_state.cancel_scope = self`
(`_asyncio.py:422-451`). `__exit__` checks two independent conditions
(lines 461-475). Every violation raises `RuntimeError` — never a silent no-op:

1. **One scope, one `with` block.** Re-entering an active scope →
   `RuntimeError("Each CancelScope may only be used for a single 'with' block")`
   (`_asyncio.py:423-426`). A scope object is single-use.
2. **Exit in the task that entered.** `current_task() is not self._host_task` →
   `RuntimeError("Attempted to exit cancel scope in a different task than it was
   entered in")` (lines 463-467). Passing a scope object to another task (or
   holding the task-group owner scope across a task boundary, e.g. entering in an
   MCP-hub owner task and exiting in a worker) **always crashes here**. This is the
   "one owner task must be preserved" rule: the scope's `_tasks` set, `_child_scopes`
   links, timeout handle, and `uncancel()` accounting all assume the same host task.
3. **LIFO nesting within the host task.** If the host's current scope is not `self`
   (scopes closed out of order, or a foreign scope was entered in between) →
   `RuntimeError("Attempted to exit a cancel scope that isn't the current tasks's
   current cancel scope")` (lines 470-475, note upstream typo `tasks's`). Plus
   exiting an inactive scope → `RuntimeError("This cancel scope is not active")`
   (line 462).
4. **Children inherit, never adopt.** Spawned tasks get `cancel_scope =
   <group scope>` at spawn (`_spawn`, lines 897-901). There is no API to move a
   running task into another scope; `TaskState.cancel_scope` is only reassigned by
   scope enter/exit in the same task and by `_AsyncioTaskStatus.started()`
   (parent_id fix-up for `tg.start`, lines 723-739).
5. **Shielding is one-directional and sticky-downward.** `_effectively_cancelled`
   walks up parents but stops at the first `shield=True` (lines 552-563); delivery
   skips shielded child scopes (lines 610-614); `_restart_cancellation_in_parent`
   stops at shields (lines 627-644). Setting `shield=False` on an active scope
   re-triggers parent delivery; setting `wait_scope.shield = True` mid-exit (as
   `TaskGroup.__aexit__` does) only protects the *wait*, it does not un-cancel
   already-cancelled children.

Suppression rule (`__exit__`, lines 493-546): an AnyIO `CancelledError` (or an
exception group consisting *only* of AnyIO cancellations, split out via
`BaseExceptionGroup.split()`) is swallowed **iff** `self._cancel_called` **and**
no parent cancellation is visible through shields
(`_parent_cancellation_is_visible_to_us`). Otherwise the exception (or the
re-raised `remaining` group with `__context__` preserved) propagates, and pending
`uncancel()` counts are forwarded to the parent scope. `cancelled_caught` is set
only on the swallow path. On Python ≥ 3.11 each `task.cancel()` on the host is
counted in `_pending_uncancellations` and balanced with `task.uncancel()` on the
swallow path (lines 497-501, 604-608); on older Pythons the counter is `None`.

## 4. Cancellation propagation semantics (asyncio)

- `get_cancelled_exc_class()` → `asyncio.CancelledError` on asyncio.
- `scope.cancel()` is synchronous and idempotent (second call no-op): cancels the
  deadline timer, sets `_cancel_called`, builds the reason string, and calls
  `_deliver_cancellation(self)` if the scope has a host task (lines 646-661).
- `_deliver_cancellation(origin)` (lines 581-625): for each task in `scope._tasks`,
  if it is not the calling task, is the host or has actually started
  (`_task_started` checks coroutine state `CORO_RUNNING`/`CORO_SUSPENDED`, so
  never-started eager/coroutine tasks are skipped), and is not already
  must-cancel, calls `task.cancel(origin._cancel_reason)` unless its waiter future
  is done; recurses into non-shielded, not-already-cancelled child scopes; the
  *origin* scope reschedules itself with `loop.call_soon` while work remains.
- `asyncio.Task.cancel(msg)` delivery is asynchronous: the `CancelledError` is
  raised at the next await point. `TaskGroup._spawn.task_done` unwraps chained
  `__context__` `CancelledError`s to find the AnyIO one (lines 852-857).
- `checkpoint()` → `await sleep(0)` i.e. `await asyncio.sleep(0)` — yields to the
  loop **and** raises if cancelled (`_asyncio.py:2450-2452`, `lowlevel.py:26-39`).
- `checkpoint_if_cancelled()` — walks the scope chain; `await sleep(0)` only at
  scopes with `cancel_called`, stops at shields; pure `sleep(0)` is never reached
  when nothing is cancelled, so it never yields in the uncancelled case
  (lines 2454-2471). This is what `Lock`/`Semaphore`/`CapacityLimiter` fast paths
  call before taking a free resource — a pending cancel still fires, but taking an
  uncontended primitive does not otherwise yield.
- `cancel_shielded_checkpoint()` → `with CancelScope(shield=True): await sleep(0)`
  — always yields, never raises for outer cancels (lines 2473-2476). Used after
  acquiring uncontended locks/semaphores (fairness yield) and by `TaskGroup`
  exit with no children.
- `sleep(delay)` → `await asyncio.sleep(delay)` (lines 2478-2480). `sleep_forever()`
  → `sleep(math.inf)`; `sleep_until(deadline)` → `sleep(max(deadline - now, 0))`
  with `now = current_time()` (`_core/_eventloop.py:98-121`).
- `current_time()` → `get_running_loop().time()` (line 2442-2444).
- `check_cancelled()` (lines 2599-2608, used by worker-thread plumbing): walks
  `threadlocals.current_cancel_scope` chain, raises `CancelledError("Cancelled via
  cancel scope ...")` at the first `cancel_called` scope, stops at shields.
- `ExceptionGroup` handling: child crashes are collected as a
  `BaseExceptionGroup("unhandled errors in a TaskGroup", ...)` (builtin on
  3.11+, `exceptiongroup` backport below). Scope exit splits AnyIO cancellations
  from real errors and re-raises only the remainder (section 3). `iterate_exceptions`
  (`_core/_exceptions.py:83-90`) flattens nested groups.

## 5. Synchronization primitives (asyncio behavior)

All four are factories (`__new__` → `get_async_backend().create_*`, falling back
to `*Adapter` objects when constructed with **no running loop** — the adapter
lazily creates the real primitive on first use; `LockAdapter.__exit__` only
releases if the inner lock exists). `fast_acquire: bool = False` opts out of the
post-acquire fairness yield.

**`Event`** (`_core/_synchronization.py:82-152`, backend `_asyncio.py:1821-1844`):
wraps `asyncio.Event`. `set()` / `is_set()` sync. `wait()`: if already set, does
`await checkpoint()` (yields + raises on cancel) instead of returning inline;
else `await self._event.wait()` (a real checkpoint — cancellable). `statistics()`
→ `EventStatistics(tasks_waiting)`.

**`Lock`** (core lines 155-267, backend lines 1846-1927): non-reentrant,
single-owner (`_owner_task: asyncio.Task`), FIFO waiter deque of `(task, future)`.
`acquire()` fast path (free + no waiters): `checkpoint_if_cancelled`, take
ownership, then fairness `cancel_shielded_checkpoint()` unless `fast_acquire`
(a `CancelledError` there releases and re-raises). Contended: queue a future,
`await` it; on cancel, dequeue if still queued, else `release()` the
just-granted ownership, then re-raise. Same task re-acquire → `RuntimeError
("Attempted to acquire an already held Lock")` (both `acquire` and
`acquire_nowait`). `acquire_nowait()`: free + no waiters → take; owned-by-self →
`RuntimeError`; else `WouldBlock`. `release()` by a non-owner →
`RuntimeError("The current task is not holding this lock")`; wakes the first
non-cancelled waiter (skips futures already `cancelled()`). Also a sync
`ResourceGuard(action="using")` context manager (core lines 740-772): second
`__enter__` while held → `BusyResourceError`. `statistics()` →
`LockStatistics(locked, owner: TaskInfo | None, tasks_waiting)`.

**`Semaphore`** (core lines 382-525, backend lines 1930-2015):
`Semaphore(initial_value: int, *, max_value: int | None = None, fast_acquire=False)`;
constructor validates `initial_value >= 0` (`TypeError`/`ValueError`), `max_value
>= initial_value`. Counter + FIFO waiter deque; same checkpoint-then-shielded-yield
fast path and same cancel-grant-release dance as `Lock`. `acquire_nowait()` on
empty → `WouldBlock` (no owner check — any task may release). `release()` past
`max_value` → `ValueError("semaphore released too many times")`; wakes the first
non-cancelled waiter instead of incrementing. `value` / `max_value` properties.
`statistics()` → `SemaphoreStatistics(tasks_waiting)`. Usable as
`async with semaphore:`.

**`CapacityLimiter`** (core lines 528-737, backend lines 2018-2136): token pool
keyed by **borrower identity** (default borrower: `current_task()`).
`CapacityLimiter(total_tokens)`; setter requires `int` or `math.inf`
(`TypeError` otherwise), `>= 0` (`ValueError`); since 4.12 `0` is legal; raising
the total notifies that many waiters FIFO. Double-borrow by the same borrower →
`RuntimeError("this borrower is already holding one of this CapacityLimiter's
tokens")`; `release` by a non-borrower → `RuntimeError("this borrower isn't
holding any of this CapacityLimiter's tokens")`. `acquire_nowait` with a queue or
no free token → `WouldBlock`. `acquire_on_behalf_of(borrower)` checkpoints first,
queues an `asyncio.Event` on contention, dequeues + cascades (`_notify_next_waiter`)
on cancel, shielded-yields on the fast path (releasing on failure). Usable as
`async with limiter:`. `total_tokens` / `borrowed_tokens` / `available_tokens`
properties; `statistics()` → `CapacityLimiterStatistics(borrowed_tokens,
total_tokens, borrowers, tasks_waiting)`.

**`Condition`** (core lines 270-379, backend-independent): owns a `Lock`
(`Condition(lock=None)` creates one) and tracks `_owner_task: TaskInfo`.
`acquire()` / `acquire_nowait()` / `release()` / `locked()` delegate with an
ownership check: any use from a task not holding the lock →
`RuntimeError("The current task is not holding the underlying lock")`
(`notify`/`notify_all` check too). `wait()`: `checkpoint_if_cancelled` first,
enqueues a fresh `Event`, releases the lock, `await event.wait()`; on any
exception unlinks (or passes a consumed notification to the next waiter), then
**re-acquires inside `with CancelScope(shield=True)`** so a cancel during the
wait cannot leave the lock dropped (lines 335-355). `wait_for(predicate)` (4.11.0)
loops `wait()` until truthy and returns the value. `notify(n=1)` /
`notify_all()` only wake; they do not release the lock. `statistics()` →
`ConditionStatistics(tasks_waiting, lock_statistics)`.

## 6. `to_thread.run_sync` (and the thread pool)

```python
await anyio.to_thread.run_sync(func, *args, abandon_on_cancel=False,
                               cancellable=None, limiter=None) -> retval
anyio.to_thread.current_default_thread_limiter() -> CapacityLimiter
```

(`to_thread.py:25-78`; backend `_asyncio.py:2537-2596`.) Runs `func(*args)` in a
reused `WorkerThread`. Semantics:

- Always `await checkpoint()` first (line 2545) — a pending cancel fires before
  touching the pool.
- Runs under `async with (limiter or default)` **and**
  `with CancelScope(shield=not abandon_on_cancel)` (line 2558-2559):
  `abandon_on_cancel=False` (default) shields the wait — outer cancellation is
  deferred until the thread finishes, and the return value/exception is still
  delivered. `True` lets the wait cancel immediately while the thread runs on
  unchecked (result/exception discarded). `cancellable=` is a deprecated (4.1.0)
  alias that overrides `abandon_on_cancel` with a `DeprecationWarning`.
- Default limiter: per-loop `RunVar`, `CapacityLimiter(40)` — max **40** worker
  threads per event loop (`_asyncio.py:3034-3040`); idle threads pruned after
  `WorkerThread.MAX_IDLE_TIME = 10` s (lines 977, 2572-2586).
- Worker entry copies the caller's `contextvars.Context` with the sniffio/async
  lib name cleared (`set_current_async_library(None)`), and `check_cancelled()`
  against the enclosing (non-shielded parent if abandoning) scope before running.
  `func` raising in the thread → the exception is re-raised to the awaiter
  (unless abandoned).

`from_thread` (sync threads → loop): `run(func, *args)`, `run_sync(func, *args)`
(require an AnyIO worker thread or an explicit token, else `NoEventLoopError`;
`RunFinishedError` if the token's loop finished), and `BlockingPortal` with
`call` / `start_task_soon` / `start_task` / `sleep_until_stopped` /
`stop(cancel_remaining=False)` / `wrap_async_context_manager`
(`from_thread.py:54-428`).

## 7. Sleep / checkpoint / introspection cheatsheet

```python
await anyio.sleep(delay)                 # asyncio.sleep(delay); full checkpoint
await anyio.sleep_forever()              # sleep(math.inf)
await anyio.sleep_until(deadline)        # loop-clock absolute; max(deadline-now, 0)
anyio.current_time() -> float            # loop.time()
from anyio.lowlevel import checkpoint, checkpoint_if_cancelled, cancel_shielded_checkpoint
# checkpoint: raise-if-cancelled + yield.  checkpoint_if_cancelled: raise-if-cancelled, no yield otherwise.
# cancel_shielded_checkpoint: yield, never raise for outer scopes.
anyio.get_current_task() -> TaskInfo     # .id / .parent_id / .name / .coro; has_pending_cancellation() is False on the base class
anyio.get_running_tasks() -> list[TaskInfo]
await anyio.wait_all_tasks_blocked()     # until every other task is waiting
anyio.current_effective_deadline() -> float
anyio.get_cancelled_exc_class()          # asyncio.CancelledError on this backend
from anyio.lowlevel import current_token() -> EventLoopToken  # 4.11.0; for from_thread calls
from anyio.lowlevel import RunVar        # loop-scoped var with .get/.set/.reset (token redeem-once)
```

No `anyio.Queue`. For producer/consumer queues use
`send, recv = anyio.create_memory_object_stream[T](max_buffer_size=...)`:
`await send.send(item)` blocks when full; `send.send_nowait(item)` →
`WouldBlock` when full, `ClosedResourceError` when closed; `await recv.receive()`
→ `EndOfStream` when send side closed and drained; `receive_nowait()` →
`WouldBlock` / `EndOfStream` / `ClosedResourceError`; `send.clone()` /
`recv.clone()` share the channel; closing the last clone closes that end;
`statistics()` → `(current_buffer_used, max_buffer_size, open_send_channels,
open_receive_channels, tasks_waiting_send, tasks_waiting_receive)`
(`streams/memory.py`, `_core/_streams.py`).

## 8. Rules for an asyncio (flet) app using this package

1. One task owns each scope/task-group: enter and exit `CancelScope`s and
   `create_task_group()` blocks in the **same** task, LIFO. Never hand a live
   scope to another task — exit raises `RuntimeError` by design (section 3).
2. Prefer `with move_on_after(...)` / `with fail_after(...)` for timeouts over
   `asyncio.wait_for`: timeouts surface as scope exit (`cancelled_caught`) or
   `TimeoutError` respectively, and compose with shields — `wait_for` would inject
   a foreign `CancelledError` the group cannot attribute.
3. Catch `asyncio.CancelledError` (== `get_cancelled_exc_class()`) only to clean
   up and re-raise; use `scope.cancelled_caught` after the `with` block to detect
   self-cancellation. Never swallow a cancellation you did not cause — the
   `__exit__` split logic already handles attribution.
4. Shield only the *wait/cleanup*, e.g. `with CancelScope(shield=True): await
   handle.wait()` / lock re-acquire / `aclose_forcefully`, and keep shielded
   regions short — shields also block deadline enforcement from outside.
5. Expect `BaseExceptionGroup` from a task group with ≥1 child failure; iterate
   with `anyio` semantics (`except*` or `iterate_exceptions`), not `except
   Exception` (a group is not an `Exception` subclass match for its members).
6. Blocking calls go through `await to_thread.run_sync(..., abandon_on_cancel=?)`
   under the 40-thread default limiter; `abandon_on_cancel=False` keeps the flet
   loop responsive while guaranteeing the result is still collected.
7. Uncontended `Lock`/`Semaphore` acquisition still performs
   `checkpoint_if_cancelled` + a shielded yield (unless `fast_acquire=True`), so
   tight acquire/release loops do not starve the loop — but a hot path shared
   across tasks should use `fast_acquire` only if fairness is handled elsewhere.
8. `Condition.wait()` must be called holding the lock, in a loop (`wait_for` does
   this); `notify*` also requires holding the lock.

## Source index (all paths under `.venv/Lib/site-packages/anyio/`)

- `__init__.py` — public re-export surface (no `Queue`, no `ShieldCancellation`).
- `_core/_tasks.py` — `CancelScope` factory/docs, `fail_after`, `move_on_after`,
  `current_effective_deadline`, `create_task_group`, `TaskHandle` + status table.
- `_core/_synchronization.py` — `Event`/`Lock`/`Condition`/`Semaphore`/
  `CapacityLimiter`/`ResourceGuard` contracts + `*Adapter` lazy variants.
- `_core/_eventloop.py` — `run/sleep/sleep_forever/sleep_until/current_time`,
  backend registry, sniffio-absent fallback.
- `_core/_exceptions.py` — `TaskFailed/TaskCancelled/TaskNotFinished`,
  `WouldBlock`, `NoEventLoopError`, `iterate_exceptions`.
- `_core/_streams.py` — `create_memory_object_stream` (the Queue substitute).
- `_core/_testing.py` — `TaskInfo`, `get_current_task`, `get_running_tasks`,
  `wait_all_tasks_blocked`.
- `_backends/_asyncio.py` — host-task binding + the three `RuntimeError`s
  (422-475), suppression/`uncancel` (493-546), effectiveness/shield walk
  (552-571), delivery/retry (581-644), `TaskGroup` wait-shield + `BaseExceptionGroup`
  (755-824), spawn/task_done (826-907), `Lock` (1846-1927), `Semaphore`
  (1930-2015), `CapacityLimiter` (2018-2136), checkpoints/sleep (2443-2480),
  `run_sync_in_worker_thread` (2537-2596, shield=`not abandon_on_cancel`),
  default thread limiter `40` (3034-3040), `check_cancelled` (2599-2608).
- `abc/_tasks.py` — `TaskGroup` ABC, `start_soon→TaskHandle` (4.14.0),
  `TaskStatus` protocol, eager-factory caveat.
- `abc/_eventloop.py` — backend capability contract.
- `lowlevel.py` — `checkpoint*`, `EventLoopToken`/`current_token`, `RunVar`.
- `to_thread.py` — `run_sync` signature + `abandon_on_cancel` contract.
- `from_thread.py` — `run/run_sync/BlockingPortal` for the reverse direction.
- `streams/memory.py` — send/receive/nowait/clone/close/statistics semantics.
