# dep: flet-notifications — complete API reference

> **NOT INSTALLED — historical doc (2026-11-01):** flet-notifications is NOT a dependency of animepahe-tv — absent from pyproject.toml dependencies, absent from the pinned .venv (flet==0.85.3), and not imported anywhere in src/ or tests/. The content below was compiled 2026-10-15 against flet-notifications 0.1.3/0.1.4 and is NOT verified against this venv. Do not use it for new code unless the package is added to pyproject.toml and uv sync is run.

> **Version note (2026-10-15):** compiled against 0.1.3; installed is
> **flet-notifications 0.1.4**. Install source wins; full refresh in hybrid Phase 5.


> Installed package under study: `C:\Users\nwoki\ad-extensions\sources\animepahe-tv\.venv\Lib\site-packages\flet_notifications\`
> Version **0.1.3** (`__version__ = "0.1.3"` in `__init__.py:53`; `Name: flet-notifications / Version: 0.1.3` in `flet_notifications-0.1.3.dist-info/METADATA`).
> Dependency: only `flet` (`Requires-Dist: flet`, `Requires-Python: >=3.10`). Verified in this venv against Flet 0.85.3 (`uv run python -c "import flet"` reports `0.85.3`).
> Self-description: "A 1:1 wrapping of the official flutter_local_notifications Flutter plugin, in the same architecture as flet-ads" (`METADATA`, `__init__.py:1-6`).
> All facts below are read from the installed source. Source key: `LP` = `.../site-packages/flet_notifications/`.

---

## 1. Version + module layout

| File | Contents |
|---|---|
| `LP/__init__.py` | Re-exports + `__version__`, `__all__` (31 names) |
| `LP/local_notifications.py` | The only control: `LocalNotifications(ft.Service)` (`@ft.control("LocalNotifications")`, `local_notifications.py:42-43`) |
| `LP/base.py` | `NotificationEvent`, `ResponseType`, `NotificationError`, `NotificationErrorCode`, `check_result`, `to_bool` |
| `LP/actions.py` | `NotificationAction`, `NotificationActionInput` |
| `LP/styles.py` | `AndroidIcon`, `BigTextStyle`, `BigPictureStyle`, `InboxStyle`, `Person`, `Message`, `MessagingStyle`, `Style` union |
| `LP/channels.py` | `NotificationChannel` |
| `LP/options.py` | `NotificationOptions` + `AndroidOptions`, `DarwinOptions`, `LinuxOptions`, `WindowsOptions`, `WebOptions`; string-constant classes `Priority`, `Visibility`, `InterruptionLevel`, `LinuxUrgency`, `WindowsScenario` |
| `LP/types.py` | Enums `RepeatInterval`, `DateTimeComponents`, `AndroidScheduleMode`, `Importance`, `GroupAlertBehavior` |
| `LP/events.py` | `PendingNotification`, `ActiveNotification`, `LaunchDetails` |
| `LP/scheduling.py` | Pure serializers `build_schedule_args`, `build_periodic_args` |
| `LP/patcher.py` | `flet-notifications-patch` console script (entry point in `entry_points.txt`: `flet-notifications-patch = flet_notifications.patcher:main`) — post-build Android manifest/Gradle patcher |

`__all__` (`__init__.py:55-91`): `ActiveNotification, AndroidIcon, AndroidOptions, AndroidScheduleMode, BigPictureStyle, BigTextStyle, DarwinOptions, DateTimeComponents, GroupAlertBehavior, Importance, InboxStyle, InterruptionLevel, LaunchDetails, LinuxOptions, LinuxUrgency, LocalNotifications, Message, MessagingStyle, NotificationAction, NotificationActionInput, NotificationChannel, NotificationError, NotificationErrorCode, NotificationEvent, NotificationOptions, PendingNotification, Person, Priority, RepeatInterval, ResponseType, Style, Visibility, WebOptions, WindowsOptions, WindowsScenario`.

---

## 2. Control, classes, and every parameter

### 2.1 `LocalNotifications` — the only control

Base: `ft.Service`, headless. "instantiate it once and it registers itself with the page. No need to add it to the page's controls." (`local_notifications.py:44-48`). Constructor attributes (`local_notifications.py:74-107`):

| Attr | Type / default | Meaning |
|---|---|---|
| `default_icon` | `Optional[str] = None` | Android default small-icon drawable name (default: app launcher icon) |
| `request_alert_permission` | `bool = True` | iOS/macOS: request alert permission during init |
| `request_sound_permission` | `bool = True` | iOS/macOS: request sound permission during init |
| `request_badge_permission` | `bool = True` | iOS/macOS: request badge permission during init |
| `request_critical_permission` | `bool = False` | iOS/macOS critical-alert permission (needs Apple entitlement) |
| `app_name` | `Optional[str] = None` | Windows: application name shown on toasts |
| `app_user_model_id` | `Optional[str] = None` | Windows: AppUserModelID grouping toasts under the app |
| `windows_guid` | `Optional[str] = None` | Windows: GUID identifying the toast notifier |
| `on_tap` | `Optional[ft.EventHandler[NotificationEvent["LocalNotifications"]]] = None` | Body tap |
| `on_action` | same type, `= None` | Action-button press (`action_id` names the button) |
| `on_dismissed` | same type, `= None` | OS-reported dismissal/clear |

Handler typing warning (from `METADATA`): "Typed handlers must use `ft.EventHandler[NotificationEvent]`, **not** `ft.ControlEventHandler[NotificationEvent]` — `ControlEventHandler[X]` double-wraps `X` in `Event[...]`, so `e.payload` raises `AttributeError`." Source note on why annotations must stay real objects, not strings: `local_notifications.py:3-6`.

### 2.2 `NotificationEvent` / `ResponseType` (`base.py:11-33`)

```python
class ResponseType(str, Enum):
    TAP = "tap"
    ACTION = "action"
    DISMISSED = "dismissed"


