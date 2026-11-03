# Downloads: MB Progress Investigation Report

**Date**: 2026-11-01
**Target**: Show "78.2/186.4 MB" for HLS jobs (not "123/456 segments")

---

## 1. Data Availability End-to-End

### HLS Path (Segment Downloads) — `src/services/downloads.py`

| Location | What's Tracked | Bytes Available? |
|----------|----------------|------------------|
| `_run()` line 805 | `total = len(uris)` — **segment count** (e.g., 144) | ❌ |
| `_run()` line 814 | `progress["total"] = total` — **segment count** | ❌ |
| `_run()` line 824 | `progress["done"] = done` — **segment count** from resume scan | ❌ |
| `_worker()` line 972 | `progress["done"] += 1` — increments per segment | ❌ |
| `_download_file()` line 1134 | `resp.headers.get("content-length")` — **segment byte size** | ✅ Per segment |
| `_download_file()` line 1173-1174 | `on_progress(len(chunk), progress_total)` — **byte callback** | ✅ But not used for HLS! |

**Critical Finding**: The HLS path calls `_download_file(segment_url, headers, part_path, final_path)` at line 946 **without** the `on_progress` callback. The byte-level progress callback exists in `_download_file` and receives `Content-Length` per segment, but HLS never wires it up.

**`progress` dict for HLS** (line 319):
```python
{
    "done": 0,  # segment count
    "total": 0,  # segment count (set at line 814)
    "bytes": 0,  # ALWAYS 0 — never updated
    "state": "queued",
    "title": "...",
    "anime_session": "...",
}
```

### Direct File Path — `src/services/downloads.py`

| Location | What's Tracked | Bytes Available? |
|----------|----------------|------------------|
| `_run_direct()` line 632 | `have = os.path.getsize(part_path)` — **bytes already on disk** | ✅ |
| `_run_direct()` line 657 | `on_progress=_chunk` — passes byte callback | ✅ |
| `_chunk()` line 635-647 | `progress["bytes"] += n`, `progress["total"] = total` — **bytes** | ✅ |
| `_run_direct()` line 698 | `progress["total"] = size_bytes` (final file size) | ✅ |

**`progress` dict for File**:
```python
{
    "done": 1,           # 1 when complete (file count)
    "total": 195_000_000, # total BYTES
    "bytes": 78_200_000,  # bytes downloaded so far
    "state": "downloading",
    ...
}
```

---

## 2. Current UI Behavior — `src/screens/downloads_screen.py`

### Per-Episode Label (`_progress_label`, lines 40-71)

```python
# Line 58-60: HEURISTIC — total > 20_000 means BYTES, else SEGMENTS
if total > 20_000:
    return f"{percent:.0f}% · {_fmt_size(done)} / {_fmt_size(total)}"
return f"{percent:.0f}% · {int(done)}/{int(total)} segments"
```

**Problem**: HLS `total` = segment count (e.g., 144) < 20,000 → shows "42% · 123/144 segments"
File `total` = bytes (e.g., 195,000,000) > 20,000 → shows "42% · 78.2/186.4 MB" ✅

### Aggregate Series Summary (lines 279-293)

```python
# Line 291: Uses segment counts and segment-based percents
summary = f"{done_items}/{len(rows)} done · {overall:.0f}%"
```

**Problem**: Always shows segment-style "3/11 · 42%" regardless of path.

---

## 3. Tray/Notification — `src/main.py`

### `_on_download_progress` (line 2419)
- Receives `progress` dict with segment counts for HLS
- Throttles and flushes to `state.download_progress`
- **Same dict structure** — no bytes for HLS

### `_flush_download_progress` (line 2432)
- Line 2434 comment: "AND the tray's progress notification"
- Publishes the same progress dict → tray sees segment counts

---

## 4. Honest Options for HLS Byte Progress

### Current Reality
- m3u8 playlists **do not** contain segment sizes (EXT-X tags lack byte info)
- Content-Length is only known **when each segment is fetched** (response header)
- Total MB **cannot be known upfront** — only after all segments are fetched

