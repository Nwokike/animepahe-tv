# Fullscreen Player Back Button Hang - Investigation Report

**Date:** 2026-11-01  
**Repo:** animepahe-tv (flet app)  
**Branch:** main (HEAD at 5356bba)

---

## Symptom
The fullscreen player's back button hangs indefinitely instead of instantly exiting/back navigating. User report: "It always hangs. Let the back button be the same as the normal screen. It should just go back instantly."

---

## Root Cause: Infinite Recursion in Back Handler Chain

### The Recursion Cycle

```
1. User presses back (UI button or keyboard/remote)
        │
        ▼
2. ImmersivePlayer._on_back_sync() → _on_back()  [immersive_player.py:1691-1719]
        │
        ▼
3. _on_back() awaits self.on_close()  [line 1715-1717]
        │
        ▼
4. on_close = lambda: _close_player()  [app_shell.py:540]
        │
        ▼
5. _close_player() calls page.run_task(_player_back)  [app_shell.py:684]
        │
        ▼
6. _player_back() awaits player._on_back(None)  [app_shell.py:644]
        │
        └──────────────────────────────► BACK TO STEP 2 (INFINITE LOOP)
```

### Code Evidence

**immersive_player.py:1708-1719** - `_on_back` awaits `on_close`:
```python
async def _on_back(self, e=None):
    if self.on_close:
        try:
            result = self.on_close()
            if asyncio.iscoroutine(result):
                await result  # ← AWAITS _close_player() which schedules _player_back()
        except Exception as ex:
            logger.error("Error executing on_close callback: %s", ex)
```

**app_shell.py:637-647** - `_player_back` awaits `player._on_back`:
```python
async def _player_back():
    player = _active_player
    if player is not None:
        try:
            await player._on_back(None)  # ← CALLS BACK INTO _on_back()
        except Exception:
            logger.debug("suppressed")
    await _async_close_player()
```

**app_shell.py:678-684** - `_close_player` schedules `_player_back`:
```python
def _close_player():
    page = flet_context.page
    if page is None:
        return
    page.run_task(_player_back)  # ← SCHEDULES _player_back (fire-and-forget)
```

---

## Why Normal (Non-Fullscreen) Back Works Instantly

In `main.py:418-442`, `_handle_global_back()`:
```python
def _handle_global_back(self):
    if close_app_dialog(self.page):
        return
    if self.ui_state.get("dialog_open"):
        self._shell_action("close_dialog")
        return
    if state.player_open:
        # The player's FocusScope handles Back and saves position first
        return  # ← DOES NOTHING - delegates to player's FocusScope
    if self.ui_state.get("view") == "anime":
        self._shell_action("back")
        return
    # Root: let OS background the app
```

The normal back is instant because it just changes view state (`set_active_view("tabs")`). The player's back *should* be similar - instant overlay removal with background cleanup.

---

## What Causes the Hang

The recursion never terminates because:
1. `_on_back()` **awaits** `on_close()` 
2. `_close_player()` schedules `_player_back()` (fire-and-forget) and returns
3. `_on_back()` completes, but `_player_back()` runs later
4. `_player_back()` **awaits** `player._on_back()` → back to step 1

Each loop iteration adds a new task to the event loop, starving the UI.

---

## Fix: Add Recursion Guard in `_on_back()`

**File:** `src/components/player/immersive_player.py`  
**Method:** `_on_back` (lines 1708-1719)

```python
async def _on_back(self, e=None):
    """Handle back button press - route through on_close callback.
    
    Matches ktv-player pattern: await on_close callback if it returns a coroutine.
    """
    # Prevent recursive calls from _player_back() → _on_back() → on_close() → _player_back()
    if self._is_closing:
        return
    self._is_closing = True
    
    if self.on_close:
        try:
            result = self.on_close()
            if asyncio.iscoroutine(result):
                await result
        except Exception as ex:
            logger.error("Error executing on_close callback: %s", ex)
```

**Why this works:**
- First call (UI back button): `_is_closing=False` → sets `True` → calls `on_close()` → schedules `_player_back()`
- Second call (from `_player_back()`): `_is_closing=True` → returns immediately
- `_player_back()` continues to `_async_close_player()` which unmounts overlay instantly
- Cleanup (position save, video stop) runs in background via `will_unmount()` → `handle_close()` (spawned task)

---

## Expected Behavior After Fix

| Action | Before Fix | After Fix |
|--------|-----------|-----------|
| Press back in fullscreen | Hangs (infinite recursion) | Instantly exits to anime detail |
| Press back in normal player | Works (delegates to FocusScope) | Works (same) |
| Position save | Never completes (hung) | Background, non-blocking |
| Video stop | Never completes (hung) | Background, non-blocking |

---

## Related Commits

- **5356bba** - "fix: resolve coroutine never awaited warnings for player back/key handlers" - Added `_on_back_sync` wrapper but introduced the recursion by making `_on_back` await `on_close` which triggers `_player_back`
- **b7b4637** - "fix: remove all contextlib.suppress..." - Cleanup, unrelated

---

## Tests

**Existing tests covering back behavior:**
- `tests/test_player_back_crashes.py` - Tests FocusManager and focus_scope back handling
- `tests/test_player_spec.py` - Player spec round-trip

**Recommended test addition:** Add test for `_on_back` recursion guard in `test_player_back_crashes.py`

---

## Severity

**HIGH** - User-facing hang on primary navigation action (back button in fullscreen player). Blocks core user flow.

---

## Summary (5 Bullets)

- **Symptom:** Fullscreen player back button hangs indefinitely; normal screen back works instantly
- **Root Cause:** Infinite recursion between `ImmersivePlayer._on_back()` → `on_close()` → `_close_player()` → `_player_back()` → `player._on_back()` 
- **Fix:** Add `_is_closing` guard in `immersive_player.py:_on_back()` to break recursion; allows `_player_back()` to complete and call `_async_close_player()` for instant overlay removal
- **Tests:** Existing `test_player_back_crashes.py` covers focus_scope/FocusManager; add recursion guard test
- **Severity:** HIGH - blocks core navigation in fullscreen mode