@dataclass
class NotificationEvent(ft.Event[ft.EventControlType]):
    id: int = 0
    action_id: str = ""  # "" for plain tap; button id for actions
    payload: str = ""
    input: str = ""  # inline-reply text when the action had an input
    response_type: str = ResponseType.TAP.value
    # + inherited `data` field: Windows action inputs arrive there, keyed by
    # input id (Windows leaves `input` null). (base.py:31-32)
```

### 2.3 `show()` — immediate notification (`local_notifications.py:155-214`)

```python
async def show(
    self,
    id: int,                                        # re-show with same id updates in place (progress bars)
    title: Optional[str] = None,
    body: Optional[str] = None,
    payload: str = "",
    actions: Optional[list[NotificationAction]] = None,
    style: Optional[Style] = None,
    show_progress: bool = False,
    max_progress: int = 0,
    progress: int = 0,
    indeterminate: bool = False,
    group_key: Optional[str] = None,
    set_as_group_summary: bool = False,
    group_alert_behavior: GroupAlertBehavior = GroupAlertBehavior.ALL,
    channel_id: Optional[str] = None,               # Android channel to post on (created if missing)
    options: Optional[NotificationOptions] = None,
) -> None
```

Notes from docstring: `payload` is an "opaque string handed back on tap (e.g. a deep link)". `actions` serialized via `[a.to_dict() for a in actions]`; style/options/grouping via `_serialize_details` (`local_notifications.py:138-145`: style/options `.to_dict()`, `group_alert_behavior.value`).

### 2.4 Styles (`styles.py`) — every notification type supported

`Style = BigTextStyle | BigPictureStyle | InboxStyle | MessagingStyle` (`styles.py:159`). There is **no media-style** class: "Not wrapped (upstream niche): … `MediaStyle` …" (`METADATA` Limitations).

| Class | Fields (all kw_only) | Wire `type` |
|---|---|---|
| `BigTextStyle` (`styles.py:45-59`) | `big_text: str` (required), `content_title: Optional[str] = None`, `summary_text: Optional[str] = None` | `big_text` |
| `BigPictureStyle` (`styles.py:62-78`) | `image: AndroidIcon` (required), `large_icon: Optional[AndroidIcon] = None`, `content_title = None`, `summary_text = None` | `big_picture` |
| `InboxStyle` (`styles.py:81-99`) | `lines: list[str]` (required, `ValueError` if empty), `content_title = None`, `summary_text = None` | `inbox` |
| `MessagingStyle` (`styles.py:140-156`) | `person: Person` (required), `messages: list[Message] = []`, `conversation_title = None`, `group_conversation: bool = False` | `messaging` |
| `Person` (`styles.py:102-121`) | `name: str` (required), `key = None`, `bot: bool = False`, `important: bool = False`, `uri = None`, `icon: Optional[AndroidIcon] = None` | — |
| `Message` (`styles.py:124-137`) | `text: str`, `timestamp: datetime` (serialized `.isoformat()`), `person: Person` (all required) | — |
| `AndroidIcon` (`styles.py:10-42`) | exactly one of `drawable_resource / file_path / content_uri / flutter_asset / data_base64` must be set, else `ValueError("AndroidIcon requires exactly one source")` | dict of all five keys |

Progress (no separate class — flat kwargs on `show`/`schedule`/`periodically_show`/`start_foreground_service`): `show_progress: bool = False`, `max_progress: int = 0`, `progress: int = 0`, `indeterminate: bool = False`. Live progress = re-`show` with the same `id` (`local_notifications.py:176-177`).

### 2.5 Actions / categories (`actions.py`, `options.py`)

```python
@dataclass(kw_only=True)
class NotificationActionInput:  # actions.py:9-28
    label: str = ""  # placeholder / button title over the text field
    choices: list[str] = []  # quick-reply suggestions
    allow_free_form_input: bool = True
    allowed_mime_types: list[str] = []


@dataclass(kw_only=True)
class NotificationAction:  # actions.py:31-55
    id: str  # required; arrives as NotificationEvent.action_id
    title: str  # required; button label
    destructive: bool = False  # iOS/macOS render
    foreground: bool = True  # bring app to foreground on press
    cancel_notification: bool = True  # Android: dismiss the notification
    input: Optional[NotificationActionInput] = None  # inline reply; text -> NotificationEvent.input
