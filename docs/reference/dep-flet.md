# dep-flet — flet 0.85.3 API reference (installed package)

> **Version note (2026-11-01, re-verified):** This reference now describes **flet 0.85.3
> exactly as pinned** in `pyproject.toml` (`flet==0.85.3`) and installed in this repo's
> `.venv` (Python 3.14.9, Linux). The earlier 2026-10-15 note described a venv with
> **flet 1.0.4** installed; that is no longer the case. Claims that were 1.0.4-only
> deltas are corrected below: in 0.85.3 **`ft.OutlineInputBorder` does NOT exist**
> (use `ft.InputBorder.OUTLINE`; `InputBorder` members are `NONE/OUTLINE/UNDERLINE`),
> **`ft.dropdown.Option` IS `ft.DropdownOption`** (same class, alias — verified
> `flet.controls.material.dropdown.Option is DropdownOption` → `True`), and
> **services do NOT auto-register** — the app must append to `page.services`
> (see `src/core/shared_services.py`, `src/main.py:376`).
> `from flet import context` works in 0.85.3 but resolves to the `Context` singleton
> re-exported from `flet/controls/context.py` (NOT a `flet/context.py` module —
> `import flet.context` raises ModuleNotFoundError); it exposes `.page` (raises
> RuntimeError outside app callbacks), `.enable_components_mode()`, etc.

> Source of truth: `/home/maikel/Desktop/kiri-apps/animepahe-tv/.venv/lib/python3.14/site-packages/flet/`
> Verified live via `cd /home/maikel/Desktop/kiri-apps/animepahe-tv && .venv/bin/python -c "..."`
> (`inspect.signature`, `dataclasses.fields`, `dir(ft)`, `getattr`), plus direct reads of
> the `.py` sources. Every claim below is tied to a file path + signature/docstring in this
> installed tree. Package exports **486** public names (re-verified 2026-11-01:
> `len([n for n in dir(ft) if not n.startswith('_')]) == 486`).
>
> ## 0. App usage vs flet 0.85.3 (verified 2026-11-01)
>
> - All **105 distinct `ft.*` names** used across `src/` exist in installed 0.85.3
>   (`grep -rhoP "ft\.[A-Za-z_][A-Za-z0-9_]*" src --include="*.py" | sort -u` → each
>   `getattr(ft, name)` non-None). No app code assumes flet >0.85.3 at the name level.
> - All 69 importable `src` modules import cleanly under the pinned venv; `pytest` =
>   **635 passed / 0 failed**; `ruff check src tests` = clean. See
>   `docs/audit-2026-11-01/test-run-2026-11-01.md`.
> - Per-area API audits (every flet API in every file, with status) live in
>   `docs/audit-2026-11-01/` (`entry-shell.md`, `components.md`, `screens.md`,
>   `core-services.md`). One auditor false positive (`ft.Colors.WARNING/SUCCESS`
>   "missing") was disproved: the app uses `AppColors.*` from `src/core/theme.py`;
>   `ft.Colors` in 0.85.3 indeed has no WARNING/SUCCESS members — corrected in
>   `docs/audit-2026-11-01/screens.md` §ERROR-1.
> - Known 0.85.3 facts that differ from the old 1.0.4-era notes: `ft.Icons` is an
>   8825-member proxy in 0.85.3 (not 95); `Video`/`Audio`/`WebView` are NOT in `ft`
>   (they live in `flet_video` / `flet_webview` — verified `hasattr(ft,'Video') is False`).

---

## 1. Version, packaging, module layout

### 1.1 Version

- **Flet: `0.85.3`** — `flet/version.py` sets `flet_version = "0.85.3"` ("set by CI"), confirmed by
  `from flet.version import flet_version` → `'0.85.3'` and by `flet-0.85.3.dist-info/METADATA`
  (`Name: flet`, `Version: 0.85.3`). `Requires-Python: >=3.10`.
- **Flutter SDK pinned: `3.41.7`** (`flutter_version = "3.41.7"` in `version.py`).
- **Pyodide: `0.27.7`** (`PYODIDE_VERSION`).
- Runtime deps from METADATA: `oauthlib>=3.2.2`, `httpx>=0.28.1`, `repath>=0.9.0`,
  `msgpack>=1.1.0`, `typing-extensions` (py<3.11). Extras: `cli` (`flet-cli==0.85.3`),
  `web` (`flet-web==0.85.3`), `desktop` (`flet-desktop==0.85.3`), `all`.
- Sibling packages installed alongside (separate dist-infos, separate references):
  `flet_cli-0.85.3`, `flet_desktop-0.85.3`, `flet_video-0.85.3`, `flet_webview-0.85.3`,
  `flet_notifications-0.1.3`, `flet_yandex_ads-0.1.0`.
- **Video/Audio/WebView are NOT in `flet` core**: verified `'Video' in dir(ft)` → `False`,
  `'WebView' in dir(ft)` → `False`. They live in the `flet-video` / `flet-webview` packages.

### 1.2 Top-level package layout (`flet/`)

| Path | Contents |
|---|---|
| `flet/__init__.py` | 1220 lines; re-exports everything below plus entry points. 486 public names. Also contains a module-level `__getattr__` that raises `AttributeError` for unknown names (verified: `ft.OAuthProvider` raises `AttributeError` — the class lives at `flet.auth.OAuthProvider` / `ft.Authorization` module path, not top-level). |
| `flet/app.py` | `app`, `app_async`, `run`, `run_async` entry points. `run(main, before_main=None, name='', host=None, port=0, view=AppView.FLET_APP, assets_dir='assets', upload_dir=None, web_renderer=WebRenderer.AUTO, route_url_strategy=RouteUrlStrategy.PATH, no_cdn=False, export_asgi_app=False, target=None)`. |
| `flet/version.py` | Version constants + `get_flet_version()` / `get_flutter_version()` (git-tag fallback). |
| `flet/controls/` | All controls. `core/` (38 modules), `material/` (~60 modules), `cupertino/` (26 modules), `services/` (20 modules), plus `page.py` (1429 lines), `base_page.py` (858 lines), `control.py`, `base_control.py`, `layout_control.py`, `scrollable_control.py`, `theme.py` (59-field `Theme` dataclass), `control_state.py`, `dialog_control.py`, `context.py`, `query_string.py`, `multi_view.py`, enums/types helpers. |
| `flet/components/` | Function-component engine: `component.py` (`Component` + `Renderer`, 537 lines), `component_decorator.py` (`@component`, 31 lines), `observable.py` (`Observable`, `@observable`, 441 lines), `memo.py` (`@memo`), `router.py` (`Router`, `Route`, route hooks), `hooks/` (`use_state`, `use_effect`, `use_ref`, `use_context`, `use_memo`, `use_callback`, `use_dialog`), `public_utils.py` (`unwrap_component`). |
| `flet/pubsub/` | `pubsub_client.py` (`PubSubClient`), `pubsub_hub.py` (`PubSubHub`). |
| `flet/auth/` | `authorization.py`, `authorization_service.py`, `oauth_provider.py`, `oauth_token.py`, `user.py`, `group.py`, `providers/` (`google_oauth_provider`, `github_oauth_provider`, `azure_oauth_provider`, `auth0_oauth_provider`). Top-level `ft` does NOT re-export `OAuthProvider` (verified `AttributeError`); access via `flet.auth`. |
| `flet/security/` | `__init__.py` only: `encrypt/decrypt` (Fernet+PBKDF2, salt-prefixed base64url), `encrypt_aes_gcm_256/decrypt_aes_gcm_256`. **Requires `cryptography` package** — verified `import flet.security` raises `ImportError: Install "cryptography" Python package` in this venv (not installed). |
| `flet/canvas/` | Re-export shim only — real code is `flet/controls/core/canvas/` (`Canvas`, `Arc`, `Circle`, `Line`, `Oval`, `Rect`, `Path`, `Points`+`PointMode`, `Shadow`, `Color`, `Fill`, `Text`, `Image`, `Shape`, `CanvasResizeEvent`). |
| `flet/utils/` | No public app API: `browser`, `classproperty`, `deprecated`, `files`, `hashing`, `network`, `platform_utils` (`is_mobile/is_windows/which` used by `version.py`), `strings`, `validation`, `vector`, etc. |
| `flet/messaging/`, `flet/fastapi/`, `flet/testing/` | Transport/test scaffolding, not app surface. |