### Option A: Accumulate Bytes Done (Recommended)
- **What**: Wire `on_progress` in `_worker()` → `_download_file()` for HLS
- **Numerator**: `progress["bytes"] += len(chunk)` per segment (real bytes written)
- **Denominator**: Unknown until all segments fetched → **show "78.2 MB done" + percent from segments**
- **UI**: "42% · 78.2 MB done" (no remaining, no total)
- **Pros**: Accurate downloaded bytes; cheap (sums Content-Length as fetched)
- **Cons**: No "remaining" or "total" until end

### Option B: Approximate Total from Running Average
- **What**: After first N segments, `avg_size = bytes_done / segments_done`, `estimated_total = avg_size * total_segments`
- **UI**: "42% · 78.2/186.4 MB (est.)"
- **Pros**: Shows total/remaining immediately
- **Cons**: Inaccurate (segments vary); owner must approve "est." label

### Option C: Show Total Only at Completion
- **What**: Accumulate bytes; only show total MB when job completes
- **UI**: "42% · 78.2 MB done" → on complete: "186.4 MB"
- **Pros**: Honest, no estimates

---

## 5. Required UI Changes — `src/screens/downloads_screen.py`

### Fallback Ladder (per owner's rule)

| Rung | Condition | Display | Data Needed |
|------|-----------|---------|-------------|
| 1 | `bytes > 0` AND `total_bytes > 0` | `"42% · 78.2/186.4 MB"` | `progress["bytes"]`, `progress["total_bytes"]` |
| 2 | `bytes > 0` ONLY | `"42% · 78.2 MB done"` | `progress["bytes"]` |
| 3 | `total_bytes > 0` ONLY | `"42% · 186.4 MB total"` | `progress["total_bytes"]` |
| 4 | Percent only | `"42%"` | `progress["percent"]` |
| 5 | Nothing | *(drop counter)* | — |

### Changes Needed

1. **`_progress_label()` (lines 40-71)**:
   - Add `total_bytes = progress.get("total_bytes") or progress.get("total") if total > 20000 else 0`
   - Add `bytes_done = progress.get("bytes", 0)`
   - Implement fallback ladder above
   - Keep percent from segments (already works)

2. **Aggregate Summary (lines 279-293)**:
   - Sum `bytes_done` across running jobs → show "78.2/186.4 MB" if available
   - Fall back to segment counts if no byte data

3. **Progress Dict Contract (in `DownloadManager`)**:
   - Add `"total_bytes"` field (separate from `"total"` which is segment count for HLS)
   - For HLS: accumulate `bytes_done` in `_worker()` via `on_progress`
   - For File: already works (`total` = bytes)

---

## 6. Implementation Plan

### Minimal Changes to Enable Option A

**File: `src/services/downloads.py`**

1. In `_worker()` (line 946): Pass `on_progress` callback to `_download_file()`
2. In `_worker()`: Accumulate `progress["bytes"] += chunk_size` in callback
3. In `_run()`: Initialize `progress["bytes"] = 0`, add `progress["total_bytes"] = 0`
4. In `_download_file()`: Already returns `progress_total` (full segment size) to callback

**File: `src/screens/downloads_screen.py`**

1. In `_progress_label()`: Read `bytes_done = progress.get("bytes", 0)`, `total_bytes = progress.get("total_bytes", 0)`
2. Implement fallback ladder
3. In aggregate summary: Sum `bytes_done` across jobs

---

## 7. 5-Bullet Summary

- **HLS progress dict carries segment counts only** (`done`/`total` = segments, `bytes` = 0 always) — `src/services/downloads.py:319,814,972`
- **Byte data EXISTS per-segment** (`Content-Length` in `_download_file` response at line 1134) but **HLS path doesn't wire the `on_progress` callback** (line 946 vs line 657 for files)
- **Direct file path already works** — UI shows "42% · 78.2/186.4 MB" via heuristic `total > 20_000` at `downloads_screen.py:58`
- **Owner's fallback ladder needs**: (1) MB done/remaining → needs `total_bytes`; (2) MB done only → needs `bytes`; (3) total MB only → needs `total_bytes`; (4) percent only; (5) drop counter
- **Minimal fix**: Wire `on_progress` in `_worker()` to accumulate `progress["bytes"]`, add `progress["total_bytes"]` field, update `_progress_label()` and aggregate summary to use the ladder