```

"Categories": there is no `Category` class. The equivalents are `AndroidOptions.category` ("AndroidNotificationCategory value", `options.py:128`), `LinuxOptions.category` (free string, `options.py:239`), and channel groups on Android. Not wrapped: action `semanticAction`/`invisible`/`contextual` (`METADATA` Limitations).

### 2.6 Scheduling — `schedule()` / `periodically_show()` (`local_notifications.py:244-370`, `scheduling.py`)

```python
async def schedule(
    self,
    id: int,
    when: datetime | timedelta,          # datetime (naive = wall-clock in time_zone/device tz;
                                        #         aware = exact instant) or timedelta-from-now
    title: Optional[str] = None,
    body: Optional[str] = None,
    payload: str = "",
    actions: Optional[list[NotificationAction]] = None,
    match_components: Optional[DateTimeComponents] = None,  # calendar repeat, see below
    options: Optional[NotificationOptions] = None,
    schedule_mode: AndroidScheduleMode = AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE,
    time_zone: Optional[str] = None,    # IANA name e.g. "Africa/Lagos"; default device tz
    style: Optional[Style] = None,      # + show_progress/max_progress/progress/indeterminate
    group_key=None, set_as_group_summary=False,
    group_alert_behavior=GroupAlertBehavior.ALL,
    channel_id: Optional[str] = None,
) -> None

async def periodically_show(
    self,
    id: int,
    repeat_interval: RepeatInterval,     # EVERY_MINUTE/HOURLY/DAILY/WEEKLY
    ... (same title/body/payload/actions/style/progress/grouping/channel/options) ...,
    schedule_mode: AndroidScheduleMode = AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE,
    repeat_duration_seconds: Optional[int] = None,  # if set, must be >= 60 else ValueError
) -> None
```

Wire form (`scheduling.py:44-77`): `timedelta` → `{"delay_seconds": total_seconds(), "time_zone": tz}`; `datetime` → `{"iso": isoformat(), "utc_offset_seconds": offset|None, "time_zone": tz}`; `match_components.value`, `schedule_mode.value`. This `schedule()` is the **zoned-schedule equivalent** (timezone-aware, OS-owned alarm). "Survives app restarts (and, on Android, reboots — see the README for the required manifest entries)" (`local_notifications.py:266-269`). `periodically_show`: "first delivery happens one interval after the call" (`local_notifications.py:339-342`).

Enums (`types.py`):

```python
class RepeatInterval(str, Enum): EVERY_MINUTE="everyMinute"; HOURLY="hourly"; DAILY="daily"; WEEKLY="weekly"
class DateTimeComponents(str, Enum): TIME="time"  # daily at this time
    DAY_OF_WEEK_AND_TIME="dayOfWeekAndTime"; DAY_OF_MONTH_AND_TIME="dayOfMonthAndTime"; DATE_AND_TIME="dateAndTime"
class AndroidScheduleMode(str, Enum): ALARM_CLOCK="alarmClock"; EXACT="exact"
    EXACT_ALLOW_WHILE_IDLE="exactAllowWhileIdle"  # default; survives doze
    INEXACT="inexact"; INEXACT_ALLOW_WHILE_IDLE="inexactAllowWhileIdle"
class Importance(str, Enum): UNSPECIFIED="unspecified"; MIN="min"; NONE="none"; LOW="low"
    DEFAULT="defaultImportance"; HIGH="high"; MAX="max"
class GroupAlertBehavior(str, Enum): ALL="all"; SUMMARY="summary"; CHILDREN="children"
```

### 2.7 `NotificationOptions` escape hatch (`options.py:327-358`)

```python
@dataclass(kw_only=True)
class NotificationOptions:
    android: Optional[AndroidOptions] = None
    iOS: Optional[DarwinOptions] = None
    macOS: Optional[DarwinOptions] = None
    linux: Optional[LinuxOptions] = None
    windows: Optional[WindowsOptions] = None
    web: Optional[WebOptions] = None