### 1.3 Entry points (`flet/app.py`, re-exported in `__init__.py`)

```python
run(main: Callable[[Page], Any | Awaitable[Any]], before_main=None, name='',
    host=None, port=0, view=AppView.FLET_APP, assets_dir='assets', upload_dir=None,
    web_renderer=WebRenderer.AUTO, route_url_strategy=RouteUrlStrategy.PATH,
    no_cdn=False, export_asgi_app=False, target=None)
app(*args, **kwargs)          # flexible legacy wrapper
app_async(*args, **kwargs)
run_async(main, before_main=None, ...)
```

`Page.render(component, *args, **kwargs)` and `Page.render_views(component, *args, **kwargs)`
mount a `@component` function as the page body / views stack (verified on `ft.Page`).

### 1.4 Pub/sub (`flet/pubsub/`)

Identical API on `PubSubClient` (per-session, reached via `page.pubsub`) and `PubSubHub`
(global), verified by member scan:

```
send_all, send_all_on_topic, send_others, send_others_on_topic,
subscribe, subscribe_topic, unsubscribe, unsubscribe_all, unsubscribe_topic
```

`PubSubClient.subscribe(handler: Callable)`. `QueryString` (page.query) has `get`, `post`.

---

## 2. Control families — every control class, one line each

Source: `issubclass(v, BaseControl)` scan over `dir(ft)` → 160 classes; first-line docstrings
dumped per class. Grouping below is editorial; module paths are verbatim.

### 2.1 Layout (arrangement, containers, scroll)

| Class | Module | Purpose |
|---|---|---|
| `Column` | `controls.core.column` | Arranges children vertically with alignment/spacing. |
| `Row` | `controls.core.row` | Arranges children horizontally with alignment/spacing. |
| `Stack` | `controls.core.stack` | Overlays children with absolute positioning (`left/top/right/bottom`). |
| `Container` | `controls.material.container` | Decorates one child (bgcolor, border, padding, margin, alignment). |
| `Card` | `controls.material.card` | Panel with rounded corners + elevation shadow. |
| `ListView` | `controls.core.list_view` | Scrollable linear list of controls. |
| `GridView` | `controls.core.grid_view` | Scrollable 2D array; `runs_count / max_extent / spacing / run_spacing / child_aspect_ratio / cache_extent`. |
| `ResponsiveRow` | `controls.core.responsive_row` | Row with per-breakpoint column sizes (`col` map). |
| `PageView` | `controls.core.page_view` | Swipeable pages, `selected_index`. |
| `ReorderableListView` | `controls.material.reorderable_list_view` | List whose items the user can drag-reorder (`spacing`, `item_extent`, `first_item_prototype`, `prototype_item`, dividers). |
| `ExpansionPanelList` | `controls.material.expansion_panel` | Lays out `ExpansionPanel` children, animates expansion. |
| `ExpansionPanel` | `controls.material.expansion_panel` | Collapsible panel; body visible only when expanded. |
| `ExpansionTile` | `controls.material.expansion_tile` | Single-line `ListTile` with arrow expanding to reveal `controls`. |
| `Divider` | `controls.material.divider` | Thin horizontal rule with side padding. |
| `VerticalDivider` | `controls.material.vertical_divider` | Thin vertical rule. |
| `SafeArea` | `controls.core.safe_area` | Insets content away from system intrusions (notch, status bar). |
| `Pagelet` | `controls.core.pagelet` | Mini page scaffold (appbar + content) embeddable inside a page. |
| `View` | `controls.core.view` | One entry of `page.views`: own `route`, appbar/drawer/nav-bar slots, `can_pop`, `on_confirm_pop`, `fullscreen_dialog`, `services`. Full signature in §3.4. |
| `Window` | `controls.core.window` | Desktop window control: `center/close/destroy/to_front/start_dragging/start_resizing/wait_until_ready_to_show`. |
| `WindowDragArea` | `controls.core.window_drag_area` | Draggable region for frameless windows. |
| `RotatedBox` | `controls.core.rotated_box` | Rotates child by quarter turns in layout. |
| `Placeholder` | `controls.core.placeholder` | Sized box drawing a placeholder (layout debugging). |
| `MergeSemantics` | `controls.core.merge_semantics` | Merges semantics of descendants for accessibility. |
| `Semantics` | `controls.core.semantics` | Labels a subtree for accessibility (`tooltip`, `badge`, `content`). |
| `TransparentPointer` | `controls.core.transparent_pointer` | Passes pointer events through to controls below. |
| `SelectionArea` | `controls.material.selection_area` | Makes `content` text-selectable; `on_change`. |
| `AutofillGroup` | `controls.core.autofill_group` | Groups autofillable fields (`AutofillGroupDisposeAction`, `AutofillHint`). |
| `FletApp` | `controls.core.flet_app` | Embeds another Flet app (like IFRAME); `FletAppOutputEvent`. |
| `MultiView` | `controls.multi_view` | Multi-window/view host (docstring "TBD" — immature API). |

### 2.2 Buttons (all 29 focusable widgets are in this + inputs families, §6.1)

| Class | Module | Purpose |
|---|---|---|
| `Button` | `controls.material.button` | Base Material button. |
| `ElevatedButton` | `controls.material.elevated_button` | Elevated filled button. |
| `FilledButton` | `controls.material.filled_button` | Highest-emphasis filled button. |
| `FilledTonalButton` | `controls.material.filled_tonal_button` | Mid-emphasis tonal button. |
| `OutlinedButton` | `controls.material.outlined_button` | Outlined, low-emphasis button. |
| `TextButton` | `controls.material.text_button` | Text-only button. |
| `IconButton` | `controls.material.icon_button` | Round ink-reaction icon button. |
| `FilledIconButton` / `FilledTonalIconButton` / `OutlinedIconButton` | `controls.material.icon_button` | Filled / tonal / outlined icon-button variants. |
| `FloatingActionButton` | `controls.material.floating_action_button` | Circular hover-above-content primary-action button. |
| `Chip` | `controls.material.chip` | Compact attribute/entity/action element (`on_click/on_delete/on_select`). |
| `PopupMenuButton` + `PopupMenuItem` | `controls.material.popup_menu_button` | Overflow menu button + one menu row. |
| `MenuBar` | `controls.material.menu_bar` | Bar managing cascading child menus (desktop). |
| `MenuItemButton` | `controls.material.menu_item_button` | Click- or keyboard-activatable menu row. |
| `SubmenuButton` | `controls.material.submenu_button` | Menu row opening a submenu (`on_open/on_close`). |
| `SegmentedButton` + `Segment` | `controls.material.segmented_button` | Multi-segment single/multi-select control. |
| `CupertinoButton` | `controls.cupertino.cupertino_button` | iOS-style button. |
| `CupertinoFilledButton` | `controls.cupertino.cupertino_filled_button` | iOS filled button. |
| `CupertinoTintedButton` | `controls.cupertino.cupertino_tinted_button` | iOS tinted-background button. |
| `CupertinoSegmentedButton` | `controls.cupertino.cupertino_segmented_button` | iOS segmented button. |
| `CupertinoSlidingSegmentedButton` | `controls.cupertino.cupertino_sliding_segmented_button` | iOS sliding-thumb segmented button. |
| `CupertinoContextMenu` + `CupertinoContextMenuAction` | `controls.cupertino.cupertino_context_menu*` | Full-screen long-press modal menu + one action. |
| `CupertinoActionSheet` + `CupertinoActionSheetAction` | `controls.cupertino.cupertino_action_sheet*` | iOS bottom action sheet + one action. |
| `CupertinoDialogAction` | `controls.cupertino.cupertino_dialog_action` | Action button inside a Cupertino dialog. |
| `ReorderableDragHandle` | `controls.core.reorderable_drag_handle` | Drag handle for reorderable list items. |

