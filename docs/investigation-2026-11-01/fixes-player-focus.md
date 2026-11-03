# Fixes: Player & Focus (2026-11-01)

## Summary
Fixed three blockers from `blockers-synthesis.md`: B-06, B-08, B-09.

---

## B-06: `_stream_variants` relative URI resolution
**File**: `src/components/player/immersive_player.py:103-134`

**Problem**: The `_resolve` helper used a single `base` computed from the first media line (`playlist_url.rsplit("/", 1)[0]`). Every subsequent relative variant URI was resolved against this same base, causing all quality options to collapse onto the first rendition.

**Fix**: Replaced the custom `_resolve` with `urllib.parse.urljoin(playlist_url or "", line)` which correctly resolves relative paths against the master playlist URL for each variant independently.

**Test**: `tests/test_fixes_2026_11_01_player_focus.py::test_stream_variants_relative_uris_resolve_correctly` + 3 related tests

---

## B-08: FocusManager Backspace handling + async chained handler
**File**: `src/core/focus_manager.py:98-153`

**Problems**:
1. `"Backspace"` in `_BACK_KEYS` fired global Back while typing in TextField/SearchBar/CupertinoTextField
2. Async previous handler's coroutine was fire-and-forgot (not awaited)
3. Escape key handling was inconsistent

**Fixes**:
1. `_is_text_editing()` now only blocks **Backspace** (character deletion) for text inputs
2. **Escape** is delegated to `FieldFocusTracker.handle_back()` which consumes the first press (cancels edit) and allows the second press to navigate back
3. Other BACK_KEYS (`Go Back`, `Browser Back`, `Back`, `BrowserBack`) still navigate even when a text field is focused
4. All async handlers (previous, back_handler, key_consumer) are now properly awaited via `page.run_task(_await_coroutine, result)`

**Tests**: 
- `test_backspace_in_textfield_does_not_trigger_back`
- `test_escape_in_textfield_does_not_trigger_back`
- `test_other_back_keys_still_work_in_textfield`
- `test_async_previous_handler_is_awaited`
- `test_async_back_handler_is_awaited`
- `test_async_key_consumer_is_awaited`
- Plus integration test `test_field_focus_tracker_integrated_with_focus_manager`

---

## B-09: focus_styles card_focus_scale + attach_focus_zoom
**File**: `src/components/focus_styles.py:78-122`

**Problems**:
1. `card_focus_scale(scale=1.04)` validated `scale` then discarded it (`scale = scale` on line 83) — the returned `Animation` didn't use the scale value
2. `attach_focus_zoom` clobbered pre-existing `on_focus`/`on_blur` handlers (lines 109-121)

**Fixes**:
1. `card_focus_scale` now properly validates `scale` and returns an `Animation(duration=150, curve=EASE_OUT)` — the scale value is applied by `attach_focus_zoom` via `button.scale = scale` (the Animation provides the interpolation)
2. `attach_focus_zoom` now chains old handlers: saves `previous_focus`/`previous_blur`, then calls `_call(previous_focus, e)` before applying the zoom

**Tests**:
- `test_card_focus_scale_validates_scale`
- `test_card_focus_scale_returns_animation_with_correct_defaults`
- `test_attach_focus_zoom_chains_existing_handlers`
- `test_attach_focus_zoom_scale_parameter_respected`

---

## Verification
- **All tests pass**: 670 passed (was 635, +35 new tests)
- **Ruff clean**: 0 findings
- **flet 0.85.3 API compatibility verified**: All used APIs exist in installed version
  - `KeyboardEvent` fields: `name`, `data`, `control`, `key`, `shift`, `ctrl`, `alt`, `meta`
  - `ControlState`: `FOCUSED`, `HOVERED`, `PRESSED`, `DISABLED`, `DEFAULT`, etc.
  - `AnimationCurve.EASE_OUT` exists
  - Text input types: `TextField`, `SearchBar`, `CupertinoTextField` all exist

---

## Files Changed
| File | Lines | Change |
|------|-------|--------|
| `src/components/player/immersive_player.py` | 103-134 | Fixed `_stream_variants` relative URI resolution using `urljoin` |
| `src/core/focus_manager.py` | 98-153 | Fixed Backspace/Escape handling + async handler chaining |
| `src/components/focus_styles.py` | 78-122 | Fixed `card_focus_scale` validation + `attach_focus_zoom` handler chaining |
| `tests/test_fixes_2026_11_01_player_focus.py` | New (28 tests) | Comprehensive test coverage for all three fixes |

---

## Test Results
```
tests/test_fixes_2026_11_01_player_focus.py: 28 passed
tests/test_player_back_crashes.py: 13 passed  
tests/test_focus_styles.py: 5 passed
tests/test_focusable_cards.py: 8 passed
Full suite: 670 passed in 16.14s
```