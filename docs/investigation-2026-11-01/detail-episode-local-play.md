# Investigation: Play Local Downloaded Episode from Anime Detail Screen

**Date**: 2026-11-01
**Repo**: /home/maikel/Desktop/kiri-apps/animepahe-tv
**Branch**: main

---

## 1. Symptom

When a user clicks on an episode in the **Anime Details screen**, the app always fetches/resolves the stream from the provider (AniKato, AnimePahe, etc.) — even if that episode is already **downloaded and complete** on the device.

The user must explicitly open the **3-dot overflow menu** on the episode card and select **"Play offline"** to play the local file. The primary tap handler on the episode card ignores the downloads store entirely.

---

## 2. Root Cause

### File: `src/screens/anime_detail_screen.py`

**Lines 170-173** — `_episode_card` function (primary click handler):
```python
return ft.Stack(
    [
        card_frame(
            mode=mode,
            media=card_media(...),
            overlay=overlay,
            on_click=lambda e: on_play(anime_session, ep.session),  # <-- ALWAYS calls play_episode
        ),
        ...,
    ],
)
```

**Lines 403-418** — `_episode_state` function (overflow menu):
```python
if done:  # done = row.get("state") == "complete"
    items.append(
        ft.PopupMenuItem(
            content="Play offline",
            icon=ft.Icons.DOWNLOAD_DONE_ROUNDED,
            height=40,
            on_click=lambda e, s=ep.session: controller.play_downloaded(s),  # <-- Only in menu
        )
    )
```

The **primary tap** (`on_click` on the card frame) calls `controller.play_episode(anime_session, ep.session)` which **never consults the downloads store**. Only the secondary "Play offline" menu item calls `controller.play_downloaded(episode_session)`.

### File: `src/main.py` — `AppController.play_episode` (line 858)

```python
async def play_episode(self, anime_session: str, episode_session: str):
    # ...
    async with self._play_lock:
        may_solve = self._may_solve(anime_session)
        async with contextlib.AsyncExitStack() as stack:
            if may_solve:
                await stack.enter_async_context(self._user_action())
            await self._play_episode(anime_session, episode_session)
```

The method immediately begins **stream resolution** via `_play_episode_resolve` → `_sources_with_kwik` → provider router. It does **not** check `self.store.get_downloads()` for an existing completed download.

### File: `src/main.py` — `AppController.play_downloaded` (line 2315)

```python
async def play_downloaded(self, episode_session: str):
    rows = await self.store.get_downloads()
    row = rows.get(episode_session) or {}
    local = row.get("playlist") or row.get("file")
    if not local or not os.path.exists(local):
        state.player_error = "The downloaded file is missing."
        state.player_open = True
        return
    state.player_spec = {
        "resource": local,  # local file path or local .m3u8 playlist
        "variants": [],
        "title": "...",
        "episode_session": episode_session,
        "anime_session": row.get("anime_session", ""),
        "headers": {},  # no headers needed for local files
    }
    state.player_open = True
```

This method **correctly** reads the downloads store, verifies the local file exists, and opens the player with the local path.

---

## 3. How Downloads Store Works

### File: `src/services/store.py`

- **`get_downloads()`** (line 358): Returns dict keyed by `episode_session`, each row contains:
  - `state`: `"partial"` | `"complete"` | `"failed"`
  - `playlist`: local path to rewritten `.m3u8` (for HLS downloads)
  - `file`: local path to direct file (for MP4/MKV downloads)
  - `anime_session`: parent anime session
  - `episode_num`: episode number
  - `title`, `poster`, `resolution`, `size_bytes`, etc.

- **`save_download()`** (line 362): Called by download manager when job completes with `state: "complete"` and local paths.

### File: `src/screens/downloads_screen.py` — Line 137-145

The downloads screen correctly uses `controller.play_downloaded(session)` for the Play button on completed episodes.

---

## 4. Player Accepts Local Source

### File: `src/app_shell.py` — `_use_player_overlay` (lines 526-549)

```python
player = ImmersivePlayer(
    resource=spec.get("resource", ""),  # <-- local path accepted
    title=spec.get("title", ""),
    http_headers=spec.get("source_headers"),  # empty for local
    resume_key=spec.get("episode_session"),
    store=get_store(),
    variants=spec.get("variants") or [],
    on_close=lambda: _close_player(),
    ...
    proxied=spec.get("proxied", False),  # false for local
    subtitles=spec.get("subtitles") or [],
    skip=spec.get("skip") or {},
)
```

### File: `src/components/player/immersive_player.py` — `_start_playback` (line 559)