### 2.3 Inputs & selection

| Class | Module | Purpose |
|---|---|---|
| `TextField` | `controls.material.textfield` | Material text input (`on_change/on_submit/on_selection_change/on_tap_outside`, `autofocus`, `focus()` method — §6.1). |
| `CupertinoTextField` | `controls.cupertino.cupertino_textfield` | iOS text field, same event set. |
| `SearchBar` | `controls.material.search_bar` | Material search field (`bar_leading/bar_trailing/bar_hint_text/bar_bgcolor`, `autofocus`, `on_tap/on_tap_outside_bar/on_submit/on_change`). |
| `AutoComplete` | `controls.material.auto_complete` | Text input with suggestion dropdown (`suggestions`, `suggestions_max_height`). |
| `Dropdown` + `DropdownOption` | `controls.material.dropdown` | Single-select dropdown (`options`, `on_select/on_text_change`). |
| `DropdownM2` | `controls.material.dropdownm2` | Legacy Material-2 dropdown (`on_change/on_click`). |
| `Checkbox` | `controls.material.checkbox` | Multi-select toggle (`on_change`). |
| `CupertinoCheckbox` | `controls.cupertino.cupertino_checkbox` | macOS-style checkbox. |
| `Switch` | `controls.material.switch` | On/off switch (`on_change`). |
| `CupertinoSwitch` | `controls.cupertino.cupertino_switch` | iOS switch (`on_change`, `on_image_error`, `on_label_color`). |
| `Radio` + `RadioGroup` | `controls.material.radio*` | Single-choice radio + group binding. |
| `CupertinoRadio` | `controls.cupertino.cupertino_radio` | macOS-style radio. |
| `Slider` | `controls.material.slider` | Continuous slider (`on_change/on_change_start/on_change_end`). |
| `CupertinoSlider` | `controls.cupertino.cupertino_slider` | iOS slider, same events. |
| `RangeSlider` | `controls.material.range_slider` | Dual-thumb range slider. |
| `DatePicker` | `controls.material.date_picker` | Material date-picker dialog (`value/first_date/modal`, `DatePickerEntryMode/Mode`). |
| `DateRangePicker` | `controls.material.date_range_picker` | Material date-range dialog. |
| `TimePicker` | `controls.material.time_picker` | Material time-picker (`value/locale/modal`, `TimePickerEntryMode/HourFormat`). |
| `CupertinoDatePicker` | `controls.cupertino.cupertino_date_picker` | iOS date picker (`CupertinoDatePickerDateOrder/Mode`). |
| `CupertinoTimerPicker` | `controls.cupertino.cupertino_timer_picker` | iOS countdown picker (`CupertinoTimerPickerMode`). |
| `CupertinoPicker` | `controls.cupertino.cupertino_picker` | Generic iOS wheel picker. |
| `FormFieldControl` | `controls.material.form_field_control` | Abstract base of form fields; owns `focus()` (verified `FormFieldControl.focus` exists; `Control`/`BaseControl` have no focus members). |

### 2.4 Dialogs, sheets, bars, overlays

| Class | Module | Purpose |
|---|---|---|
| `DialogControl` | `controls.dialog_control` | Abstract dialog base: `open: bool = False`, `on_dismiss`. Everything below extends it. |
| `AlertDialog` | `controls.material.alert_dialog` | Acknowledgement dialog (`title/content/actions/modal/bgcolor/elevation/icon/*_padding/actions_alignment/shape`). |
| `CupertinoAlertDialog` | `controls.cupertino.cupertino_alert_dialog` | iOS alert dialog. |
| `BottomSheet` | `controls.material.bottom_sheet` | Modal bottom sheet (`content`, `elevation`). |
| `CupertinoBottomSheet` | `controls.cupertino.cupertino_bottom_sheet` | iOS bottom sheet. |
| `SnackBar` + `SnackBarAction` | `controls.material.snack_bar` | Transient bottom message + action (`DismissDirection`, `SnackBarBehavior`). |
| `Banner` | `controls.material.banner` | Persistent important message with actions; requires user action. |
| `Tooltip` | `controls.material.tooltip` | Hover/long-press hint wrapper (also accepted as `Control.tooltip`). |
| `Badge` | `controls.material.badge` | Count/status adornment (also accepted as `Control.badge`). |
| `ContextMenu` | `controls.material.context_menu` | Wraps `content`, shows menus on mouse events. |

### 2.5 Media, text, graphics

| Class | Module | Purpose |
|---|---|---|
| `Image` | `controls.core.image` | Displays an image (local asset / URL / bytes). |
| `Icon` | `controls.core.icon` | Displays a built-in (`Icons` — 8825 members in 0.85.3, verified `len(list(ft.Icons)) == 8825`) or custom icon. |
| `Text` | `controls.core.text` | Styled text run (`TextStyle`, overflow, align — §6). |
| `TextSpan` | `controls.core.text_span` | Inline span inside `Text.spans` with own style/events. |
| `Markdown` | `controls.core.markdown` | Renders Markdown (`MarkdownStyleSheet/CodeTheme/ExtensionSet`). |
| `CircleAvatar` | `controls.material.circle_avatar` | User-representing circle (image/initials). |
| `ProgressBar` | `controls.material.progress_bar` | Horizontal determinate/indeterminate progress. |
| `ProgressRing` | `controls.material.progress_ring` | Circular determinate/indeterminate progress. |
| `CupertinoActivityIndicator` | `controls.cupertino.cupertino_activity_indicator` | iOS clockwise spinner. |
| `Shimmer` | `controls.core.shimmer` | Shimmer loading effect over `content` (`ShimmerDirection`, gradient). |
| `ShaderMask` | `controls.core.shader_mask` | Masks `content` with a `Gradient` shader (`blend_mode`). |
| `Canvas` (+`Arc/Circle/Line/Oval/Rect/Path/Points+PointMode/Shadow/Color/Fill/Text/Image/Shape`, `CanvasResizeEvent`) | `controls.core.canvas` | Imperative 2D drawing surface (real code under `core/canvas/`; `flet/canvas/__init__.py` is a re-export shim). |
| `CupertinoTimerPicker` | (inputs, listed once) | — |

### 2.6 Collections & data display

| Class | Module | Purpose |
|---|---|---|
| `DataTable` + `DataColumn` + `DataRow` + `DataCell` | `controls.material.datatable` | Material data table; column/row/cell configs (`sort_ascending`). |
| `ListTile` | `controls.material.list_tile` | Fixed-height row with leading/trailing icon + text (`ListTileStyle/TitleAlignment`). |
| `CupertinoListTile` | `controls.cupertino.cupertino_list_tile` | iOS list tile. |
| `Tabs` + `Tab` + `TabBar` + `TabBarView` | `controls.material.tabs` | Tab strip + pages (`selected_index`, `length`, `animation_duration`, `TabAlignment/IndicatorSize/Animation`). |

### 2.7 Navigation chrome

| Class | Module | Purpose |
|---|---|---|
| `AppBar` | `controls.material.app_bar` | Material top app bar. |
| `CupertinoAppBar` | `controls.cupertino.cupertino_app_bar` | iOS app bar. |
| `BottomAppBar` | `controls.material.bottom_app_bar` | Material bottom app bar. |
| `NavigationBar` + `NavigationBarDestination` | `controls.material.navigation_bar` | Material-3 bottom nav (`NavigationBarLabelBehavior`). |
| `CupertinoNavigationBar` | `controls.cupertino.cupertino_navigation_bar` | iOS bottom tab bar. |
| `NavigationRail` + `NavigationRailDestination` | `controls.material.navigation_rail` | Side rail nav (`NavigationRailLabelType`). |
| `NavigationDrawer` + `NavigationDrawerDestination` | `controls.material.navigation_drawer` | Slide-in drawer; `page.show_drawer()/close_drawer()`, `show_end_drawer()/close_end_drawer()`. |

