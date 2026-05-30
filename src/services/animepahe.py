import re
import httpx
from bs4 import BeautifulSoup
from core.state import Anime, Episode, Source, LatestRelease
from services.ddos_solver import DDoSSolver

BASE = "https://animepahe.com"


class AnimePaheScraper:
    def __init__(self):
        self.ddos = DDoSSolver()

    def latest_releases(self, page: int = 1) -> tuple[list[LatestRelease], bool]:
        resp = self.ddos.get(
            f"{BASE}/api",
            params={"m": "airing", "page": page},
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return [], False
        try:
            data = resp.json()
        except (ValueError, httpx.DecodingError):
            return [], False

        results = []
        for item in data.get("data", []):
            results.append(
                LatestRelease(
                    anime_id=item.get("anime_id", 0),
                    anime_title=item.get("anime_title", ""),
                    anime_session=item.get("anime_session", ""),
                    episode=item.get("episode", 0),
                    snapshot=item.get("snapshot", ""),
                    session=item.get("session", ""),
                    created_at=item.get("created_at", ""),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        return results, has_more

    def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        results, has_more = self._search_api(query, page)
        if results:
            return results, has_more
        return self._search_html(query, page)

    def _search_api(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        resp = self.ddos.get(
            f"{BASE}/api",
            params={"m": "search", "q": query, "page": page},
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return [], False
        try:
            data = resp.json()
        except (ValueError, httpx.DecodingError):
            return [], False
        results = []
        for item in data.get("data", []):
            results.append(
                Anime(
                    id=item.get("id", 0),
                    title=item.get("title", ""),
                    type=item.get("type", ""),
                    episodes=item.get("episodes", 0),
                    status=item.get("status", ""),
                    season=item.get("season", ""),
                    year=item.get("year", 0),
                    score=item.get("score", 0.0),
                    poster=item.get("poster", ""),
                    session=item.get("session", ""),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        return results, has_more

    def _search_html(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        resp = self.ddos.get(f"{BASE}/", params={"search": query, "page": page})
        if resp.status_code != 200:
            return [], False
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for card in soup.select(".anime-card"):
            results.append(
                Anime(
                    id=0,
                    title=card.get("data-title", ""),
                    type=card.get("data-type", ""),
                    episodes=int(card.get("data-episodes", 0)),
                    status=card.get("data-status", ""),
                    season=card.get("data-season", ""),
                    year=int(card.get("data-year", 0)),
                    score=float(card.get("data-score", 0)),
                    poster=card.get("data-poster", ""),
                    session=card.get("data-session", ""),
                )
            )
        return results, bool(soup.select(".pagination .next"))

    def episodes(self, anime_session: str, page: int = 1) -> tuple[list[Episode], bool]:
        results, has_more = self._episodes_api(anime_session, page)
        if results:
            return results, has_more
        return self._episodes_html(anime_session, page)

    def _episodes_api(
        self, anime_session: str, page: int = 1
    ) -> tuple[list[Episode], bool]:
        resp = self.ddos.get(
            f"{BASE}/api",
            params={
                "m": "release",
                "id": anime_session,
                "page": page,
                "sort": "episode_asc",
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return [], False
        try:
            data = resp.json()
        except (ValueError, httpx.DecodingError):
            return [], False
        results = []
        for item in data.get("data", []):
            results.append(
                Episode(
                    id=item.get("id", 0),
                    anime_id=item.get("anime_id", 0),
                    episode=item.get("episode", 0),
                    title=item.get("title", ""),
                    snapshot=item.get("snapshot", ""),
                    disc=item.get("disc", ""),
                    audio=item.get("audio", ""),
                    duration=item.get("duration", ""),
                    session=item.get("session", ""),
                    filler=bool(item.get("filler", 0)),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        return results, has_more

    def _episodes_html(
        self, anime_session: str, page: int = 1
    ) -> tuple[list[Episode], bool]:
        return [], False

    def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        results = self._sources_data_src(anime_session, episode_session)
        if results:
            return results
        return self._sources_regex(anime_session, episode_session)

    def _sources_data_src(
        self, anime_session: str, episode_session: str
    ) -> list[Source]:
        resp = self.ddos.get(f"{BASE}/play/{anime_session}/{episode_session}")
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        sources = []
        for el in soup.select("[data-src]"):
            src = el.get("data-src", "").strip()
            if "kwik" in src.lower():
                sources.append(
                    Source(
                        url=src,
                        resolution=int(
                            el.get("data-resolution", 0) or el.get("data-res", 0) or 0
                        ),
                        audio=el.get("data-audio", "") or el.get("data-lang", "jpn"),
                        fansub=el.get("data-fansub", ""),
                    )
                )
        return sources

    def _sources_regex(self, anime_session: str, episode_session: str) -> list[Source]:
        resp = self.ddos.get(f"{BASE}/play/{anime_session}/{episode_session}")
        if resp.status_code != 200:
            return []
        urls = re.findall(r"https?://kwik\.[a-z]+/(?:e|f|d)/[A-Za-z0-9_-]+", resp.text)
        seen = set()
        sources = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                sources.append(Source(url=url, resolution=0, audio="jpn", fansub=""))
        return sources

    def close(self):
        self.ddos.close()
