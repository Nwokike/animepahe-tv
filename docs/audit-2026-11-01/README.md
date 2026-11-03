# Audit 2026-11-01 — animepahe-tv vs pinned flet 0.85.3 venv

**Date:** 2026-11-01 · **Platform:** Linux (Fedora 45) · **Venv Python:** 3.14.9
**Pinned in pyproject.toml:** `flet==0.85.3`, `flet-webview==0.85.3`, `flet-video==0.85.3`,
`flet-yandex-ads>=0.1.0` (installed 0.1.0), `requires-python = ">=3.12"`.
`.venv` was deleted and recreated with plain `uv sync`.

**Source of truth (per docs/reference/README.md rule):** the installed packages only —
`.venv/lib/python3.14/site-packages/` (`flet/`, `flet_video/`, `flet_webview/`,
`flet_yandex_ads/`, `primp` 2.0.1, `anyio` 4.16.0, `httpx` 0.28.1).

Method: 10 sub-agents ran in two batches — four per-section code auditors + one
test-runner (batch 1), one per flet dependency doc (batch 2). Every flet API used in
every assigned file was checked against the installed 0.85.3 tree via `getattr` /
`inspect.signature` / `dataclasses.fields` / source reads; all app modules were
imported and the full test suite + ruff were run. Auditor claims that did not
survive manual re-verification were corrected in place (see "Corrections" below).

## Bottom line

- **No real flet-0.85.3 API breakage anywhere in `src/`.** All 105 distinct `ft.*`
  names used by the app exist in installed 0.85.3; all 69 importable modules import
  cleanly; **pytest: 635 passed / 0 failed**; **ruff check src tests: clean**.
- The app was **not** written against a newer flet at the API-name level. The stale
  parts were the **docs**, not the code: `docs/reference/dep-flet*.md` described a
  venv with flet 1.0.4 — all five flet-family dep docs were re-verified/rewritten
  against 0.85.3 on 2026-11-01 (see `docs/reference/README.md` version stamps).
- Real residual items are **warnings/complexities**, not errors (listed per doc).

## Files in this folder

| File | Scope | Result |
|---|---|---|
| [test-run-2026-11-01.md](test-run-2026-11-01.md) | compileall, import-all-modules, full pytest, ruff on the pinned venv | 0 import failures, 635 passed, ruff clean |
| [entry-shell.md](entry-shell.md) | `src/main.py`, `src/app_shell.py` (153 API touchpoints) | 0 ERROR, 6 WARNING, 153 OK |
| [components.md](components.md) | all of `src/components/` incl. player (fv.Video etc.) | 0 real ERROR (5 flagged were false positives — corrected), 8 WARNING, 120+ OK |
| [screens.md](screens.md) | all of `src/screens/` | 0 real ERROR (flagged `ft.Colors.WARNING/SUCCESS` was a false positive — corrected), 13 WARNING, 140+ OK |
| [core-services.md](core-services.md) | `src/core/`, `src/services/`, `src/state/`, `src/hooks/`, `src/app/` | 0 critical ERROR (primp `resp.aclose()` claim was a false positive — corrected), 14 WARNING, 85+ OK |

Dependency docs re-verified against the 0.85.3 venv (in `docs/reference/`):
`dep-flet.md`, `dep-flet-video.md` (all 47 `fv.*` usages in the player verified),
`dep-flet-webview.md` (all WebView usages verified; note: WebView methods are gated to
mobile/macOS platforms and **exclude `ANDROID_TV``), `dep-flet-yandex-ads.md`
(imports cleanly on flet 0.85.3), `dep-flet-notifications.md` (banner added:
**not installed, not a dependency, historical only**).

## Corrections applied during consolidation (auditor false positives)

All verified live against `.venv` on 2026-11-01:

1. `ft.Colors.WARNING` / `ft.Colors.SUCCESS` "missing" (screens.md) — the app uses
   `AppColors.*` (`src/core/theme.py:48-49`); zero true `ft.Colors.WARNING/SUCCESS`
   usages exist (`grep "ft\.Colors\.WARNING" src` → no hits). Corrected in screens.md.
2. `fv.VideoSubtitleConfiguration` "requires padding" (components.md) — `padding` has
   a default in flet-video 0.85.3. False positive.
3. `ft.StoragePaths()` "requires page arg" (components.md) — signature is
   `(self, *, data, key, ref)`; no page param. False positive.
4. `page.web` "does not exist" (components.md) — `hasattr(ft.Page, "web")` is True
   (dataclass field, default False). False positive.
5. `ft.context.page` "wrong pattern" (components.md) — `ft.context is
   (from flet import context)` → True; same singleton. False positive.
6. primp `resp.aclose()` "AttributeError" (core-services.md) — app only calls
   `aclose()` on **responses**; `primp.AsyncResponse.aclose` exists in 2.0.1
   (`AsyncClient.aclose` does not, and the app never calls it — client cleanup in
   `services/providers/base.py:110-120` prefers `__aexit__`). False positive.
7. `hls_proxy.py:874` "calls `resp.__aexit__`" (core-services.md) — actual code is
   `await resp.aclose()`. Misread.

Also verified correct for 0.85.3 (old docs claimed otherwise): `ft.dropdown.Option`
**is** `ft.DropdownOption` (alias, same class); `ft.OutlineInputBorder` does **not**
exist in 0.85.3 (use `ft.InputBorder.OUTLINE`); services do **not** auto-register
(append to `page.services`); `from flet import context` resolves to the `Context`
singleton from `flet/controls/context.py` (there is no `flet/context.py` module);
`ft.Icons` has 8825 members; `Video`/`WebView` are not in `ft`.

## Genuine warnings / complexities worth keeping on the radar

- `flet_webview` WebView methods are platform-gated and **exclude `ANDROID_TV`**
  (`_check_mobile_or_mac_platform`) — the TV web fallback in `webview_solver.py` is
  deliberate; documented in dep-flet-webview.md.
- `page._dialogs.controls` private access in `src/core/dialogs.py:36` (use
  `page.show_dialog`/`pop_dialog` or `use_dialog` where possible).
- `pywebview` is only in the `dev` dependency-group; `desktop_cf_solver.py` needs it
  for desktop CF solving (fine under `uv sync`; would be missing in a non-dev
  production install).
- Defensive dead branch in `webview_solver.py:259-260` (assumes `e.data` dict;
  0.85.3 passes a plain string URL).
- No list virtualization: screens render full `Column`/`Row` lists (consider
  `GridView`/`ListView` for very large episode lists).
- Complexity hotspots (not bugs): imperative `page.overlay` mounting in main/app_shell,
  mutable global `state` dict version bumps, fire-and-forget `spawn()` with
  `session_alive()` guards, bound-method identity for `on_keyboard_event` in
  `core/focus_manager.py`.