### 2.8 Interaction / gestures / animation primitives

| Class | Module | Purpose |
|---|---|---|
| `GestureDetector` | `controls.core.gesture_detector` | Raw gesture callbacks (tap, drag, scale, hover). |
| `Dismissible` | `controls.core.dismissible` | Drag-to-dismiss wrapper (`dismiss_direction`, `background/secondary_background`, `DismissDirection`). |
| `Draggable` | `controls.core.draggable` | Drag source for `DragTarget`. |
| `DragTarget` | `controls.core.drag_target` | Drop target (`DragTargetEvent/LeaveEvent`, `DragWillAcceptEvent`). |
| `Hero` | `controls.core.hero` | Shared-element route transition (`tag`, `transition_on_user_gestures`). |
| `AnimatedSwitcher` | `controls.core.animated_switcher` | Animated swap between `content` values (`duration/reverse_duration/switch_in_curve/switch_out_curve`, `AnimatedSwitcherTransition`, default `FADE`). |
| `InteractiveViewer` | `controls.core.interactive_viewer` | Pan/zoom/rotate wrapper for `content`. |
| `KeyboardListener` | `controls.core.keyboard_listener` | Key-event callback wrapper: `(content, autofocus=False, include_semantics=True, on_key_down, on_key_up, on_key_repeat)`; `KeyDownEvent/KeyRepeatEvent/KeyUpEvent`. |
| `Screenshot` | `controls.core.screenshot` | Captures its subtree (`page.take_screenshot` is the page-level twin). |

### 2.9 Base / abstract (not instantiated directly)

`Control` (`controls.control`), `BasePage` (`controls.base_page`), `AdaptiveControl`
(adaptive Material↔Cupertino switch), `LayoutControl` + `ConstrainedControl`
(`controls.layout_control`), `ScrollableControl` (`controls.scrollable_control`),
`Component` (`components.component`, §4), `Service` (`controls.services.service`).

---

## 3. The Page API

Class: `Page` in `controls/page.py` (1429 lines), extends `BasePage` in
`controls/base_page.py` (858 lines). Constructor takes internal session/plumbing first
(`sess: InitVar['Session']`), then app-facing params.

### 3.1 Page identity / platform detection

```python
Page(..., route: str = '/', web: bool = False, pwa: bool = False, debug: bool = False,
     wasm: bool = False, test: bool = False, multi_view: bool = False, pyodide: bool = False,
     platform_brightness: Brightness | None = None,
     client_ip: str | None = None, client_user_agent: str | None = None,
     platform: PagePlatform | None = None, fonts: dict[str, str] | None = None, ...)
```

- `page.platform: PagePlatform | None` — enum `IOS, ANDROID, ANDROID_TV, MACOS, WINDOWS, LINUX`
  (verified `list(ft.PagePlatform.__members__)`). `ANDROID_TV` exists — relevant for a TV app.
- `page.web / page.pwa / page.wasm / page.pyodide / page.debug / page.test / page.multi_view: bool`.
- `page.platform_brightness: Brightness | None`; `on_platform_brightness_change(PlatformBrightnessChangeEvent)`.
- `page.client_ip`, `page.client_user_agent`, `page.fonts` (custom-font map), `page.title: str | None`,
  `page.width / page.height` (window size), `page.media: PageMediaData` + `on_media_change`,
  `on_resize(PageResizeEvent)`.
- `page.window: Window` (desktop: center/close/destroy/to_front/start_dragging/start_resizing).
- `page.session`, `page.query: QueryString` (`.get/.post`), `page.url`, `page.route: str`.
- `PageMediaData`, `PageResizeEvent` live in `controls/base_page.py`.

### 3.2 Theming

```python
Page(..., views: list[View] = factory, theme_mode: ThemeMode = ThemeMode.SYSTEM,
     theme: Theme | None = None, dark_theme: Theme | None = None,
     theme_animation_style: AnimationStyle | None = None,
     locale_configuration: LocaleConfiguration | None = None,
     show_semantics_debugger: bool | None = None, ...)
```

- `ThemeMode`: `SYSTEM, LIGHT, DARK`. `page.theme / page.dark_theme / page.theme_mode`.
- `Theme` is a 59-field dataclass (`len(dataclasses.fields(ft.Theme)) == 59`);
  `__init__(self, *args, **kwargs)` — pass style sub-objects (`ColorScheme`, `TextStyle`, …).
- `theme_animation_style: AnimationStyle | None` animates theme transitions.
- `page.platform_brightness` + `on_platform_brightness_change` let the app follow the OS.

### 3.3 Content: views stack, overlay, dialogs, drawers

- `page.views: list[View]` (constructor field, default empty) — the navigation stack.
  `Page` also exposes legacy proxies as **properties** on `BasePage` (verified):
  `appbar, bottom_appbar, navigation_bar, drawer, end_drawer, floating_action_button,
  floating_action_button_location, controls, scroll, auto_scroll, bgcolor, padding,
  spacing, decoration, foreground_decoration, vertical_alignment, horizontal_alignment`
  — these read/write the **active (last) view**.
- `page.overlay: list[BaseControl]` — property on `BasePage` (`base_page.py:577`).
  Floating layer for SnackBars, Banners, ad-hoc controls.
- Dialogs live in the internal `page._dialogs: Dialogs` (`Dialogs` + `Overlay` classes at
  `base_page.py:834/850`; `page._dialogs` confirmed as a `Page` field, no public `dialogs` prop —
  `hasattr(ft.Page, 'dialogs')` is `False`).

```python
Page.show_dialog(self, dialog: DialogControl) -> None   # base_page.py:398
Page.pop_dialog(self) -> DialogControl | None           # base_page.py:423
```

`show_dialog` raises `RuntimeError("Dialog is already opened")` if the instance is already
in the stack; sets `open=True`, parents to `_dialogs`, wraps `on_dismiss` so client-side
dismissal removes it from the stack. `pop_dialog` closes the topmost open dialog.
Component-tree code should prefer the `use_dialog(dialog | None)` hook (§4.6), which
does frozen-diff patching to preserve nested `TextField` focus.

- Drawers: `page.show_drawer() / close_drawer()`, `page.show_end_drawer() / close_end_drawer()`
  (defined on both `BasePage` and `View`).
- `View.confirm_pop(should_pop: bool)` + `View(can_pop=True, on_confirm_pop=...)` for
  back-button interception.

### 3.4 Routing: `go / push_route / navigate / pop_views_until`

```python
Page.go(self, route: str, skip_route_change_event: bool = False, **kwargs: Any) -> None       # page.py:854
Page.push_route(self, route: str, **kwargs: Any) -> None            # async, page.py:865
Page.navigate(self, route: str, **kwargs: Any) -> None              # page.py:946
Page.pop_views_until(self, route: str, result: Any = None) -> None  # async, page.py:960
```

Events: `on_route_change(RouteChangeEvent(route))`, `on_view_pop ViewPopEvent(route, view))`,
`on_views_pop_until ViewsPopUntilEvent(route, result, view))`.
`RouteChangeEvent(name, control, route, *, data)`,
`ViewPopEvent(name, control, route, view=None, *, data)`.
`View(route=..., fullscreen_dialog=False, ...)` — full signature verified in §3 intro dump;
`route` defaults to a generated value.

### 3.5 Background work: `run_task / run_thread`

```python
Page.run_task(self, handler: Callable[..., Awaitable[Ret]], *args, **kwargs) -> Future[Ret]
Page.run_thread(self, handler: Callable[..., Any], *args, **kwargs) -> None
```

`run_task` schedules a coroutine on the page loop and returns a `concurrent.futures.Future`;
`run_thread` runs sync work off the event loop. `page.loop`, `page.executor` are public props.

### 3.6 Keyboard, lifecycle, errors

