# DDGS → animepahe-tv port reference

Source studied: `C:\Users\nwoki\.zcode\workspace\default\DDGS\src\`
Target studied: `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\src\`
Date: 2026-10-11. Every claim below cites the file (and line range) it was read from. No inference without a citation.

Conventions: `DDGS:` = `C:\Users\nwoki\.zcode\workspace\default\DDGS\src\…`;
`ANIME:` = `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\src\…`.

---

## 1. Feature inventory (DDGS, file-by-file)

### 1.1 Screens

| Screen | File | What it does |
|---|---|---|
| Home (search-first dashboard) | `DDGS:screens/home_screen.py` | `ft.SearchBar` + paste button + category chips + collapsible Search Tools + recent-3 + feature cards + How-It-Works + privacy banner + offline banner + 2 banner ads |
| Results | `DDGS:screens/results_screen.py` | AppBar (back, query title, result count / loading subtitle, version chip, cancel/close), shimmer loading box, classified error box, per-type card builders, in-feed banner ad every 4th card, AI overview, cache banner, Load-more button |
| History | `DDGS:screens/history_screen.py` | `ft.Dismissible` rows with swipe-to-delete, re-search on tap, clear-all behind confirm dialog with Undo snackbar, empty-state illustration |
| Settings | `DDGS:screens/settings_screen.py` + `DDGS:components/settings/sections_*.py` | Theme 3-cards, AI section, Premium section (channel-gated), Search Rules (safe-search chips, region dropdown, max-results slider, timelimit), Backends per category, Extraction format, Downloads, Connection (proxy/SSL/threads), Performance, Logs, Storage, About + exactly 3 banner ads (order pinned by a guard test) |
| Onboarding | `DDGS:screens/onboarding_screen.py:66-162` | Swipeable slides (`_build_slide`, `_build_dots`, `_on_swipe`, `_on_next`, `_on_skip`, `_finish`), gates `AppShell` on `state.has_accepted_terms` |
| Chat / Assistant | `DDGS:screens/chat_screen.py` (ref `DDGS:app_shell.py:146-160`, `DDGS:app_controller.py:1033-1087`) | Full-screen agentic chat opened from FAB; back minimizes instead of destroying (`chat_open`→`chat_minimized`, `_persist_history`); FAB tooltip flips New-chat ↔ Restore |
| Content reader | `DDGS:screens/content_reader_screen.py:117-151` | Pushes a new `page.views` entry; chains its own keyboard handler on top of the global one, restores the previous handler on pop |

### 1.2 App architecture

- **Controller owns everything.** `DDGS:app_controller.py:38-48` — `AppController(page)` holds `storage`, `search_service`, `ad_service`, `connectivity`, `update_service`, `premium`, `billing=None`. `ANIME:main.py:52-71` is structurally identical (scraper, kwik, cache, router, hls_proxy, downloads, focus_manager). Both are "controller owns services, shell owns navigation".
- **Mount via contexts + `page.render`.** `DDGS:app_controller.py:170-188`: builds `ControllerMethods(...)` then `page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`, stashes `page._ddgs_controller`. `ANIME:main.py:1346` does the same: `page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`.
- **Observable state singleton.** `DDGS:core/state.py:84-196` (`@ft.observable class AppState`, module-level `state`). `ANIME:state/app_state.py:55-132` — same pattern, plus explicit `*_version` counters (`latest_version`, `search_version`, `episodes_version`, `busy_version`, …) as re-render triggers instead of relying on deep-diff.
- **Two contexts.** `DDGS:contexts/controller_ctx.py` (methods) + `DDGS:contexts/app_state_ctx.py` (state). `ANIME:state/controller_ctx.py` + `ANIME:state/app_state.py` (`AppStateCtx`) — same split. One deliberate difference, see §5.
- **Settings persistence split.** DDGS controller exposes **two** entry points — sync `save(key, value)` (applies to state immediately, persists in background) and async `save_async`/`save_setting` — `DDGS:app_controller.py:442-483`. The docstring at `:443-451` explains why: state previously only changed after the async write so a tap "appeared to do nothing". Anime has no equivalent split; every settings write is `spawn(store.put…)` from the screen (`ANIME:screens/settings_screen.py:195-229, 252-270`).
- **Global keyboard.** `DDGS:app_controller.py:663-687`: `page.on_keyboard_event` handles `Escape` → `page.pop_dialog()` and `Ctrl+K` → focus home search bar via `page._ddgs_search_bar` (set at `DDGS:screens/home_screen.py:986`). The reader screen chains on top (`DDGS:screens/content_reader_screen.py:117-151`). Anime routes Back/Escape through `FocusManager` + `ui_state` dict (`ANIME:main.py:119-124, 251-285`) — equivalent coverage for Back, no Ctrl+K equivalent.
- **Lifecycle.** `DDGS:app_controller.py:284-317`: background → `storage.flush()`; foreground → re-probe connectivity + debounced licence `reconcile_if_due`. Plus `on_app_close` (`:1287-1308`): stop chat turn first, `flush_now`, shutdown premium/router. Anime has no `on_app_close` flush; its store writes through immediately (`ANIME:services/store.py:94-99`).

### 1.3 Services

| Service | DDGS file | Notes portable to anime |
|---|---|---|
| Storage | `DDGS:services/storage_service.py` | JSON doc + in-memory cache, 1 s debounced writes (`_WRITE_DEBOUNCE_SEC = 1.0`, `:86`), atomic tmp→replace (`:146-165`), legacy migration (`:72-83`), web/SharedPreferences branch, malformed-history-row self-heal (`:278-303`), `flush_now` for exit |
| Search | `DDGS:services/search_service.py:161-228, 228-435` | `cancel()` flag checked between pages; per-type `search()`; extract path; YouTube/OpenLibrary fallbacks (`:80-160, :565-630`) |
| Cache (results) | `DDGS:services/cache_service.py:47-64, 119-285` | `search_key(query, type, **filters)` folds **every** filter into the key; stale-while-revalidate in controller (`app_controller.py:786-797`); TTL prune every 30 min (`app_controller.py:1198-1225`) |
| Ads | `DDGS:services/ad_service.py:28-64, 79-96, 146-271` | UMP consent, `preload_interstitial`, single-use interstitial replacement, **central 60 s gap** (`MIN_INTERSTITIAL_GAP = 60.0`, stamped only on a fired impression, `state.last_interstitial_ts`) |
| Updates | `DDGS:services/update_service.py:60-120` | 4 s-timeout JSON feed check, build-number compare, announcement type bypasses version gate, returns dict incl. `mandatory`, `github_url`, `playstore_url`, `action_url` |
| Connectivity | `DDGS:app_controller.py:84-101, 211-233` | Native `ft.Connectivity` service, `state.is_online` defaults `True` ("a slow probe never shows a spurious offline banner", `core/state.py:121-124`), fail-fast re-probe in `start_search` (`app_controller.py:747-778`) with cached-results-beats-offline-card rule |
| Premium/licence | `DDGS:app_controller.py:126-130, 258-282`, `services/premium_service.py`, `services/license_service.py` | Offline token verdict before first frame (`:139-148`), entitlement OR-arbiter (Play flag + licence flag), hourly reconcile loop, licence-price catalog prefetch |
| AI/router | `DDGS:app_controller.py:1148-1196, 1227-1268` | Catalog snapshot + 3 s-foreground/30 s-background watchdog that only writes state on change; scrape scheduler (60 s tick) |
| Logging | `DDGS:core/utils.py:179-259` | `log_search_event`, `log_error`, `log_performance`, `log_ddgs_call`; `sanitize_url` (`:421-…`); `classify_error` (`:494-…`) |

### 1.4 Header

Full treatment in §2 (theme toggle) and §4 below. Shape: `DDGS:components/app_header.py:140-259` — `AppHeader(page, title, subtitle, show_back, on_back, show_settings, on_settings, show_theme, extra_actions, leading_control)`; left = icon-or-back + title column; right = version chip **first**, then `extra_actions`, then theme toggle, then settings gear; outer Row `scroll=AUTO` (Sherlock rule: scroll, never clip). Docstring (`:1-13`) and inline comment (`:209-211`) pin the version-chip-leads ordering.

### 1.5 Ads, updates, connectivity, error handling

- **Banner factory.** `DDGS:core/styles.py:12-78` (`build_banner_ad`): premium/mobile-platform gate, native 320×50 ad centered inside an `expand=True` glass stretched by an outer Row (the "320 px pin" fix, `:16-24`), never sets alignment on the wide Container (`:23`). Anime's `ANIME:components/banner_ad.py:41-84` already mirrors this; deltas in §4.
- **Interstitial cadence.** Every search and every extract fires `show_interstitial()` (`DDGS:app_controller.py:874-877, 964-965`); the 60 s gap is enforced centrally in the service. Anime fires one-shot between episodes with no gap (`ANIME:services/ads.py:54-66`, `ANIME:main.py:502-508`).
- **Update UX.** Boot check → `state.update_available/update_data` (`DDGS:app_controller.py:190-202`); mandatory opens the dialog immediately; version chip morphs (§4); two-mode dialog — update-available (per-channel single destination: Play→Play Store only, direct→GitHub only) vs up-to-date (version + bundled changelog + live re-check) — `DDGS:components/update_dialog.py:1-264`. Anime: boot check + morphing pill + one-mode dialog (`ANIME:components/update_dialog.py:21-76`); no up-to-date mode, no mandatory branch, no re-check.
- **Offline.** Persistent non-blocking strip (`DDGS:components/offline_banner.py:17-45`, `visible=not state.is_online`), plus classified error cards (`DDGS:components/results/empty_states.py:79-160`: offline / server / generic + Retry; dedicated video rate-limit box `:163-254` with "Try Web Search" escape hatch), plus `classify_error` (`DDGS:core/utils.py:494-518`).
- **Snackbar discipline.** Every snack goes through `DDGS:core/snack.py:28-54`: `page.show_dialog(snack)` **plus** a 5 s local backstop task that closes that exact bar (flet snackbars stranded in the dialog stack freeze all input — the module docstring `:1-11`).
- **Cache banner.** `DDGS:components/cache_banner.py:18-70`: "Showing saved results. Refreshing…" (spinner) vs "…from this device." + Refresh button. Wired in results screen `:212-238` with the `results_from_cache && results` visibility guard.

---

## 2. The theme system in exact detail (the pattern to replicate)

### 2.1 Palette + helpers — `DDGS:core/theme.py` quoted verbatim

Constants (`:6-32`):

```python
class AppColors:
    # Brand Orange Palette
    PRIMARY = "#B33A1D"  # Premium Dark Orange/Terracotta
    PRIMARY_LIGHT = "#DE5833"  # Standard Brand Orange
    PRIMARY_DARK = "#8E250F"  # Deep Pressed Orange
    ACCENT = "#0EA5E9"  # Sky Blue accent for visual variety

    SUCCESS = "#2E7D32"  # Clean Material Green
    WARNING = "#F9A825"  # Amber Gold
    ERROR = "#D32F2F"  # Red

    # Premium Neutral Slate Dark Mode Palette
    DARK_BG_1 = "#0F1114"  # Deep Slate-Black Background
    DARK_BG_2 = "#121518"  # Slate Surface
    DARK_SURFACE = "#1A1D22"  # Card Background
    DARK_SURFACE_2 = "#252A30"  # Dialog Background
    DARK_BORDER = "#2E3339"  # Outline / Divider Border
    DARK_TEXT = "#ECEFF1"  # Primary Text
    DARK_TEXT_DIM = "#90A4AE"  # Secondary text

    # Premium Neutral Slate Light Mode Palette
    LIGHT_BG = "#FAFAFA"  # Pure clean warm background
    LIGHT_SURFACE = "#FFFFFF"  # Pure White Cards
    LIGHT_SURFACE_2 = "#F5F5F5"  # Soft divider focus surface
    LIGHT_BORDER = "#E0E0E0"  # Soft divider border
    LIGHT_TEXT = "#1A1A2E"  # Deep Charcoal slate body text
    LIGHT_TEXT_DIM = "#757575"  # Secondary gray text