```

`AndroidOptions` (`options.py:91-192`, all `Optional`, `None` = omit): `channel_id, channel_description, channel_bypass_dnd, audio_attributes_usage, icon` (drawable name), `importance` (Importance value), `priority` (Priority value), `play_sound, sound` (raw name/URI), `enable_vibration, vibration_pattern: list[int], channel_show_badge, auto_cancel, ongoing, silent, color` (#RRGGBB/#AARRGGBB, validated), `colorized, large_icon` (drawable/file path/content URI), `only_alert_once, show_when, when` (epoch ms), `uses_chronometer, chronometer_count_down, sub_text, number, visibility` (Visibility value), `timeout_after` (ms), `category, full_screen_intent, shortcut_id, additional_flags: list[str], ticker, tag, enable_lights, led_color` (hex, validated), `led_on_ms, led_off_ms`. Channel-subset fields (`channel_description, channel_bypass_dnd, audio_attributes_usage`) "apply when the channel is created — on Android 8+ sound/vibration are immutable after creation, so changing them needs a new channel id" (`options.py:95-98`).

`DarwinOptions` (`options.py:195-230`): `sound, badge_number` (0 clears), `subtitle, thread_identifier` (grouping), `interruption_level` (InterruptionLevel value), `critical_sound_volume` (0.0–1.0), `attachments: list[str]` (file paths), `present_alert, present_badge, present_sound, present_banner, present_list`.

`LinuxOptions` (`options.py:233-262`): `icon, sound, category, urgency` (LinuxUrgency value), `timeout_ms, resident, transient, suppress_sound, action_key_as_icon_name`.

`WindowsOptions` (`options.py:265-292`): `header, audio` (URI/ms-winsoundevent), `duration` ("long"|"short"), `scenario` (WindowsScenario value), `timestamp` (epoch ms), `subtitle, images: list[str]` (URIs), `bindings: dict[str,str]`.

`WebOptions` (`options.py:295-324`): `direction` ("auto"|"ltr"|"rtl"), `badge_url, icon_url, image_url, lang, require_interaction, is_silent, renotify, timestamp`.

String-constant classes (`options.py:16-78`): `Priority` MIN/LOW/DEFAULT/HIGH/MAX; `Visibility` PUBLIC/PRIVATE/SECRET; `InterruptionLevel` PASSIVE/ACTIVE/`timeSensitive`/`critical`; `LinuxUrgency` LOW/NORMAL/CRITICAL; `WindowsScenario` REMINDER/ALARM/`incomingCall`/URGENT.

### 2.8 Channels (`channels.py:11-58`, methods `local_notifications.py:433-457, 589-613`)

```python
@dataclass(kw_only=True)
class NotificationChannel:
    id: str  # required, ValueError if empty
    name: str  # required, ValueError if empty
    description: str = ""
    group_id: Optional[str] = None
    importance: Importance = Importance.DEFAULT
    bypass_dnd: bool = False
    play_sound: bool = True
    sound: Optional[str] = None  # raw resource name, e.g. "alert"
    enable_vibration: bool = True
    vibration_pattern: Optional[list[int]] = None
    show_badge: bool = True
    enable_lights: bool = False
    led_color: Optional[str] = None  # #RRGGBB, validated
```

"Sound and vibration are fixed at channel creation; to change them you create a new channel with a new id." (`channels.py:13-17`).

```python
async def create_notification_channel(self, channel: NotificationChannel) -> None
async def delete_notification_channel(self, channel_id: str) -> None
async def get_notification_channels(self) -> list[NotificationChannel]
async def create_notification_channel_group(self, group_id: str, name: str, description: str = "") -> None
async def delete_notification_channel_group(self, group_id: str) -> None
```

### 2.9 Queries, probes, foreground service (`local_notifications.py:372-613`)

```python
async def cancel(self, id: int, tag: Optional[str] = None) -> None   # tag = Android notification tag
async def cancel_all(self) -> None              # cancels all SHOWN notifications
async def cancel_pending(self) -> None          # cancels all SCHEDULED-but-undelivered
async def get_pending_notifications(self) -> list[PendingNotification]   # Android + iOS/macOS; empty elsewhere
async def get_active_notifications(self) -> list[ActiveNotification]     # Android 6+, iOS 10+, macOS 10.14+; empty elsewhere
async def get_notification_app_launch_details(self) -> LaunchDetails
async def initialize(self) -> None              # auto on creation; call only to force re-init
async def request_permissions(self) -> bool     # 300 s timeout; Android 13+ runtime dialog / Windows browser prompt
async def are_notifications_enabled(self) -> bool
async def open_app_notification_settings(self) -> None   # opens OS settings page for the app
async def can_schedule_exact_notifications(self) -> bool      # Android 14+
async def request_exact_alarm_permission(self) -> bool        # Android 14+, opens settings screen, 300 s timeout
async def request_full_screen_intent_permission(self) -> bool # Android 14+
async def has_notification_policy_access(self) -> bool        # Android DND-bypass state
async def request_notification_policy_access(self) -> bool    # Android DND-access settings screen
async def start_foreground_service(self, id: int, title=None, body=None, payload="",
    actions=None, style=None, show_progress=False, max_progress=0, progress=0,
    indeterminate=False, channel_id=None, options=None,
    start_type: Optional[str] = None,
    foreground_service_types: Optional[list[str]] = None) -> None   # id==0 -> ValueError
async def stop_foreground_service(self) -> None
```

Payload types (`events.py`):

```python
@dataclass
class PendingNotification: id: int; title: str = ""; body: str = ""; payload: str = ""
@dataclass
class ActiveNotification: id: int = 0; channel_id: str = ""; group_key: str = ""; tag: str = ""
    title: str = ""; body: str = ""; payload: str = ""; big_text: str = ""
@dataclass
class LaunchDetails: did_notification_launch_app: bool = False
    notification: Optional[NotificationEvent] = None
