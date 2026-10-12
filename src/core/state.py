import flet as ft
from dataclasses import dataclass, field


@dataclass(unsafe_hash=True)
class Anime:
    id: int
    title: str
    type: str
    episodes: int
    status: str
    season: str
    year: int
    score: float
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


@dataclass(unsafe_hash=True)
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


@dataclass(unsafe_hash=True)
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


@dataclass(unsafe_hash=True)
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
    search_query: str = ""
    search_results: list[Anime] = []
    latest_releases: list[LatestRelease] = []
    latest_page: int = 1
    latest_has_more: bool = True
    search_has_more: bool = True
    episodes: list[Episode] = []
    episodes_has_more: bool = True
    episodes_page: int = 1
    current_anime_session: str = ""
    current_episode_session: str = ""
    player_error: str | None = None
    cache: object | None = None
    cf_blocked: bool = False
    is_online: bool = True
    connectivity_version: int = 0
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
    search_history: list[dict] = []
    search_error: str | None = None
    search_page: int = 1
    continue_watching: dict = {}
    selected_anime: dict | None = None
    selected_source: object | None = None
    current_source_name: str = ""
    # Dev-test panel (Settings): rows from "Test all sources".
    source_test_results: list = []
    sources_test_version: int = 0
    # Airing schedule (anikato): 7 day tabs + the selected day's entries.
    schedule_tabs: list = []
    schedule_entries: list = []
    schedule_time: str = ""
    schedule_version: int = 0

    # Player (in-app playback)
    player_open: bool = False
    player_spec: dict | None = None
    player_error: str | None = None
    quality_dialog_open: bool = False
    quality_choices: list | None = None
    pending_playback: dict | None = None

    # Offline downloads (durable rows + throttled live progress)
    downloads: dict = {}
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
        self.search_results = []
        self.episodes = []
        self.update_data = None
        self.starting_downloads = set()
        self.follows = {}


state = AppState()