```

Page-resolving colour getters (`:34-80`) — every one follows this shape:

```python
@staticmethod
def _resolve_page(page: ft.Page | None) -> ft.Page | None:
    """Return the active page, falling back to ``flet.context.page``."""
    if page is not None:
        return page
    try:
        from flet import context as flet_context

        return flet_context.page
    except Exception:
        return None


@staticmethod
def get_bg(page: ft.Page | None = None) -> str:
    resolved = AppColors._resolve_page(page)
    is_dark = is_dark_mode(resolved)
    return AppColors.DARK_BG_1 if is_dark else AppColors.LIGHT_BG


# get_surface / get_surface_2 / get_border / get_text / get_text_dim identical
```

Dark-mode predicate (`:83-101`):

```python
def is_dark_mode(page: ft.Page | None) -> bool:
    """Check if the page is currently in dark mode (explicit or system). ..."""
    if page is None:
        try:
            from flet import context as flet_context

            page = flet_context.page
        except Exception:
            return True  # fallback to dark
    if page is None:
        return True
    return page.theme_mode == ft.ThemeMode.DARK or (
        page.theme_mode == ft.ThemeMode.SYSTEM and page.platform_brightness == ft.Brightness.DARK
    )
```

Glass helpers (`:104-123`):

```python
GLASS_BG = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
GLASS_BORDER_COLOR = ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
LIGHT_GLASS_BG = ft.Colors.with_opacity(0.04, ft.Colors.BLACK)
LIGHT_GLASS_BORDER = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)