```python
Page(..., on_keyboard_event: ... KeyboardEvent ... = None,
     on_connect / on_disconnect / on_close / on_logout / on_error ... = None,
     on_login: ... LoginEvent ... = None,
     on_route_change / on_view_pop / on_views_pop_until ... = None,
     on_app_lifecycle_state_change: ... AppLifecycleStateChangeEvent ... = None,
     on_locale_change: ... LocaleChangeEvent ... = None,
     on_multi_view_add / on_multi_view_remove ... = None, ...)
```

- `KeyboardEvent(name, control, key, shift, ctrl, alt, meta, *, data)`.
- `on_close` fires when the session closes; `on_error(Event[Page])` is the last-resort
  handler; `on_connect/on_disconnect` track session presence.
- `AppLifecycleStateChangeEvent.state: AppLifecycleState`;
  `LoginEvent(error, error_description)`; `on_logout(Event[Page])`.
- Auth: `Page.login(provider, fetch_user=True, fetch_groups=False, scope=None,
  saved_token=None, on_open_authorization_url=None, complete_page_html=None,
  redirect_to_page=False, authorization=AuthorizationService) -> AT`;
  `Page.logout() -> None`. Providers live in `flet.auth.providers`
  (`GoogleOAuthProvider`, `GitHubOAuthProvider`, `AzureOAuthProvider`, `Auth0OAuthProvider`).

### 3.7 URLs, screenshots, misc

```python
Page.launch_url(self, url: str | Url, *, web_popup_window_name=None, web_popup_window=False,
                web_popup_window_width=None, web_popup_window_height=None) -> None
Page.can_launch_url(self, url: str) -> bool
Page.close_in_app_web_view(self) -> None
Page.scroll_to(self, offset=None, delta=None, scroll_key=None, duration=None, curve=None) -> None
Page.take_screenshot(self, pixel_ratio=None, delay=None) -> bytes
Page.take_animation(self, name: str, frame_delays_ms: list[int], pixel_ratio=None) -> list[bytes]
Page.set_allowed_device_orientations(self, orientations: list[DeviceOrientation]) -> None
Page.get_upload_url(self, file_name: str, expires: int) -> str
Page.get_device_info(self) -> DeviceInfo | None
Page.get_control(self, id: int) -> BaseControl | None
Page.error(self, message: str) -> None
Page.add/insert/remove/remove_at/clean/update(*controls)   # legacy content mutation
```

`page.services: list[Service]` (property + setter, `base_page.py:817/825`).
Services can also be attached per-`View` (`View.services`).

---

## 4. `@ft.component` + hooks + `@ft.observable`

### 4.1 `@component` — what it actually does (`components/component_decorator.py`, 31 lines)

```python
def component(fn: Callable[P, R]) -> Callable[P, R]
```

Sets `fn.__is_component__ = True`, pops optional `key` from kwargs, and delegates to
`current_renderer().render_component(fn, args, kwargs, key=key)`, which builds a frozen
`Component` wrapper (`c._frozen = True`) parented to the current render-stack top and
snapshotting active contexts. Calling a component function **does not execute the body** —
it creates a `Component` node; the body runs during `before_update`/`update` inside a
`Renderer._Frame`. Calling a non-decorated function raises
`ValueError("... is not a component (missing @component?)")`.

Related: `ft.memo(fn)` marks the next rendered component memoized (skip re-render when
shallow-compared args/kwargs are unchanged — `Component.before_update`, `component.py:154`);
`ft.unwrap_component(c)` unwraps a component node.

### 4.2 `use_state` (`components/hooks/use_state.py`)

```python
def use_state(initial: StateT | Callable[[], StateT]) -> tuple[StateT, Callable[[StateT | Updater], None]]
```

- Lazy init: callable `initial` is invoked once (`initial() if callable(initial) else initial`).
- Setter accepts a value **or** an updater fn (`new_value_or_fn(hook.value) if callable(...)`).
- **Shallow-equality guard**: `if new_value != hook.value:` — equal values do NOT re-render.
  `hook.version += 1` then `hook.component._schedule_update()` (marks dirty + `session.schedule_update`).
- **Observable values auto-subscribe**: `update_subscription()` detaches the old
  `ObservableSubscription` and, if the new value `isinstance(h.value, Observable)`,
  attaches a fresh one — so `use_state(observable_obj)` re-renders on field mutation
  without calling the setter.

### 4.3 `use_context` / `create_context` (`components/hooks/use_context.py`)

```python
def create_context(default_value: T) -> ContextProvider[T]
def use_context(context: ContextProvider[T]) -> T
```

`create_context` mints a unique `object()` key; the provider is a callable
`provider(value, callback)` that pushes onto the current renderer's context stack and pops
in `finally`. `use_context` reserves a `ContextHook` slot (hook-order stability), walks
`component._parent_component()` chain for the nearest `_contexts[key]`, falls back to
`default_value`, and **auto-subscribes** (`_attach_observable_subscription`) when the
resolved value is an `Observable`. Also exported: `ContextProvider` protocol.

### 4.4 `use_effect` + `on_mounted/on_unmounted/on_updated` (`components/hooks/use_effect.py`)

```python
def use_effect(setup: Callable[[], Any | Awaitable[Any]],
               dependencies: Sequence[Any] | None = None,
               cleanup: Callable[[], Any | Awaitable[Any]] | None = None) -> None
def on_mounted(fn) -> None      # use_effect(fn, dependencies=[])
def on_unmounted(fn) -> None    # use_effect(lambda: None, dependencies=[], cleanup=fn)
def on_updated(fn, dependencies=None) -> None   # use_effect(fn, dependencies=dependencies)
```

Semantics as implemented (`Component._run_mount_effects/_run_render_effects/_run_unmount_effects`,
`component.py:296`):
- `dependencies=[]` → mount-only (skipped in `_run_render_effects` via `hook.deps != []` check).
- `dependencies=None` → runs after **every** render (`deps_changed` is True when `deps is None`).
- Otherwise re-runs when `deps != prev_deps` (plain `!=` list comparison), running the
  previous `cleanup` first (both scheduled via `session.schedule_effect`).
- `setup` may return a value but the **declared `cleanup` param** is what runs on unmount —
  note the docstring says setup "may optionally return a cleanup function", but the
  implementation schedules `hook.cleanup`, not a setup return value. Effects may be async
  (awaitable); `EffectHook.cancel()` cancels pending setup/cleanup tasks.
- Unmount clears all hooks (`hooks.clear()`) and detaches observable subscriptions.

### 4.5 `use_ref` / `use_memo` / `use_callback`

```python
def use_ref(initial_value: RefValueT | Callable[[], RefValueT] | None = None) -> MutableRef[RefValueT]
def use_memo(calculate_value: Callable[[], MemoValueT], dependencies: Sequence[Any] | None = None) -> MemoValueT
def use_callback(fn: Callable[P, R], dependencies: Sequence[Any] | None = None) -> Callable[P, R]
```

- `use_ref`: stable-identity `MutableRef` with a single `.current` slot (`__slots__`);
  mutating `.current` never schedules a render. Lazy init if callable.
- `use_memo`: `dependencies=None` → **recomputes every render**; otherwise recomputes when
  `not shallow_compare_args(prev_deps, dependencies)`. First render seeds via `_create`.
- `use_callback(fn, deps)` is exactly `use_memo(lambda: fn, dependencies)` — stabilizes
  function identity for memoized children / effect deps.

### 4.6 `use_dialog` (`components/hooks/use_dialog.py`)

```python
def use_dialog(dialog: DialogControl | None = None) -> None
```

Declarative dialog portal: pass a dialog to show (`open=True`, appended to
`page._dialogs.controls`), `None` to dismiss (`open=False` + direct `patch_control`),
with unmount cleanup closing any open dialog. Same-`type` re-renders take the
**frozen-diff** path (`session.patch_control(..., frozen=True)`, `_migrate_state`) so
Flutter widget identity — and nested `TextField` cursor/focus — survives re-renders.
Uses identity (`is`) comparison, not `==`, to find its entry among sibling hosts' dialogs.

