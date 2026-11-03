# Download Progress Realtime Investigation

## Symptom
The downloads UI does **not update live** (state + percentage) while a download job runs. Users see no progress bar movement or state changes until the job completes or fails.

## Root Cause

### The Pipeline Breakage at `main.py:2375-2379`

The download progress flusher (`_flush_download_progress` at `main.py:2358-2395`) **filters out completed/failed jobs** by only keeping entries where `self.downloads.job_running(session)` returns `True`. This check happens **after** the manager already popped the job's progress entry in `_run()` / `_run_direct()` completion paths.

```python
# main.py:2375-2379
live = {s: row for s, row in pending.items() if self.downloads.job_running(s)}
merged.update(live)
for session in list(merged):
    if not self.downloads.job_running(session):
        merged.pop(session, None)
```

But `DownloadManager.job_running()` (`downloads.py:556-560`) checks if the session is still in `_progress`:
```python
def job_running(self, episode_session: str) -> bool:
    return episode_session in self._progress
```

The manager **removes** the progress entry **before** the flusher runs:
- `_run()` (HLS): `self._progress.pop(episode_session, None)` at line 882
- `_run_direct()` (file): `self._progress.pop(episode_session, None)` at line 719

So by the time the throttled flush fires (~0.5s later), the session is no longer in `_progress` → `job_running()` returns `False` → the progress row is **dropped** from `state.download_progress` → the UI re-renders with empty progress.

### What Works in CollabShell / Sherlock
Those apps don't have a download manager with this architecture, but the **house pattern** for live progress (seen in their avatar downloads, scan progress, etc.) uses:
1. **Direct observable mutations** — `state.progress[key] = {...}` without an intermediate flusher
2. **No "job_running" filter** — progress stays in state until explicitly cleared by UI consumption
3. **Flet's `@observable` dict** — `state.download_progress[session] = progress` triggers re-render immediately

### Missing Wire in animepahe-tv
The `DownloadManager.on_progress` callback **does fire correctly** (segments at `downloads.py:968-973`, file chunks at `downloads.py:1173-1174`), and it reaches `AppController._on_download_progress` → `_pending_progress` → flusher.

**But the flusher discards the very data it should publish** because the manager clears `_progress` at job completion, and the flusher treats "not in _progress" as "not running."

## Concrete Fix

### Option A: Keep Progress Until UI Consumes It (Recommended)
Change `DownloadManager` to **not pop progress on completion**. Instead, let the controller clear it after reading (as it already does for failed jobs at `main.py:2395`).

**File: `src/services/downloads.py`**
- Remove `self._progress.pop(episode_session, None)` from `_run()` (line 882) and `_run_direct()` (line 719)
- The `clear_progress(sessions)` method at line 562-566 already exists for the controller to call

### Option B: Fix the Flusher Filter
Change `_flush_download_progress` to **not filter by `job_running`** — just merge all pending progress. The manager's `_progress` dict is the source of truth; if a session is in `pending`, it's live.

**File: `src/main.py` lines 2363-2379**
```python
# REPLACE the filter logic with:
while self._pending_progress:
    await asyncio.sleep(_PROGRESS_FLUSH_SECONDS)
    pending, self._pending_progress = self._pending_progress, {}
    if not pending:
        return
    merged = dict(state.download_progress or {})
    merged.update(pending)  # ALL pending entries, no job_running filter
    state.download_progress = merged
    state.downloads_version += 1
    # failed handling unchanged
```

### Why Option A is Better
- Matches the **house pattern**: progress lives in observable state until explicitly consumed
- `DownloadManager.clear_progress()` is already called by controller for failed jobs (`main.py:2395`)
- For completed jobs, `_on_download_finished` already reloads `state.downloads` from store (`main.py:2408`) — the row shows "complete" from the store, not from progress
- No race between manager pop and flusher read

## Tests Coverage

| Test File | Covers |
|-----------|--------|
| `test_download_states.py` | State machine (pause/resume/retry), progress percent calculation, queue concurrency |
| `test_downloads.py` | Playlist rewriting, store round-trip |
| `test_download_parity.py` | HLS vs direct path parity |
| `test_download_quality.py` | Quality selection |
| `test_download_engine_integrity.py` | Segment download integrity |
| `test_download_crashes.py` | Error handling |

**Gap**: No test verifies **live progress updates reach `state.download_progress`** during an active download. The existing tests mock the HTTP layer and run jobs to completion synchronously — they assert final state, not intermediate progress emissions.

## Severity: **HIGH**
- Core user-facing feature (download management) appears broken
- Users cannot monitor downloads — no percentage, no state changes
- Workaround: None (UI simply doesn't update until job ends)

## 5-Bullet Summary
1. **Symptom**: Download progress bar and state never update live — UI frozen until job completes/fails
2. **Root Cause**: `main.py:2375-2379` flusher filters out progress for sessions not in `DownloadManager._progress`, but manager pops `_progress` at job completion (`downloads.py:719,882`) before flusher runs
3. **Fix**: Remove `self._progress.pop()` from `_run()` and `_run_direct()` in `downloads.py`; let controller's existing `clear_progress()` handle cleanup (Option A)
4. **Tests**: Current tests verify final states only; no test covers live progress emission → flusher → UI path
5. **Severity**: HIGH — core feature visibly broken, no user workaround