```

Errors (`base.py:35-88`): `NotificationError(code, message="")`, `str` = `"code: message"`. `NotificationErrorCode`: `unsupported_platform, init_failed, show_failed, schedule_failed, invalid_action, invalid_schedule, invalid_style, invalid_channel, invalid_service_id, invalid_option, channel_failed, foreground_service_failed, query_failed, permission_failed, unknown_method`. Dart failures arrive as `"error:<code>:<message>"` and `check_result()` raises them on every `show/schedule/cancel/channel/...` call. `to_bool()` coerces `"true"/"false"` results for permission/probe calls (raising first if the result is an error string).

---

## 3. Service/control lifecycle

1. **Construct once**: `notifications = LocalNotifications()`; optional `on_tap/on_action/on_dismissed` assignments; optional `default_icon`, iOS flags, Windows identity attrs. Headless service, self-registering (`local_notifications.py:44-48`).
2. **Mount caveat**: `ft.Service._invoke_method` raises `RuntimeError("<Class> Control must be added to the page first")` when `self.page` is unset (verified against installed `flet` 0.85.3 source). So no method may be called before the page session owns the service, even though it is never added to `page.controls`.
3. **(Optional) re-init**: `await notifications.initialize()` — automatic at creation (`local_notifications.py:147-153`).
4. **Permissions**: `await notifications.request_permissions()` → `bool` (300 s timeout, `local_notifications.py:234-242`). Gate every `show`/`schedule` on a `True` return.
5. **Fire/query**: `show / schedule / periodically_show / cancel(id, tag?) / cancel_all / cancel_pending / get_pending / get_active / get_launch_details`.
6. **Tap dispatch**: body tap → `on_tap` (`NotificationEvent` with `action_id=""`, `response_type="tap"`); button → `on_action` (`action_id` = button id, `response_type="action"`); dismissal → `on_dismissed` (`response_type="dismissed"`).
7. **Background/foreground** (`METADATA` + `local_notifications.py:551-571`): "Taps that arrive while the app wasn't running are replayed on the next start (Android background taps, iOS/macOS cold-start launches)." "Background taps are replayed automatically to `on_tap` / `on_action`; [`get_notification_app_launch_details`] is for apps that want the cold-start details themselves." It returns `LaunchDetails(did_notification_launch_app, notification: NotificationEvent|None)`.
8. **Foreground service** (Android long-running work + persistent notification): `start_foreground_service(...)` / `stop_foreground_service()`; needs manifest entries — opt in via `flet-notifications-patch --foreground-service-type <type>` (`patcher.py:197-238`; valid types: `camera, connectedDevice, dataSync, health, location, mediaPlayback, mediaProjection, microphone, phoneCall, remoteMessaging, shortService, specialUse, systemExempted`).

---

## 4. Android specifics

- **Channels**: required since Android 8.0. Create/update via `create_notification_channel(NotificationChannel(...))`; per-call `channel_id=` on `show`/`schedule` posts on that channel and creates it if missing (`local_notifications.py:187, 287`). Manage groups via `create/delete_notification_channel_group`. List via `get_notification_channels()`. Sound/vibration/DND-bypass are **immutable after creation** — change = new channel id (`channels.py:13-17`, `options.py:95-98`).
- **Importance**: `Importance` enum (`types.py:36-45`); default `Importance.DEFAULT` (`"defaultImportance"`). Also drives priority.
- **Small icon**: `LocalNotifications(default_icon="...")` drawable name, else the app launcher icon (`local_notifications.py:74-75`); per-notification override `AndroidOptions(icon="...")` (`options.py:105`). Large icon: `AndroidOptions.large_icon` (drawable / file path / content URI) or `BigPictureStyle.large_icon: AndroidIcon`. Episode thumbnails must therefore be pre-downloaded to a file and passed as `AndroidIcon(file_path=...)` — no remote-URL icon field exists.
- **Payload / on-tap**: `payload: str = ""` on every fire call; delivered back verbatim as `NotificationEvent.payload` on `on_tap`/`on_action` and in `PendingNotification`/`ActiveNotification`. Recommended pattern (per docstring, `local_notifications.py:180`): put a deep link / route in `payload` (e.g. `"animepahe://anime/<id>"`), then route to the detail screen in the `on_tap` handler. Cold start: same event is replayed automatically; `get_notification_app_launch_details()` exposes it explicitly.
- **Android 13 permission flow**: `POST_NOTIFICATIONS` is a runtime permission. `request_permissions()` shows the runtime dialog and returns the grant as `bool`. The patcher injects `POST_NOTIFICATIONS, VIBRATE, RECEIVE_BOOT_COMPLETED, SCHEDULE_EXACT_ALARM` into the manifest (`patcher.py:39-44`); the app's `pyproject.toml` must additionally declare `[tool.flet.android.permission] RECEIVE_BOOT_COMPLETED = true` and `SCHEDULE_EXACT_ALARM = true` (`METADATA` Configuration).
- **Scheduling infra**: patcher injects three `<application>` receivers (`patcher.py:32-37`, `exported=false`): `ActionBroadcastReceiver`, `ScheduledNotificationReceiver`, `ScheduledNotificationBootReceiver` (boot one with `BOOT_COMPLETED / MY_PACKAGE_REPLACED / QUICKBOOT_POWERON` filters, `patcher.py:46-51`), plus Gradle `isCoreLibraryDesugaringEnabled = true`, `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")`, `multiDexEnabled = true` (`patcher.py:113-174`). Without running `flet-notifications-patch` after `flet build apk`, scheduled notifications (and reboot restore) do not work — `[tool.flet.android.*]` cannot declare receivers (`patcher.py:3-8`).
- **Exact alarms (Android 14+)**: `can_schedule_exact_notifications()` / `request_exact_alarm_permission()` (opens the exact-alarm settings screen). Default `schedule_mode=EXACT_ALLOW_WHILE_IDLE` survives doze.
- **Full-screen intent / DND (Android 14+)**: `request_full_screen_intent_permission()`; `has/request_notification_policy_access()`.
- **Limits** (`METADATA`): aggressive OEM skins may drop alarms after force-stop; Samsung caps ~500 alarms.