### 4.7 `@observable` — change-detection mechanics (`components/observable.py`, 441 lines)

```python
def observable(cls) -> ...   # mixes Observable into any class (incl. dataclasses, either decorator order)
class Observable: subscribe(fn) -> disposer; notify(); _notify(field)
```

- `@observable` builds `type(cls.__name__, (Observable, cls), ns)` — MRO `(Observable, cls)`.
- `Observable.__setattr__`: **private (`_`-prefixed) assigns never notify**; public assigns
  auto-wrap `list→ObservableList` / `dict→ObservableDict`, then `if not value_equal(old, value):
  self._notify(name)`. `__delattr__` notifies if the attr existed. `notify()` broadcasts
  with `field=None`. `__version__` counter increments per notification.
- Listeners are a lazily-created `weakref.WeakSet` (`__listeners` property) — **a listener
  with no other reference is garbage-collected and stops firing**; `subscribe` returns a
  `dispose()` closure.
- `ObservableList`/`ObservableDict` hold only a `weakref` to the owner and call
  `owner._notify(field)` on every mutating op (`append/extend/insert/remove/clear/sort/
  reverse/pop/setitem/delitem`, `update/popitem/setdefault`, …), wrapping nested values.
- **Propagation to UI**: `ObservableSubscription(ComponentOwned)` subscribes
  `component._schedule_update` (`__on_change` → `_schedule_update` if `component` alive).
  Subscriptions attach at three points: `use_state` observable values, `use_context`
  observable values, and observable component `args/kwargs`
  (`_subscribe_observable_args`, re-attached every render after `_detach_...`).
  Updates are skipped for unmounted components (`_schedule_update` and `update()` both
  guard on `_state.mounted`), and zombie children are never resurrected.
- **Hook-order rule** (from `Component.use_hook`, `component.py:274`): hooks are positional
  slots advanced by `hook_cursor`; conditional hook calls corrupt the mapping. State
  migration (`_migrate_state`) refuses to transfer hooks when `self.fn is not other.fn`.
- `Component` bodies' outputs are marked `_frozen = True` item-wise before
  `session.patch_control(..., frozen=True)` — the frozen-diff path migrates `_i` ids and
  emits field deltas only.

---

## 5. Services (`flet/controls/services/`, 20 modules)

All services are `Service(BaseControl)` subclasses attached via `page.services` (or
`View.services`). Constructor pattern: `(self, <events...>, *, data=None, key=None, ref=None)`.

| Service | Init extras | Key methods (verified signatures where shown) |
|---|---|---|
| `Connectivity` | `on_change: ConnectivityChangeEvent | None` | `get_connectivity()`; event carries `connectivity: list[ConnectivityType]`. `ConnectivityType` ∈ 95-enum list (§8). |
| `Clipboard` | — | `set(value: str) -> None`; `get() -> str | None`; `get_files/get_image/set_files/set_image`. |
| `UrlLauncher` | — | `launch_url(url, *, mode=LaunchMode.PLATFORM_DEFAULT, web_view_configuration=None, browser_configuration=None, web_only_window_name=None)`; `can_launch_url(url) -> bool`; `open_window/supports_launch_mode/supports_close_for_launch_mode/close_in_app_web_view`. (Page-level `launch_url/can_launch_url/close_in_app_web_view` delegate here.) |
| `SharedPreferences` | — | `set(key, value: str|int|float|bool|list[str]) -> bool`; `get(key) -> str|int|float|bool|list[str]|None`; `contains_key(key) -> bool`; `remove(key) -> bool`; `clear() -> bool`; `get_keys(key_prefix: str) -> list[str]`. Async-flavored? No — all sync returning values directly (they round-trip through the session). |
| `FilePicker` | `on_upload: FilePickerUploadEvent | None` | `pick_files(dialog_title=None, initial_directory=None, file_type=FilePickerFileType.ANY, allowed_extensions=None, allow_multiple=False, with_data=False) -> list[FilePickerFile]`; `save_file(...) -> str | None`; `get_directory_path(...) -> str | None`; `upload(files: list[FilePickerUploadFile])` (+ `page.get_upload_url(file_name, expires)` for the URL). |
| `Share` | — | `share_text/share_uri/share_files`. |
| `HapticFeedback` | — | `light_impact/medium_impact/heavy_impact/selection_click/vibrate`. |
| `Wakelock` | — | `enable/disable/is_enabled`. (Note: `flet-video` has its own `wakelock: bool = True` on `Video`; this service is the generic one.) |
| `BrowserContextMenu` | — | `disable/enable` (web only). |
| `StoragePaths` | — | `get_temporary_directory/get_application_documents_directory/get_application_support_directory/get_application_cache_directory/get_downloads_directory/get_external_storage_directory/get_external_storage_directories/get_external_cache_directories/get_library_directory/get_console_log_filename`. |
| `Battery` | `on_state_change: BatteryStateChangeEvent | None` | `get_battery_level/get_battery_state/is_in_battery_save_mode`. |
| `ScreenBrightness` | `on_system_..._change/on_application_..._change: ScreenBrightnessChangeEvent | None` | `get/set_system_application_brightness, reset_application_screen_brightness, set_animate/set_auto_reset, is_animate/is_auto_reset, can_change_system_screen_brightness`. |
| `ShakeDetector` | `minimum_shake_count=1, shake_slop_time_ms=500, shake_count_reset_time_ms=3000, shake_threshold_gravity=2.7, on_shake` | Event only. |
| `SemanticsService` | — | `announce_message/announce_tooltip/get_accessibility_features`. |
| `Accelerometer` / `Gyroscope` / `Magnetometer` / `Barometer` / `UserAccelerometer` | `enabled=True, interval: Duration | None=None, cancel_on_error=True, on_reading, on_error: SensorErrorEvent | None` | Stream `*ReadingEvent` (accel in m/s², gyro in rad/s, magnetometer in µT, barometer in hPa). |

`Service` base (`controls/services/service.py`) adds nothing app-facing beyond `Control`.

---

## 6. Behaviors an app must know

### 6.1 Focus: which controls are focusable (29 classes, verified by `dataclasses.fields` scan for `on_focus`/`on_blur`)

`Button, Checkbox, Chip, CupertinoButton, CupertinoCheckbox, CupertinoFilledButton,
CupertinoRadio, CupertinoSlider, CupertinoSwitch, CupertinoTextField, CupertinoTintedButton,
Dropdown, DropdownM2, ElevatedButton, FilledButton, FilledIconButton, FilledTonalButton,
FilledTonalIconButton, IconButton, MenuItemButton, OutlinedButton, OutlinedIconButton,
Radio, SearchBar, Slider, SubmenuButton, Switch, TextButton, TextField`.

Notes:
- `TextField`/`SearchBar`/`CupertinoTextField` additionally have `autofocus: bool` (verified
  in fields) and `on_tap_outside`; `TextField.focus()` exists on `FormFieldControl`
  (verified; `Control`/`BaseControl` expose no focus members).
- `KeyboardListener(content, autofocus=False, include_semantics=True, on_key_down,
  on_key_up, on_key_repeat)` is the focusable wrapper for non-focusable subtrees.
- TV implication: focus visibility is driven by `ControlState.FOCUSED` (next).

### 6.2 `ControlState` maps (`controls/control_state.py`)

```python
class ControlState(Enum): HOVERED='hovered', FOCUSED='focused', PRESSED='pressed',
    DRAGGED='dragged', SELECTED='selected', SCROLLED_UNDER='scrolledUnder',
    DISABLED='disabled', ERROR='error', DEFAULT='default'
ControlStateValue = Union[T, dict[ControlState, T]]
```

Many style props accept either a single value (all states) or a `dict[ControlState, T]`
per-state map, with `DEFAULT` as fallback for undeclared states. Used by `ButtonStyle`,
`bar_bgcolor`, etc.

### 6.3 Frozen-control rules for component trees (`components/component.py`)

