"""AnimePahe provider — the app's proven source as provider #1.

A thin adapter over the EXISTING AnimePaheScraper (untouched): same
methods, same shapes, same cache. AnimePahe is complete (catalog,
episodes, files via kwik) and stays the safety net. Its session strings
stay BARE (no namespace) so the user's existing store, history and
continue-watching keys keep working unchanged.
"""

from core.state import Anime, Episode, LatestRelease, Source
from services.animepahe import AnimePaheScraper


class AnimePaheProvider:
    name = "animepahe"
    capabilities = {
        "files": True,
        "episodes": True,
        "episode_stills": True,
        "kwik_resolve": True,  # its source URLs need the Kwik unpack
    }

    def __init__(self, scraper: AnimePaheScraper | None = None):
        self.scraper = scraper or AnimePaheScraper()

    # The controller's retry-Cloudflare flow and the KwikResolver use the
    # scraper's ddos solver directly.
    @property
    def ddos(self):
        return self.scraper.ddos

    async def probe(self) -> bool:
        """AnimePahe's api is Cloudflare-walled; a plain GET answering
        200 means the wall is open (clearance cached) — 403 means the
        gate will need solving. Either way the provider is REACHABLE;
        only transport death marks it down."""
        try:
            await self.scraper._fetch_api({"m": "airing", "page": "1"})
            return True
        except Exception as ex:
            status = getattr(getattr(ex, "response", None), "status_code", None)
            if status in (401, 403, 503):
                return True  # walled, not dead
            return False

    async def latest_releases(self, page: int) -> tuple[list[LatestRelease], bool]:
        return await self.scraper.latest_releases(page)

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:
        return await self.scraper.search(query, page)

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        return await self.scraper.episodes(session, page)

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        return await self.scraper.sources(anime_session, episode_session)

    def clear_cache(self) -> None:
        self.scraper.clear_cache()

    async def close(self) -> None:
        await self.scraper.close()