---

## 5. What degrades or no-ops on desktop/unsupported platforms

Platform matrix (`METADATA` Platform Support):

| Platform | Show | Schedule | Actions & callbacks | Channels | Progress |
|---|---|---|---|---|---|
| iOS 13+ | yes | yes | yes | — | — |
| Android 7.0+ (API 24) | yes | yes | yes | yes | yes |
| macOS 10.15+ | yes | yes | yes | — | — |
| Windows 10+ | yes | **one-shot only** | yes | — | yes |
| Linux (D-Bus server) | yes | **—** | yes | — | — |
| Web | yes | **—** | **Chrome/Edge only** | — | — |

Explicit degradation rules (all from `METADATA` Limitations + method docstrings):

- `schedule()` on Linux/Web has **no OS scheduler**; `periodically_show()` is "not supported on Linux/Web (no OS scheduler) or Windows (one-shot only)" (`local_notifications.py:341-342`).
- `get_pending_notifications()` — "Supported on Android and iOS/macOS; empty on other platforms" (`local_notifications.py:376-380`).
- `get_active_notifications()` — "Supported on Android 6+, iOS 10+ and macOS 10.14+; empty elsewhere" (`local_notifications.py:528-532`).
- Windows `cancel`/queries need an MSIX identity (`METADATA`).
- Web permissions are gesture-gated (`METADATA`); iOS interruption beyond `passive` needs Xcode capabilities; `critical` needs an Apple entitlement (constructor flag `request_critical_permission=False` by default).
- **Failure mode is raising, not silent no-op**: every mutating/query call wraps its result in `check_result()`, which raises `NotificationError(code, ...)` on `"error:<code>:<message>"` — including `code="unsupported_platform"` for unsupported platforms. Calling any method before page mount raises `RuntimeError` from `ft.Service._invoke_method`.
- **Missing-extension case** (plain `flet run` without the Dart half): "`flet run` launches the prebuilt client without the extension's Dart half — notifications need a built app (an artifact above, or `flet build <platform>`)" (`METADATA`). Calls then fail (`unknown_method` / transport error surfaced as `NotificationError`), so the services layer must treat "extension missing" as *notifications unavailable* and skip (log + continue), never crash.
- Not wrapped at all (do not design around): HTML-format style flags, `MediaStyle`, action `semanticAction`/`invisible`/`contextual`, CarPlay, message data MIME/URI, Linux custom hints (`METADATA` Limitations).

---

## 6. What we'd use for "Episode 1103 of One Piece is out"

- **Fire immediately from our own background task — do NOT `schedule()` per episode.** `schedule()` is an OS-owned one-shot/calendar alarm for a *known* future instant; we don't know episode air times, and schedules need exact-alarm permission + patcher receivers + reboot-restore handling. Our checker (periodic poll of followed anime) already determines "episode N is out" at runtime, so it should call `show()` at that moment. `periodically_show()` is for fixed-cadence reminders ("check every hour"), not per-episode content, and is unsupported on desktop.
- **Content call** (basic + big text, or big picture when a thumbnail file is cached locally):
  ```python
  if await notifications.request_permissions():   # once per session, gate everything
      await notifications.show(
          id=<stable per-anime int>,              # same id updates/replaces the previous ep notice
          title="One Piece",
          body="Episode 1103 is out",
          payload=f"animepahe://anime/{anime_id}",  # on_tap routes to the detail screen
          style=BigTextStyle(                     # long synopsis / multi-episode text
              big_text="Episode 1103: ...",
              summary_text="animepahe",
          ),
          # or, when episode thumbnail is downloaded to a file:
          # style=BigPictureStyle(
          #     image=AndroidIcon(file_path=thumb_path),
          #     summary_text="animepahe",
          # ),
          channel_id="new_episodes",              # created if missing; pre-create with importance HIGH
      )
  ```
  `id` strategy: one stable id per anime (update semantics) keeps the tray to one row per series; unique id per episode keeps history but risks tray spam — prefer per-anime id + `InboxStyle(lines=[...])` if batching several new episodes.
- **Channel setup (once, Android 8+)**: `await notifications.create_notification_channel(NotificationChannel(id="new_episodes", name="New episodes", description="...", importance=Importance.HIGH))`. Sound/vibration are fixed at creation — pick them now; changing them later requires a new channel id.
- **Tap → open detail**: `notifications.on_tap = handler` (must be `ft.EventHandler[NotificationEvent]`, not `ControlEventHandler`); read `e.payload`, parse the anime id, navigate. Cold-start taps replay automatically; use `get_notification_app_launch_details()` only if explicit launch attribution is needed.
- **Quiet-hours / batching**: group with `group_key="new_episodes"`, or hold shows until the user returns and fire one `InboxStyle` summary.
- **Adapter degradation contract**: wrap the service so that `NotificationError` (any code, incl. `unsupported_platform`/`unknown_method`) and pre-mount `RuntimeError` → "notifications unavailable", skip silently with a log. `are_notifications_enabled()` distinguishes user-denied (offer `open_app_notification_settings()`) from platform-unsupported. Never call `schedule()` on Linux/Web/Windows-expecting-recurrence; never assume `get_pending/active` are non-empty off Android/iOS/macOS.