```python
self.video.playlist = [fv.VideoMedia(self.resource, http_headers=self.http_headers)]
await self.video.play()
```

The `fv.VideoMedia` accepts **local file paths** (file:// or absolute paths) and plays them directly without the HLS proxy when `proxied=False` and `headers={}`.

---

## 5. Proposed Fix

### Option A: Fix in Controller (Recommended) — `src/main.py`

Modify `play_episode` to check downloads store **before** resolving streams:

```python
async def play_episode(self, anime_session: str, episode_session: str):
    # Check downloads store FIRST
    rows = await self.store.get_downloads()
    row = rows.get(episode_session) or {}
    if row.get("state") == "complete":
        local = row.get("playlist") or row.get("file")
        if local and os.path.exists(local):
            # Play local file directly — bypass all stream resolution
            await self.play_downloaded(episode_session)
            return
    
    # ... existing stream resolution flow
    if self._play_lock.locked():
        ...
```

**Why in controller**: 
- Single source of truth for all play entry points (detail screen, continue watching, downloads screen, external links)
- Handles both single-episode downloads and series downloads (all episodes) uniformly
- Keeps screens simple — they just call `play_episode`

### Option B: Fix in Detail Screen — `src/screens/anime_detail_screen.py`

Modify the `on_play` callback passed to `_episode_card` (line 541):

```python
# In AnimeDetailScreen, before rendering cards:
async def _on_play(anime_session: str, episode_session: str):
    # Check downloads via state (already loaded)
    downloads = state.downloads or {}
    row = downloads.get(episode_session) or {}
    if row.get("state") == "complete":
        controller.play_downloaded(episode_session)
    else:
        controller.play_episode(anime_session, episode_session)


# Pass _on_play instead of controller.play_episode to _episode_card
```

**Why NOT here**:
- Duplicates logic across screens (continue watching, search results, etc. would need same fix)
- Screen shouldn't know about store internals
- State.downloads may be stale vs store

---

## 6. Considerations

### Series Downloads (All Episodes)
- `download_series` (line 1970) queues N independent jobs
- Each episode gets its own row in downloads store with `state: "complete"`
- The fix naturally handles this — each episode check is independent

### Resume Position
- `play_downloaded` uses `resume_key=episode_session` (line 2339)
- Player reads position from store via `store.get_position(resume_key)` (immersive_player.py:524)
- Works identically for local and streamed playback

### Subtitles
- Downloaded HLS: subtitles embedded in local `.m3u8` playlist
- Downloaded file: subtitles may be embedded in MKV/MP4 or separate `.vtt`/`srt`
- Current `play_downloaded` passes `subtitles=[]` — may need enhancement to include downloaded subtitle tracks if stored

### Offline/Online State
- If online but download exists: **play local** (user intent = offline playback)
- If offline and download exists: **play local** (only option)
- If download missing/corrupted: fall through to stream resolution (shows error card if fails)

---

## 7. Tests to Verify

### Existing Tests
- `tests/test_download_playback_parity.py` — verifies local playlist rewrite matches written segment files
- `tests/test_episode_switch.py` — verifies episode list clears on anime switch

### New Tests Needed
1. **Unit test**: `play_episode` calls `play_downloaded` when download exists and is complete
2. **Integration test**: Tap episode card → player opens with local resource (not proxy URL)
3. **Edge case**: Download exists but file missing → falls back to stream resolution
4. **Edge case**: Download state = "partial" → does NOT play local, resolves stream

---

## 8. Severity

**High** — User Experience regression:
- Wasted bandwidth re-downloading streams already on device
- Slower playback start (resolution + proxy vs instant local)
- Fails offline when user expects downloaded episode to play
- Inconsistent with Downloads screen behavior (which plays local correctly)

---

## 9. Files to Modify

| File | Change |
|------|--------|
| `src/main.py` | In `AppController.play_episode`: add downloads store check before stream resolution (lines 858-873) |
| `tests/test_play_local_if_downloaded.py` | New test file (create) |

---

## 10. Summary

| Aspect | Detail |
|--------|--------|
| **Symptom** | Episode tap always resolves stream, ignores completed downloads |
| **Root Cause** | `anime_detail_screen.py:172` calls `play_episode` which never checks downloads store |
| **Fix Location** | `src/main.py` — `AppController.play_episode` (add early return via `play_downloaded`) |
| **Player Support** | Already handles local files via `fv.VideoMedia(resource, headers={})` with `proxied=False` |
| **Tests** | Add test for `play_episode` → `play_downloaded` delegation when download complete |
| **Severity** | High — bandwidth waste, slow start, offline breakage |