def adaptive_glass_bg(page: ft.Page | None = None) -> str:
    """Return card background color appropriate for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BG
    return GLASS_BG


def adaptive_glass_border(page: ft.Page | None = None) -> str:
    """Return card border color appropriate for current theme."""
    if page and not is_dark_mode(page):
        return LIGHT_GLASS_BORDER
    return GLASS_BORDER_COLOR
```

Card/gradient styles (`:126-198`): `AppStyles.section_card(title, icon, content, page)` (frosted card: icon+title row, 8 %-opacity divider, radius 12, theme bg + border), `glass_card(content, page)`, `brand_gradient(page)` (dark: `DARK_BG_1→DARK_BG_2`; light: `#F5F5F5→LIGHT_BG`). Themes (`:201-248`): `AppTheme.get_light_theme()` / `get_dark_theme()` build full `ft.ColorScheme`s (primary/on_primary/primary_container/secondary/surface/on_surface/surface_container/surface_container_highest/on_surface_variant/error/outline/outline_variant), `font_family="Outfit"`, `visual_density=COMFORTABLE`.

### 2.2 The 3-way cycle — canonical implementation, quoted

Icon reflects **current** mode (`DDGS:components/app_header.py:109-116`):

```python
def _theme_icon(page: ft.Page | None) -> ft.IconData:
    if page is None:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.DARK:
        return ft.Icons.DARK_MODE_ROUNDED
    if page.theme_mode == ft.ThemeMode.LIGHT:
        return ft.Icons.LIGHT_MODE_ROUNDED
    return ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED
```

Cycle DARK → LIGHT → SYSTEM → DARK, persisting through the controller (`:119-137`):

```python
def _cycle_theme(page: ft.Page | None) -> None:
    if page is None:
        return
    if page.theme_mode == ft.ThemeMode.DARK:
        new_mode = ft.ThemeMode.LIGHT
    elif page.theme_mode == ft.ThemeMode.LIGHT:
        new_mode = ft.ThemeMode.SYSTEM
    else:
        new_mode = ft.ThemeMode.DARK

    page.theme_mode = new_mode
    state.theme_mode = new_mode
    ctrl = getattr(page, "_ddgs_controller", None)
    if ctrl is not None and hasattr(ctrl, "save"):
        ctrl.save("theme", new_mode.value)
    try:
        page.update()
    except Exception:
        pass
```

Wired into the header (`:216-224`):

```python
    if show_theme:
        right_controls.append(
            ft.IconButton(
                icon=_theme_icon(page),
                icon_size=20,
                on_click=lambda e: _cycle_theme(page),
                tooltip="Toggle Theme",
            )
        )
```

Persistence path, in order:

1. Boot defaults to SYSTEM: `DDGS:app_controller.py:57-61` sets `page.theme/dark_theme` then `page.theme_mode = ft.ThemeMode.SYSTEM`.
2. Stored value overrides: `DDGS:app_controller.py:333-339` —
   ```python
   t = await storage.get_theme()
   self.page.theme_mode = {
       "dark": ft.ThemeMode.DARK,
       "system": ft.ThemeMode.SYSTEM,
       "light": ft.ThemeMode.LIGHT,
   }.get(t, ft.ThemeMode.SYSTEM)
   state.theme_mode = self.page.theme_mode
   ```
   Default `"system"` (`DDGS:services/storage_service.py:89`, `STORAGE_THEME = "theme"` at `DDGS:core/constants.py:5`, `get_theme/set_theme` at `storage_service.py:256-260`).
3. `save("theme", new_mode.value)` fans out via `_setter_map` (`DDGS:app_controller.py:408`) to `_apply_state` (`:454-468`), which maps the string back to the enum, sets **both** `page.theme_mode` and `state.theme_mode`, and schedules the storage write; the async half (`save_setting`, `:470-483`) deliberately skips re-assigning state for `"theme"` ("assigning the raw string here used to clobber it").
4. Settings screen mirrors with three explicit cards: `DDGS:components/settings/sections_general.py:13-67` (`create_theme_card` × Light/Dark/System, selected = 2 px primary border + 10 % primary fill, `on_click=lambda e: page.run_task(change_theme_fn, mode)`), read via `_current_theme()` mapping enum→string (`DDGS:screens/settings_screen.py:68-74`).

### 2.3 What animepahe-tv has today (same shape, three gaps)

- Palette + themes: `ANIME:core/theme.py:4-138` — `AppColors` (rose primary, slate dark, slate-50 light), `_is_dark(page)` (`:34-43`, same SYSTEM+platform_brightness rule), `get_glass_bg/get_hover_bg/get_surface_variant`, `AppTheme` with pinned `surface_container_*` roles (`:79-106`, comment explains the purple-tint fallback it prevents). **Gap A:** no `get_bg/get_surface/get_border/get_text/get_text_dim` page-resolving getters — each call site hand-rolls the mode check (e.g. `get_surface_variant` `:58-71` repeats the if/try chain; `home_screen` `:635-639` inlines `DARK_SURFACE if is_dark else LIGHT_SURFACE`).
- Cycle: `ANIME:screens/home_screen.py:214-224` (`_theme_cycle`: `order = (DARK, LIGHT, SYSTEM)`, `nxt = order[(index+1) % 3]`, icon map keyed by **current** mode) + `_toggle_theme` (`:438-447`: set `page.theme_mode`, `page.update()`, `spawn(save_theme_mode)`). Boot restore `ANIME:main.py:164-176` + `save_theme_mode`/`_theme_name` (`:178-191`) + store `get_theme_mode/save_theme_mode` (`ANIME:services/store.py:266-271`). **Same order as DDGS** (DARK→LIGHT→SYSTEM), matching icon semantics.
- **Gap B:** the toggle lives only in the Home header (`ANIME:screens/home_screen.py:158-211`) — Search/Downloads/Settings have no theme control. DDGS renders it in the shared `AppHeader` on every screen (`DDGS:components/app_header.py:216-224`) and keeps it on History too (`DDGS:screens/history_screen.py:252-263`).
- **Gap C:** no state-mirror of the mode and no Settings 3-card picker. DDGS writes `state.theme_mode` on every transition (header `:130`, `_apply_state` `:466`) and offers Light/Dark/System cards in Settings (`sections_general.py:13-67`). Anime persists the string but never mirrors it into `ANIME:state/app_state.py` and offers no Settings picker (`ANIME:screens/settings_screen.py:83-362` — no theme row at all).
- Minor: anime's glass helper hardcodes white-on-dark values (`ANIME:components/banner_ad.py:81-82`, `bgcolor=with_opacity(0.05, WHITE)`) instead of branching on `is_dark_mode` like `adaptive_glass_bg/border` (`DDGS:core/theme.py:112-123`).

---

## 3. Search UX patterns worth porting (dual file+line refs)

### 3.1 Submit-driven search, debounce only for suggestions

- DDGS home: `ft.SearchBar(..., full_screen=True, on_submit=…, on_change=set_search_query, autofocus=False)` (`DDGS:screens/home_screen.py:619-668`); typing updates local state only, Enter/button fires `controller.start_search` (`:373-379`). Anime already follows this exact rule and documents it in the module docstring (`ANIME:screens/search_screen.py:1-8`): `ft.TextField(on_submit=_submit, on_change=_on_change)` (`:254-278`), `use_debounce(query, 250)` (`:172`) applied **only** to the suggestion filter (`:241-246`). Both debounces share the 250 ms default (`DDGS:hooks/use_debounce.py:13`, `ANIME:hooks/use_debounce.py:15`). **Port note:** not a gap — a confirmed parity; keep the rule. One portable extra: DDGS's `use_search()` hook (`DDGS:hooks/use_search.py:13-36`) wrapping `start/extract/cancel` for components; anime screens call `controller.load_search` directly (`ANIME:screens/search_screen.py:201, 226, 359-365`).

### 3.2 Search field craft

- Per-tab hint map: `_HINT_MAP` text/images/videos/news/books/extract (`DDGS:screens/home_screen.py:91-98`) bound to `bar_hint_text` (`:621`). Anime has one static hint (`ANIME:screens/search_screen.py:255`, `hint_text="Search anime..."`) — port is trivial if multi-source search ever lands; today N/A (single provider search).
- Paste-from-clipboard trailing action (`DDGS:screens/home_screen.py:626-634`, `_on_paste` `:381-391` via `ft.Clipboard()`). Anime has no paste button — **worth porting** (TV/long-press paste is poor; one `IconButton` + 10-line handler).
- Input clamp: anime already clamps (`ANIME:screens/search_screen.py:248-252`, `[:MAX_SEARCH_QUERY_LENGTH]`, `MAX_SEARCH_QUERY_LENGTH = 200` at `ANIME:core/constants.py`). Parity.
- Double-submit guard + inline spinner: anime (`ANIME:screens/search_screen.py:180-184` guard on `state.is_loading`; `:282-296` ProgressRing-inside-button). DDGS has no equivalent guard on Home (only task-cancel in `start_search`, `DDGS:app_controller.py:780-781`). **Reverse-port candidate:** DDGS could take anime's guard.

### 3.3 Suggestions / recent searches

- DDGS: last-3 history rows as glass `_history_row` cards with type icon + timestamp + arrow (`DDGS:screens/home_screen.py:159-200, 422-436`), tap re-fires that type's search (`:398-401`), "View all history" arrow to tab 1 (`:830-833`). No live filtering of suggestions while typing.
- Anime: **superset** — debounced substring filter over `{title, session}` rows matching the *opened anime title* (`ANIME:screens/search_screen.py:237-246`, `_row_title_session` `:32-43`), tap opens the anime directly when a session exists else searches (`:203-226`), Clear-recent button (`:328-332`). Keep anime's; consider DDGS's timestamp/type subtitle line (`f"{label} · {rc} results · {ts}"`, `DDGS:screens/history_screen.py:165`) if recents ever need metadata.

### 3.4 History screen

- DDGS (`DDGS:screens/history_screen.py`): `ft.Dismissible` swipe-to-delete with red delete background (`:125-138`), per-row icon tile + `query` + `type · count · timestamp` (`:139-199`), delete handling removes from observable list then `save_async("history", …)` (`:54-63`), clear-all behind `AlertDialog` with **Undo** snackbar restoring a deep copy (`:65-109`), header carries clear-all + back + settings + theme (`:240-263`), empty state (`:205-237`).
- Anime history lives inline in Search (`ANIME:screens/search_screen.py:301-332`): suggestion rows only, `clear_search_history` with no confirm and no undo (`ANIME:main.py:1242-1245`), rows are `{title, session, ts}` capped at 20 with MRU dedupe (`ANIME:services/store.py:105-149`). **Port:** swipe-to-delete is not available (inline list, no Dismissible); the cheap wins are confirm-before-clear and Undo (copy DDGS `:65-109` shape; anime's `show_snack` already supports `action_label`, `ANIME:core/notify.py:25-57`).

### 3.5 Results rendering

- DDGS (`DDGS:screens/results_screen.py`): AppBar with query + `N results` / `Loading …` subtitle (`:79-98`); cancel-while-running vs close-when-done close button (`:101-112`); shimmer skeleton cards under a progress bar (`DDGS:components/results/empty_states.py:12-76`); classified error box + Retry (`:79-160`); video-rate-limit escape box (`:163-254`); in-feed banner every 4th card (`results_screen.py:169-172`); AI overview slotted above results (`:175`); `Load more` TextButton appending deduped next page (`:27-35`, controller `:689-730`).
- Anime (`ANIME:screens/search_screen.py:334-400`): centered ProgressRing (loading), cloud-off error card + Retry (`:340-354`), `EmptyState` for no-results vs never-searched (`:389-400`), portrait-card `ResponsiveRow` + inline banner + pager (`:355-388`). **Ports:** (a) skeleton/shimmer loading instead of a lone ring; (b) a `Loading…` subtitle or spinner state on the pager (anime's pager already takes `is_loading`, `ANIME:components/pagination.py:79-…`); (c) in-results Refresh/retry affordances beyond the single Retry button.

### 3.6 Filters / search tools

- DDGS Search Tools collapsible (`DDGS:screens/home_screen.py:688-803`): Safe Search / Region / Max Results / Time / Source always; +5 image filters on the images tab / +3 video filters on videos (`:507-600`); per-tab backend maps (`:44-50`, constants `:65-98`); stale-backend self-correct (`:440-446`); all writes via `controller.save` (`:461-505`). Persisted keys enumerated in `_setter_map` (`DDGS:app_controller.py:405-440`).
- Anime equivalent: content-source pin (auto vs provider, `ANIME:screens/settings_screen.py:242-332`, `ANIME:main.py:831-836`, router failover preserved). No safe-search/region concept (anime catalog, not web search) — correctly absent. **Port:** the collapsible-tools *container* pattern and the stale-value self-correct are reusable if anime ever gains search filters; today informational only.

### 3.7 Keyboard / focus

- DDGS desktop: global `Escape`→pop dialog, `Ctrl+K`→home+focus search (`DDGS:app_controller.py:663-687`, bar ref `:986`). Anime: TV-first — `FilledButton` cards (only Button takes on_focus/on_blur + per-state sides in flet 1.0.4, `ANIME:screens/search_screen.py:135-154`), `attach_focus_zoom` micro-zoom, `FocusManager` Back routing, overlay player `KeyboardListener` (`ANIME:app_shell.py:383-387`). No text-field shortcut equivalent. **Port:** Ctrl+K-style focus shortcut is desktop-only value; skip on TV, consider if desktop ships.

---

## 4. Ranked port opportunities (evidence-backed)

Ordered by value ÷ cost. Each item names the DDGS source and the anime integration point.

1. **Snackbar backstop (robustness, ~15 lines).** DDGS `core/snack.py:28-54` schedules a 5 s task closing that exact bar because a stranded snackbar swallows all taps. Anime's `show_snack` (`ANIME:core/notify.py:25-57`) handles the double-show RuntimeError but has no backstop. Integration: wrap `ANIME:core/notify.py:show_snack` body, keep its signature.
2. **Offline-first search path.** DDGS `app_controller.py:747-778`: re-probe, serve `_cached_progress` when offline, else an explicit offline `SearchProgress(ERR_NO_INTERNET)` — never a timeout wait. Anime checks `state.is_online` in `_submit/_pick` and warns (`ANIME:screens/search_screen.py:187-189, 214-216`), but has no cached-anything fallback and no offline results state. Anime already owns a `Cache` service (`ANIME:main.py:82`, sweep `:148`) — key past search result sets through it and mirror the DDGS branch shape.
3. **History clear confirm + Undo.** Copy `DDGS:screens/history_screen.py:65-109` into anime's `clear_btn` handler (`ANIME:screens/search_screen.py:328-332`). Anime's snackbar already takes `action_label`/`on_action` (`ANIME:core/notify.py:25-57`), so only the deep-copy + re-add is new.
4. **Header theme toggle on every screen + Settings picker.** Move anime's `_theme_cycle/_toggle_theme` (`ANIME:screens/home_screen.py:214-224, 438-447`) into a shared header helper used by Home/Search/Downloads/Settings (DDGS shape: `DDGS:components/app_header.py:109-137, 216-224`), and add the 3-card Light/Dark/System picker (`DDGS:components/settings/sections_general.py:13-67`) to `ANIME:screens/settings_screen.py` with enum↔string mapping (`DDGS:screens/settings_screen.py:68-77`). Also mirror `state.theme_mode` if adaptive code ever needs it without a page ref.
5. **Page-resolving colour getters.** Add `get_bg/get_surface/get_text(/_dim)/get_border` to `ANIME:core/theme.py` delegating to `_is_dark`, mirroring `DDGS:core/theme.py:34-80`, and replace the hand-rolled branches (`ANIME:core/theme.py:58-71`, `ANIME:screens/home_screen.py:635-639`, `ANIME:components/banner_ad.py:81-82` — the last also needs the dark/light glass branch DDGS has at `DDGS:core/theme.py:112-123`).
6. **Update dialog up-to-date mode + live re-check.** Anime's dialog (`ANIME:components/update_dialog.py:21-76`) only handles update-available. Add DDGS's `_show_up_to_date` branch (`DDGS:components/update_dialog.py:35-111`: version + `notes_for` changelog + "Check for Updates" re-check) so the version pill (`ANIME:screens/home_screen.py:109-156`, itself a good DDGS-chip port already done) is useful when no update exists. Adopt the per-channel single-destination rule (`DDGS:components/update_dialog.py:147-190`) if anime ever ships two stores.
7. **Storage hardening.** DDGS `services/storage_service.py`: debounced coalesced writes (`:86-87, 188-204`), atomic tmp→replace (`:146-165`), malformed-row self-heal (`:278-303`), `flush_now` on exit (`:183-185` + `on_app_close` at `DDGS:app_controller.py:1287-1308`). Anime's `JsonStore` already does atomic replace (`ANIME:services/store.py:47-56`) and v1-row migration (`:115-128`) but flushes synchronously on every write (`:94-99`) with no lifecycle flush. Port the debounce + exit flush when write volume grows (downloads progress already throttles in memory, `ANIME:main.py:1082-1104` — good).
8. **Skeleton loading + result-count subtitle.** Replace/augment anime's centered ring (`ANIME:screens/search_screen.py:334-339`) with shimmer placeholders (`DDGS:components/results/empty_states.py:12-76`) and surface counts like DDGS's AppBar subtitle (`DDGS:screens/results_screen.py:89-94`).
9. **Paste button on the search field.** `DDGS:screens/home_screen.py:626-634, 381-391`. ~15 lines into `ANIME:screens/search_screen.py:284-299`.
10. **Sync/async settings split.** If any anime setting ever appears to lag a tap, adopt DDGS's `save`/`save_async` pair (`DDGS:app_controller.py:442-483` with the `:443-451` rationale). Not needed today — noted for the record.
11. **Onboarding gate.** DDGS `screens/onboarding_screen.py:66-162` + `has_accepted_terms` gate in `AppShell` (`DDGS:app_shell.py:86-89`) + `STORAGE_ONBOARDING_DONE` (`DDGS:core/constants.py:10`, `storage_service.py:423-427`). Anime has no first-run screen. Port only if terms/consent kräver it.

Explicitly **not** recommended: safe-search/region/timelimit/backend-per-category filters (web-search concepts; anime catalog has no equivalent — anime's provider pin `ANIME:screens/settings_screen.py:242-332` is the correct analog); AI overview/chat/FAB (no anime use case); premium/licence stack (no payments in anime); scrape scheduler + router watchdog (anime's router health `ANIME:main.py:792-802` + test-all-sources panel covers diagnostics); `use_search` hook (thin wrapper; direct controller calls are fine).

---

## 5. Things animepahe-tv already does equivalently

- **3-way theme cycle, same order and icon semantics.** `ANIME:screens/home_screen.py:214-224` cycles DARK→LIGHT→SYSTEM with the icon showing the *current* mode — identical to `DDGS:components/app_header.py:109-137`. Persisted pre-first-render (`ANIME:main.py:158-176`) matching DDGS's restore-before-mount (`DDGS:app_controller.py:333-339`).
- **Pinned surface roles against Material fallback.** `ANIME:core/theme.py:74-106` pins `surface_container_*`/`outline_*` for both modes with the purple-tint comment — deeper than DDGS's `ColorScheme` (`DDGS:core/theme.py:201-248`), which sets fewer roles.
- **Debounce discipline.** 250 ms, suggestions-only, submit fires the network (`ANIME:screens/search_screen.py:1-8, 171-201` + `ANIME:hooks/use_debounce.py:15-36` vs `DDGS:hooks/use_debounce.py:13-46`). Same default, same rule.
- **Generation-counter staleness guards.** Anime `main.py:296-299, 360-367, 1183-1186` (`_latest_gen`, `_episodes_gen`, `_search_gen` discard stale responses) — same defense as DDGS's `_current_search_tasks` cancel + `is_search_running` (`DDGS:app_controller.py:48, 508-531, 580-589`).
- **Native connectivity listener.** `ANIME:main.py:204-240` (`ft.Connectivity`, `on_change`, init probe, offline/online handling + CF-retry on reconnect) mirrors `DDGS:app_controller.py:84-101, 211-233`. Distinct offline vs gated states in both (`ANIME:screens/home_screen.py:387-416` vs `DDGS:components/offline_banner.py` + `empty_states.py:79-104`).
- **Banner ad house rule.** Full-width glass + native 320×50 inside + collapse to 0×0 off mobile/TV + never against nav (`ANIME:components/banner_ad.py:41-84`, `ANIME:app_shell.py:9-11` docstring) = DDGS `core/styles.py:12-78` + `app_shell.py` FAB/nav discipline. (One nit: anime's glass is white-on-dark unconditionally, §2.3 Gap A.)
- **Version pill morph.** `ANIME:screens/home_screen.py:109-156` (quiet `v1.0.9` → accented "Update Available!" + dot, tap opens dialog) = DDGS `_build_version_chip` (`DDGS:components/app_header.py:27-106`, additionally handling the announcement variant).
- **Boot update check → observable state.** `ANIME:main.py:193-198` (`_check_for_updates_bg`, 2 s delay, sets `update_available/update_data`) = DDGS `app_controller.py:190-202` (plus mandatory auto-open, which anime correctly omits — its dialog has no mandatory mode).
- **Atomic store writes + history migration.** `ANIME:services/store.py:47-56` (tmp+`os.replace`) + `:115-128` (v1 bare-string rows migrate on read) = DDGS `services/storage_service.py:146-165` + `:278-303`.
- **Controller/context split + shell-owned navigation.** `ANIME:state/controller_ctx.py` + `ANIME:app_shell.py:53-131` (shell mutates one `ControllerMethods` instance in place; identity preserved — the module docstring calls this out) matches DDGS `contexts/controller_ctx.py` + `app_shell.py`. Anime's in-place-mutation comment is the clearer articulation of the shared rule.
- **Card craft.** Portrait cards with gradient + center play icon + bottom-left meta + equalizer-for-now-playing (`ANIME:screens/search_screen.py:46-154`) and 1.67 landscape releases (`ANIME:screens/home_screen.py:35-106`) with `FilledButton`-as-card for TV focus (`ANIME:screens/search_screen.py:135-154` comment) — anime-specific, no DDGS equivalent needed.
- **Download progress throttle.** `ANIME:main.py:1082-1104` (0.5 s flush coalescing) is the same idea as DDGS's storage write debounce (`DDGS:services/storage_service.py:86`) applied to a hotter path.
