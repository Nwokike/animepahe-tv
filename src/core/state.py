import flet as ft
from dataclasses import dataclass


@dataclass
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


@dataclass
class Source:
    url: str
    resolution: int
    audio: str
    fansub: str


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
    search_query: str = ""
    search_results: list[Anime] = []
    latest_releases: list[LatestRelease] = []
    latest_page: int = 1
    latest_has_more: bool = True
    search_has_more: bool = True
    episodes: list[Episode] = []
    episodes_has_more: bool = True
    episodes_page: int = 1
    selected_source: Source | None = None
    current_anime_session: str = ""
    current_episode_session: str = ""
    player_error: str | None = None
    cache: object | None = None
    update_available: bool = False
    update_data: dict | None = None

    def __init__(self):
        self.search_results = []
        self.episodes = []
        self.update_data = None


state = AppState()