1. Component outputs are frozen: `object.__setattr__(item, "_frozen", True)` on every
   body return item (`update()` and `before_update()` both, `component.py:132/180`).
2. Diffs go through `session.patch_control(..., frozen=True)`, which migrates `_i`
   control ids (`_migrate_state`) and emits deltas — **mutating a control object after
   returning it from a component breaks the diff**; produce new values via state instead.
3. `@memo`-ized components skip re-render when shallow arg/kwarg comparison passes and
   re-parent the cached `_b` (`before_update`, `component.py:159`).
4. Hooks are positional: never call hooks conditionally; different `fn` ⇒ no state
   migration (`_migrate_state` returns early when `self.fn is not other.fn`).
5. Observable args/kwargs resubscribe every render; unmounted components never update.

### 6.4 Animation declarations

Every `LayoutControl` (hence `View` and most visuals) carries (verified on `View.__init__`):

```
animate_opacity, animate_size, animate_position, animate_align, animate_margin,
animate_rotation, animate_scale, animate_offset: bool | int | Animation | None
size_change_interval: int = 10
on_size_change(LayoutSizeChangeEvent), on_animation_end(Event)
```

`True` = default animation, `int` = duration ms, `Animation` = full spec
(`Animation(duration, curve, ...)`; `AnimationCurve` has 42 members incl. `EASE`,
`BOUNCE_*`, `EASE_IN_OUT_*`; `AnimationStyle` for theme transitions).
`Container`/`Text`/`Image` etc. inherit these from `LayoutControl`.

### 6.5 Adaptive controls

`AdaptiveControl` base + `Control.adaptive: bool | None`. Cupertino counterparts exist for
Button, Checkbox, Radio, Slider, Switch, TextField, dialogs, sheets, navigation —
set `adaptive=True` to render the Cupertino variant on iOS/macOS automatically.

---

## 7. What 0.85.3 has that we are NOT using but should know

Usage baseline: `grep -rhoP "ft\.\w+|page\.\w+" src/` — the app uses ~90 `ft.*` names and
`page.update/services/overlay/run_task/pop_dialog/theme_mode/show_dialog/platform/
on_keyboard_event/views/theme/fonts/dark_theme/render`.

Notable verified-but-unused surface (each verified present via `getattr(ft, ...)` +
signature dump; absence in app verified by grep):

- **`Router` + route hooks** — `ft.Router(*args, **kwargs)`,
  `ft.Route(path=None, index=False, component=None, children=None, loader=None,
  outlet=False, modal=False, recursive=False)`,
  `use_route_location() -> str`, `use_route_params() -> dict[str,str]`,
  `use_route_outlet() -> Control`, `use_view_path() -> str`,
  `use_route_loader_data()`, `is_route_active(path, exact=False) -> bool`,
  `LocationInfo(pathname, search='', hash='')`. The app hand-rolls screen switching;
  this is the framework nav stack with nested outlets, loaders, and modal routes.
- **`SharedPreferences`** — full typed get/set service (§5); the app currently only wires
  `Connectivity`, `Clipboard`, `UrlLauncher` (`page.services` grep hits = 12, all three).
  Persistent settings without a custom backend.
- **`FilePicker`** — pick/save/directory/upload dialogs + `page.get_upload_url`
  (relevant for downloads-screen export / local import).
- **`StoragePaths`** — 10 directory resolvers (temp, documents, support, cache,
  downloads, external, library, console-log) for the downloads feature.
- **`SearchBar` + `AutoComplete`** — purpose-built search UI (`bar_leading/trailing/
  hint_text/bgcolor`, suggestions dropdown); the app builds search from raw
  `TextField` + lists.
- **`GridView`** (`runs_count/max_extent/child_aspect_ratio/cache_extent`) — the poster
  grids are hand-built rows/columns; this is the virtualized 2D equivalent of `ListView`.
- **`Hero` (tag-based shared-element transitions)** + **`AnimatedSwitcher`
  (FADE default + curves/durations)** — route/poster transitions without custom code.
- **`Semantics` / `MergeSemantics` / `SemanticsService.announce_message`** —
  accessibility labeling + TalkBack announcements; `show_semantics_debugger` on Page.
- **`Wakelock` service, `HapticFeedback`, `ScreenBrightness`, `Battery`,
  `ShakeDetector`, 5 sensor streams** — device-integration surface (§5), all unused.
- **`Share.share_text/share_uri/share_files`** — system share sheet for anime links.
- **Auth stack** — `flet.auth` (`Google/GitHub/Azure/Auth0OAuthProvider`,
  `Authorization`, `OAuthToken`, `User`, `Group`) + `Page.login/logout/on_login` —
  verified present (`dir(flet.auth)`), unused by the app.
- **`flet.security` encrypt/decrypt (+AES-GCM variants)** — token/credential storage
  helpers; **not importable here** (missing `cryptography` package — verified ImportError).
- **Canvas 2D** (`Canvas` + 13 shapes) — custom drawing (e.g. progress overlays, waveforms).
- **`DataTable`, `PageView`, `ReorderableListView`, `Dismissible`, `InteractiveViewer`
  (pan/zoom/rotate), `SelectionArea`, `Banner`, `BottomSheet`, `ExpansionTile`,
  `DatePicker/TimePicker/DateRangePicker`, `MenuBar`, `ContextMenu`, `Tooltip/Badge`
  as standalone controls, `Cupertino*` family (26 classes), `Markdown`, `ShaderMask`,
  `Shimmer`** — all present, unused.
- **`use_memo` / `use_callback`** — verified exported, **zero** app hits; memoization
  currently relies on `@memo` + `use_state` only.
- **`page.take_screenshot / take_animation`, `Screenshot` control,
  `page.set_allowed_device_orientations`, `page.get_device_info`,
  `on_app_lifecycle_state_change`, `on_locale_change`, `locale_configuration`,
  `theme_animation_style`, `MultiView`, `FletApp` (embed), `AutofillGroup`** —
  present, unused.
- **95 exported enums** (full list verified): Geography-adjacent ones worth knowing —
  `ConnectivityType`, `DeviceOrientation`, `AppLifecycleState`, `LaunchMode`,
  `FilePickerFileType`, `ScrollMode`, `WebRenderer`, `RouteUrlStrategy`,
  `ShareResultStatus`, `BatteryState`, `WindowEventType`.

---

## 8. App improvement opportunities

Ranked by impact for this app (TV-first streaming client: D-pad focus navigation, video
playback via `flet-video`, hand-rolled screens, dialogs via `show_dialog`/`use_dialog`,
`page.services` = Connectivity/Clipboard/UrlLauncher only). Each item cites the exact
verified API and the app surface it improves. Absence-in-app verified by the §7 grep
survey (`grep -rhoP "ft\.\w+|page\.\w+" src/`).

### 8.1 (High) Replace hand-rolled search UI with `SearchBar` + `AutoComplete`

- **API**: `SearchBar(controls=[], value='', bar_leading=None, bar_trailing=[],
  bar_hint_text=None, bar_bgcolor: str|Colors|ControlState-map|None, ...,
  autofocus, on_tap/on_tap_outside_bar/on_submit/on_change/on_focus/on_blur)` —
  `flet/controls/material/search_bar.py`, signature dumped live; `autofocus` field
  verified in `dataclasses.fields`. `AutoComplete(value='', suggestions=[],
  suggestions_max_height=...)` — `flet/controls/material/auto_complete.py`.
- **Improves**: `src/screens/search_screen.py` (currently raw `TextField` + manual lists).
  Native search affordances (leading icon, trailing clear, hint, suggestion dropdown,
  tap-outside dismissal) remove custom focus/blur bookkeeping and give D-pad users a
  standard Material pattern with `ControlState.FOCUSED` styling for free.
- **Why now**: zero migration risk — both are `Control` subclasses droppable into the
  existing component tree.

### 8.2 (High) Virtualize poster grids with `GridView`

