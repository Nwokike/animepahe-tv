from dataclasses import dataclass, field
from typing import ClassVar

import flet as ft


@dataclass
class Anime:
    id: int
    title: str
    type: str
    episodes: int
    status: str
    season: str
    year: int
    # A source that publishes NO numeric rating carries None (Kayoanime's
    # "rating" is the age certification, verified live 2026-10-19) — the
    # card then renders no star at all, never a fabricated "★ 0.0".
    score: float | None
    poster: str
    session: str
    synopsis: str = ""
    genres: list = field(default_factory=list)
    mal_id: int = 0
    anilist_id: int = 0
    # Carried by the providers that parse them (animepahe's details page
    # is the one that serves all three); defaults keep the others valid.
    studios: list = field(default_factory=list)
    aired: str = ""
    # The page's own cover, when the map gives a verified selector for it.
    backdrop: str = ""


@dataclass
class Episode:
    id: int
    anime_id: int
    episode: int
    title: str
    snapshot: str
    disc: str
    audio: str
    duration: str
    session: str
    filler: bool
    # Per-episode audio availability (anikato's data-sub/data-dub flags).
    # Defaults keep providers that don't publish them valid.
    subs: bool = False
    dub: bool = False
    # Air time as unix seconds when the source publishes one (anikato's
    # data-timestamp). 0 = unknown, never invented.
    aired_ts: int = 0


@dataclass
class Source:
    url: str
    resolution: int
    audio: str
    fansub: str
    # Per-source request headers the player/proxy must send (e.g. the
    # Referer a CDN requires). Empty = this source needs nothing special.
    headers: dict = field(default_factory=dict)
    # Subtitle tracks exactly as the source serves them:
    # [{label, url, default?}] — never reordered or filtered.
    subtitles: list = field(default_factory=list)
    # Skip windows as the source declares them: {"intro": {...},
    # "outro": {...}} — shapes vary per source (arrays or objects).
    skip: dict = field(default_factory=dict)
    # File size when the source serves it (e.g. "176MB") — display only.
    size: str = ""
    # The provider's own download route when it serves one (animepahe's
    # pahe.win menu) — the site's offering, not a second guess at it.
    download_url: str = ""
    # BD (Blu-ray disc) badge, documented on that same menu.
    bd: bool = False


@dataclass
class LatestRelease:
    anime_id: int
    anime_title: str
    anime_session: str
    episode: int
    snapshot: str
    session: str
    created_at: str


@ft.observable
class AppState:
    is_loading: bool = False
    # Startup gate: the shell shows its splash until the backend is
    # resolved and the first home fetch has been attempted (the fixed order
    # runs once at startup; switching while open is the owner's act).
    startup_ready: bool = False
    startup_stage: str = ""
    search_query: str = ""
    search_results: ClassVar[list[Anime]] = []
    latest_releases: ClassVar[list[LatestRelease]] = []
    latest_page: int = 1
    latest_has_more: bool = True
    search_has_more: bool = True
    episodes: ClassVar[list[Episode]] = []
    episodes_has_more: bool = True
    episodes_page: int = 1
    current_anime_session: str = ""
    current_episode_session: str = ""
    cache: object | None = None
    cf_blocked: bool = False
    is_online: bool = True
    connectivity_version: int = 0
    # Bumped when the window changes size. The header's badge and the
    # detail screen's compact layout read the WIDTH at render time, and
    # without this they kept the size of the last render: rotate a
    # phone and the app stayed in the old layout until something else
    # re-rendered it (audit, 2026-10-19).
    viewport_version: int = 0
    # The observable theme mode: the header toggle and the Settings
    # picker both drive it, and every screen reads it instead of asking
    # the page (which is not observable).
    theme_mode: object = None
    update_available: bool = False
    update_data: dict | None = None
    # Version counters: bumped by the controller when a collection is
    # replaced, so components re-render explicitly instead of relying on
    # deep-diffing large lists.
    latest_version: int = 0
    search_version: int = 0
    episodes_version: int = 0
    continue_version: int = 0

    # Search + continue watching (durable store-backed). Recent rows are
    # {title, session, ts} — the ANIME that was opened, not the typed text.
    search_history: ClassVar[list[dict]] = []
    search_error: str | None = None
    search_page: int = 1
    continue_watching: ClassVar[dict] = {}
    selected_anime: dict | None = None
    selected_source: object | None = None
    current_source_name: str = ""
    # Which provider served each list — the artwork defaults are learned per
    # provider+surface, so every list carries the name it painted from.
    latest_source: str = ""
    search_source: str = ""
    # Dev-test panel (Settings): rows from "Test all sources".
    source_test_results: ClassVar[list] = []
    sources_test_version: int = 0
    # Airing schedule (anikato): 7 day tabs + the selected day's entries.
    schedule_tabs: ClassVar[list] = []
    schedule_entries: ClassVar[list] = []
    schedule_time: str = ""
    schedule_version: int = 0

    # Discover: provider-generated filters + the filtered grid. The filter
    # vocabulary comes from the provider (never hardcoded in the UI), so
    # discover_source names which provider served it.
    discover_filters: ClassVar[list] = []
    discover_selections: ClassVar[dict] = {}
    discover_results: ClassVar[list] = []
    discover_has_more: bool = False
    discover_source: str = ""
    discover_page: int = 1
    discover_version: int = 0
    # The Discover tab hosts both surfaces: the filtered grid, and search.
    # This flag says which one is showing.
    discover_showing_search: bool = False
    # The header badge's provider picker (shell-owned dialog).
    backend_picker_open: bool = False

    # Settings -> Storage: live cache-tier size and a bump-to-re-render
    # counter (computed on the fly — it is a directory walk).
    cache_bytes: int = 0
    storage_version: int = 0

    # Player (in-app playback)
    player_open: bool = False
    player_spec: dict | None = None
    player_error: str | None = None
    quality_dialog_open: bool = False
    quality_choices: list | None = None
    pending_playback: dict | None = None

    # Offline downloads (durable rows + throttled live progress)
    downloads: ClassVar[dict] = {}
    download_progress: dict | None = None
    downloads_version: int = 0
    # Download quality choice (the same list the play dialog shows — a
    # silent sources[0] would download the wrong rendition).
    download_choice_open: bool = False
    download_choices: list | None = None
    pending_download: dict | None = None

    # Favorites (whole anime, keyed by anime_session)
    follows: dict = None
    follows_version: int = 0

    # Long-running action feedback (KTV's rule: anything that takes more
    # than a beat shows a spinner, or the app looks dead).
    is_resolving: bool = False
    resolve_stage: str = ""
    cf_retrying: bool = False
    quality_resolving: bool = False
    starting_downloads: set = None
    # Bumped whenever any busy flag flips, so components re-render.
    busy_version: int = 0

    def __init__(self):
        # All mutable collections are instantiated per-instance in __init__
        # so they are not shared at the class level and Observable.__setattr__
        # wraps them in ObservableList and ObservableDict automatically.
        self.search_results = []
        self.latest_releases = []
        self.episodes = []
        self.search_history = []
        self.continue_watching = {}
        self.source_test_results = []
        self.schedule_tabs = []
        self.schedule_entries = []
        self.discover_filters = []
        self.discover_selections = {}
        self.discover_results = []
        self.downloads = {}
        self.follows = {}
        self.starting_downloads = set()
        self.update_data = None


state = AppState()