---

## 7. App improvement opportunities

Every item below cites a verified source (file + signature from §§1–6). Items that could not be verified against installed 0.1.3 are separated at the end. Ordered by expected impact on the planned new-episode feature (notify on new episodes of followed anime).

1. **Tap-payload deep link → cold-start-safe navigation to the anime detail.**
   `show(..., payload: str = "", ...)` (`local_notifications.py:155-172`; docstring: "Opaque string handed back on tap (e.g. a deep link)", `local_notifications.py:180`) round-trips verbatim as `NotificationEvent.payload: str` (`base.py:20-33`) on `on_tap: Optional[ft.EventHandler[NotificationEvent["LocalNotifications"]]]` (`local_notifications.py:98-99`). Taps arriving while the app wasn't running "are replayed on the next start" (`METADATA`; `get_notification_app_launch_details() -> LaunchDetails`, `local_notifications.py:551-571`, is only for apps that want the cold-start details themselves).
   Improves the new-episode feature end to end: fire with `payload=f"anime:{anime_session}"` and parse it in the `on_tap` handler into the existing `app_shell.py:69-75` entry point (`_open_anime(session)` → `set_active_view("anime")` + `controller.load_anime(session)`). This is the single highest-impact item — without it a notification is a dead end; with it every "Episode N is out" row deep-links to `AnimeDetailScreen()`. Must-use-`ft.EventHandler` typing caveat applies (`METADATA`, `local_notifications.py:3-6`).

2. **Fire from our own poll task with immediate `show()` — do not `schedule()` per episode.**
   `schedule(id, when: datetime | timedelta, ..., match_components: Optional[DateTimeComponents] = None, schedule_mode: AndroidScheduleMode = ..., time_zone: Optional[str] = None, ...)` (`local_notifications.py:244-265`) is an OS-owned alarm for a *known* instant (wire form `{"iso"/"delay_seconds", "time_zone"}` in `scheduling.py:44-77`); `periodically_show(id, repeat_interval: RepeatInterval, ..., repeat_duration_seconds: Optional[int] = None)` (`local_notifications.py:318-338`, first delivery one interval after the call) is fixed-cadence recurrence, "not supported on Linux/Web (no OS scheduler) or Windows (one-shot only)" (`local_notifications.py:341-342`). Scheduling additionally needs the patcher receivers + `RECEIVE_BOOT_COMPLETED`/`SCHEDULE_EXACT_ALARM` (§4), neither of which this app has yet (`pyproject.toml:28-31` lists only `INTERNET`/`ACCESS_NETWORK_STATE`/`WAKE_LOCK`).
   Improves correctness and scope: episode air times are unknown until a poll of followed anime (favorites rows keyed by `anime_session` in `store.py:315-365`, fetched via `router.py:205-221` `latest_releases`/`episodes`) detects them, so the checker — spawned via the house pattern `spawn(coro, name)` (`core/tasks.py:13-27`, precedent throughout `app_shell.py`/`immersive_player.py`) — should call `show()` at detection time. Saves the exact-alarm permission, the patcher step, and reboot-restore handling entirely.

3. **Per-anime stable `id` + `InboxStyle` batching to keep one tray row per series.**
   `show(id: int, ...)` — "showing again with the same id updates it" (`local_notifications.py:176-177`); `cancel(id: int, tag: Optional[str] = None)` / `cancel_all()` (`local_notifications.py:216-232`); `InboxStyle(lines: list[str], content_title=None, summary_text=None)` requiring ≥1 line (`styles.py:81-99`); grouping knobs `group_key / set_as_group_summary / group_alert_behavior: GroupAlertBehavior = ALL` on every fire call (`local_notifications.py:167-170`).
   Improves tray hygiene for follow-lists: derive one stable int per `anime_session` (favorites dict keys, `store.py:315-324`) so "Episode 1103" replaces "Episode 1102" instead of stacking; when several followed series release at once, re-`show` the same id with `InboxStyle(lines=["One Piece — Ep 1103", ...])` or `group_key="new_episodes"`. Avoids notification spam, the fastest route to the user disabling the channel.

4. **Channel design up front: one `new_episodes` channel at `Importance.HIGH`.**
   `NotificationChannel(id, name, description="", group_id=None, importance: Importance = DEFAULT, bypass_dnd=False, play_sound=True, sound=None, enable_vibration=True, vibration_pattern=None, show_badge=True, enable_lights=False, led_color=None)` (`channels.py:11-58`, `id`/`name` required); `create_notification_channel(channel)` (`local_notifications.py:435-439`); `Importance` enum (`types.py:36-45`, default `"defaultImportance"`); sound/vibration "fixed at channel creation … create a new channel with a new id" to change (`channels.py:13-17`, `options.py:95-98`). Per-call `channel_id=` "created if missing" (`local_notifications.py:187`).
   Improves user control and deliverability on Android 8+: pre-create `NotificationChannel(id="new_episodes", name="New episodes", importance=Importance.HIGH)` once at startup so episode alerts pop with sound/heads-up rather than inheriting whatever default channel the first `show()` auto-creates. Keep a separate channel id for any future download-progress noise so users can silence one without losing the other.