- **API**: `GridView(controls=[], horizontal=False, reverse=False, runs_count=1,
  max_extent=None, spacing=10, run_spacing=10, child_aspect_ratio=1.0, padding=None,
  clip_behavior=None, semantic_child_count=None, cache_extent=...)` —
  `flet/controls/core/grid_view.py`, signature dumped live.
- **Improves**: `src/screens/home_screen.py` poster rows/grids (hand-built
  `Row`/`Column` per usage survey: `ft.Row` ×31, `ft.Column` ×45). `GridView` +
  `cache_extent` gives lazy building and scroll performance on large catalogs where
  hand-built columns inflate the whole tree; `max_extent` adapts column count to TV
  vs. phone widths without `ResponsiveRow` math.
- **Evidence of need**: `ft.GridView` has zero app hits; `ft.ListView` has 1.

### 8.3 (High) Adopt `SharedPreferences` for settings persistence

- **API**: `SharedPreferences()` service with `set(key, value:
  str|int|float|bool|list[str]) -> bool`, `get(key)`, `contains_key`, `remove`,
  `clear`, `get_keys(key_prefix)` — `flet/controls/services/shared_preferences.py`,
  all six signatures dumped live (§5). Attach via `page.services` (same mechanism the
  app already uses for Connectivity/Clipboard/UrlLauncher).
- **Improves**: `src/screens/settings_screen.py` + any theme/source-preference state
  (app currently toggles `page.theme_mode` ×7 with no verified persistence layer).
  Synchronous typed API, no custom file/JSON plumbing, `get_keys(prefix)` namespaces
  per-provider settings.

### 8.4 (Medium-high) Stabilize renders with `use_memo` / `use_callback` (verified, unused)

- **API**: `use_memo(calculate_value, dependencies=None) -> MemoValueT` —
  `components/hooks/use_memo.py:24` (`None` = recompute every render, else shallow-compare);
  `use_callback(fn, dependencies=None)` = `use_memo(lambda: fn, ...)` —
  `components/hooks/use_callback.py:12`. Both exported top-level (function list, §8 intro).
- **Improves**: `src/components/*` + `src/screens/*` — 14 `@component` functions with 11
  `use_state` but **zero** `use_memo`/`use_callback` hits. Derived lists (filtered anime
  catalogs, episode lists) recompute per render; callbacks passed to `@memo` children
  change identity per render, defeating `Component.before_update`'s shallow-compare skip
  (`component.py:159`). Wrapping derived data in `use_memo` and callbacks in
  `use_callback` makes existing `@memo` boundaries effective.
- **Not speculative**: semantics read from source, not docs (§4.5).

### 8.5 (Medium) Use `Hero` + `AnimatedSwitcher` for poster→detail transitions

- **API**: `Hero(tag: str, content: Control, transition_on_user_gestures=False)` and
  `AnimatedSwitcher(content, duration, reverse_duration, switch_in_curve,
  switch_out_curve, transition=AnimatedSwitcherTransition.FADE)` —
  `flet/controls/core/hero.py`, `flet/controls/core/animated_switcher.py`; both full
  signatures dumped live (§2.8 + verification call).
- **Improves**: `home_screen.py → anime_detail_screen.py` navigation (note: app's
  `PromoHero` in `cross_promo.py` is a local component name, not `ft.Hero` — no
  `ft.Hero` hits). Shared-element poster zoom + fade content swaps elevate perceived
  quality on TV with ~5 lines each.

### 8.6 (Medium) Route with `Router`/`Route` instead of hand-rolled switching

- **API**: `Router(*args, **kwargs)`, `Route(path=None, index=False, component=None,
  children=None, loader=None, outlet=False, modal=False, recursive=False)`,
  `use_route_location() -> str`, `use_route_params() -> dict[str,str]`,
  `use_route_outlet() -> Control`, `use_view_path() -> str`,
  `use_route_loader_data()`, `is_route_active(path, exact=False) -> bool` —
  `flet/components/router.py`, all signatures dumped live. Complements (not replaces)
  `page.go/push_route/views` (§3.4).
- **Improves**: `src/app_shell.py` + `src/services/router.py` (app's own
  `ProviderRouter` is a *provider-failover* router — different concern, verified by read:
  `RouterError("all providers failed for {op}")`). Framework routes add deep-linkable
  paths (`/anime/:id/ep/:n`), nested outlets, per-route loaders, and modal routes
  (player-as-modal) with back-stack semantics the manual screen switcher lacks.

### 8.7 (Medium) TV-grade a11y/D-pad feedback: `Semantics` + focus-state styling

- **API**: `Semantics(tooltip=None, badge=None, content=...)`,
  `MergeSemantics`, `SemanticsService().announce_message/announce_tooltip`,
  `page.show_semantics_debugger`, `ControlState.FOCUSED` in `ControlStateValue` maps —
  `flet/controls/core/semantics.py`, `merge_semantics.py`,
  `flet/controls/services/semantics_service.py`, `flet/controls/control_state.py:7`
  (all verified; `ControlState` members listed in §6.2).
- **Improves**: `src/hooks/use_focus_scope.py` (KeyboardListener+autofocus Back-press
  workaround) + `src/components/focus_styles.py`. Pairing the existing focus scope with
  `FOCUSED`-state style maps (border/scale emphasis) and TalkBack announcements makes
  D-pad position legible; `show_semantics_debugger` validates the tree.
- **Note**: app already owns focus styling (29 focusable classes verified §6.1); this
  extends it to screen-reader users rather than replacing it.

### 8.8 (Lower-medium) Downloads screen: `FilePicker` + `StoragePaths`

- **API**: `FilePicker(on_upload=None).pick_files(...allow_multiple/with_data)`,
  `.save_file(...)`, `.get_directory_path(...)`, `.upload(...)` + `page.get_upload_url`
  — `flet/controls/services/file_picker.py` (signatures §5);
  `StoragePaths().get_downloads_directory/get_external_storage_directory/...`
  (10 resolvers) — `flet/controls/services/storage_paths.py`.
- **Improves**: `src/screens/downloads_screen.py` — export-to-file and directory choice
  via native dialogs instead of hardcoded paths; resolves per-platform save locations
  (Android external storage vs. desktop documents) without `page.platform` branching.

### 8.9 (Low, targeted) `Share` sheet, `HapticFeedback`, `Wakelock` service

- **API**: `Share().share_text/share_uri/share_files`; `HapticFeedback().light_impact/
  medium_impact/heavy_impact/selection_click/vibrate`; `Wakelock().enable/disable/
  is_enabled` — `flet/controls/services/share.py`, `haptic_feedback.py`, `wakelock.py`
  (method lists verified §5).
- **Improves**: anime-link sharing (share sheet vs. clipboard-only today — `Clipboard`
  is wired, `Share` is not); D-pad selection clicks; keeping the screen awake on
  non-video screens (the player already has `flet-video`'s own `wakelock=True`).

### Unverified / explicitly ruled out (no speculation)

- **`flet.security` encrypt/decrypt** — source read (`flet/security/__init__.py`) confirms
  the API, but `import flet.security` **fails in this venv** (`ModuleNotFoundError:
  No module named 'cryptography'` → re-raised as `ImportError`). Useful for stored
  credentials *only after* adding `cryptography` to deps — listed here, not ranked.
- **`Video`/`Audio`/`WebView` in `flet`** — verified absent (`in dir(ft)` → `False`);
  covered by sibling references `dep-flet-video.md` etc., not this report.
- **`SecureStorage`** — does not exist in this tree (grep over `flet/controls/services/`
  module list §1.2: no such module; `SharedPreferences` is the storage service).
- **`page.dialog_open`-style helpers, `rate`/`balance` on Video** — not `flet` API
  (app-local names / sibling-package concerns, per `page.*` usage survey).
- Nothing else significant found: the remaining unused surface (§7: sensors, auth
  providers, Canvas, DataTable, pickers, MenuBar, MultiView, take_screenshot, device
  orientations) has no credible high-impact mapping to a streaming client and is
  documented in §7 rather than promoted here.