5. **Permission flow: gate on `request_permissions()`, fall back to in-app snack + settings link.**
   `request_permissions() -> bool` (300 s timeout; Android 13+ runtime dialog, `local_notifications.py:234-242`); `are_notifications_enabled() -> bool` (`local_notifications.py:520-522`); `open_app_notification_settings() -> None` (`local_notifications.py:524-526`).
   Improves first-run and denied-state UX: call `request_permissions()` once per session before any `show()`; on `False`, keep the existing in-app path (`show_snack(page, message, ...)` in `core/notify.py:25-52`, used by `main.py`/`search_screen.py`/`settings_screen.py`) and offer a settings row (`_setting_row` + `ft.Switch` pattern in `screens/settings_screen.py:45-84, 235`) that calls `open_app_notification_settings()`. Distinguishes user-denied (recoverable via settings) from platform-unsupported (`NotificationError(unsupported_platform)`, §5) — never prompt-loop on the latter.

6. **`BigPictureStyle` with locally cached episode thumbnails.**
   `BigPictureStyle(image: AndroidIcon, large_icon: Optional[AndroidIcon] = None, content_title=None, summary_text=None)` (`styles.py:62-78`); `AndroidIcon` requires exactly one of `drawable_resource / file_path / content_uri / flutter_asset / data_base64` (`styles.py:10-42`); there is no remote-URL image field (§4). `BigTextStyle(big_text, content_title=None, summary_text=None)` (`styles.py:45-59`) is the text fallback.
   Improves glanceability of the alert ("Episode 1103 of One Piece is out" + key visual): download the episode/poster image to a file (note `store.py:324-341` deliberately strips `data:`-URI posters before persisting — cache the bytes on disk, pass the path), then `BigPictureStyle(image=AndroidIcon(file_path=thumb_path))`. Fall back to `BigTextStyle` with the synopsis when no image is cached. Expectation to set: thumbnails require a small file-cache addition; the package will not fetch URLs itself.

7. **Action buttons "Play now" / "Mark watched" via `on_action`.**
   `NotificationAction(id: str, title: str, destructive=False, foreground=True, cancel_notification=True, input: Optional[NotificationActionInput] = None)` (`actions.py:31-55`); passed as `actions: Optional[list[NotificationAction]]` on `show()` (`local_notifications.py:161`); press arrives on `on_action` with `action_id == id`, `response_type="action"` (`local_notifications.py:101-102`, `base.py:11-19`).
   Improves conversion from alert to playback: `NotificationAction(id="play", title="Play now")` routes like item 1 then starts resolution (precedent: `spawn(controller._app_controller.play_adjacent(...))` in `app_shell.py:89-97`); `NotificationAction(id="watched", title="Mark watched", cancel_notification=True)` records via `JsonStore.record_watch` (`store.py:167-190`) and `cancel(id)`s the notice. Ranked last because it is enhancement, not core: action/callback support is Chrome/Edge-only on Web and absent from some targets in the §5 matrix, so both actions must degrade to tap-equivalence off Android/iOS.

Unverified / explicitly absent — checked and NOT in installed 0.1.3, so no improvement can be built on them without a different package or version:

- Remote-URL episode artwork passed directly: `AndroidIcon` has no URL source (`styles.py:10-42` full five-source enumeration is the evidence); `WebOptions.image_url` (`options.py:295-324`) is Web-only. Thumbnail-by-URL without a local download is not possible on Android.
- Media-style playback controls (play/pause on the notification): "Not wrapped … `MediaStyle`" (`METADATA` Limitations). Use `NotificationAction` buttons (item 7) instead.
- HTML-format body styling, action `semanticAction`/`invisible`/`contextual`, CarPlay, message data MIME/URI, Linux custom hints: all listed as not wrapped (`METADATA` Limitations).
- iOS attachment thumbnails end to end: `DarwinOptions.attachments: list[str]` exists (`options.py:195-230`) but delivery was not verified on device — "iOS IPAs need Apple signing and are built owner-side" (`METADATA`).
- Reboot-persistent schedules in our APK: the three receivers + desugaring flags exist only in `patcher.py:32-51, 113-174` and this app's `pyproject.toml:28-31` does not yet declare `RECEIVE_BOOT_COMPLETED`/`SCHEDULE_EXACT_ALARM`, so restore-after-reboot is unwired, not broken.
- OEM/force-stop alarm survival and the ~500-alarm Samsung cap (`METADATA` Limitations): documented upstream constraints, not measured on target hardware.
- Whether "followed anime" maps to the existing `favorites` section (`store.py:315-365`, toggled in `anime_detail_screen.py:343-356`) or needs a separate follow table: an app-design decision outside this package's surface — the items above assume favorites keyed by `anime_session` but do not assert it.
