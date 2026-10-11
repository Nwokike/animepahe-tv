"""AnimePahe provider — the app's proven source as provider #1.

An adapter over the EXISTING AnimePaheScraper: same shapes, same cache,
plus the m=links stream API the scraper never called (per-rendition
audio/kwik/filesize — attested by six independent clients in the
backend map). AnimePahe is complete (catalog, episodes, files via kwik)
and stays the safety net. Its session strings stay BARE (no namespace)
so the user's existing store, history and continue-watching keys keep
working unchanged.

Source-specific limits (documented in backend-animepahe.md): English
hardsub — NO subtitle tracks exist; no schedule API; no watchlist API
(our store IS that feature).
"""

import logging

from core.state import Anime, Episode, LatestRelease, Source
from services.animepahe import AnimePaheScraper

logger = logging.getLogger("animepahe.provider.animepahe")


class AnimePaheProvider:
    name = "animepahe"
    capabilities = {
        "files": True,
        "episodes": True,
        "episode_stills": True,
        "kwik_resolve": True,  # its source URLs need the Kwik unpack
        "subtitles": False,  # hardsubbed — three converging evidence lines
    }

    def __init__(self, scraper: AnimePaheScraper | None = None):
        self.scraper = scraper or AnimePaheScraper()
        # episode_session -> numeric anime_id (from m=release rows) — the
        # key m=links needs. Filled whenever episodes() runs.
        self._anime_ids: dict[str, int] = {}

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
        episodes, has_more = await self.scraper.episodes(session, page)
        for ep in episodes:
            if ep.anime_id:
                self._anime_ids[ep.session] = ep.anime_id
        return episodes, has_more

    async def _sources_via_links(self, anime_session: str, episode_session: str) -> list[Source]:
        """m=links: one JSON call -> per-rendition {audio, kwik,
        kwik_pahewin, filesize?, hd}. Needs the numeric anime_id from
        m=release (carried on the episodes we already loaded)."""
        anime_id = self._anime_ids.get(episode_session)
        if not anime_id:
            return []
        resp = await self.scraper._fetch_api(
            {
                "m": "links",
                "id": str(anime_id),
                "session": episode_session,
                "p": "kwik",
            }
        )
        if resp is None:
            return []
        data = resp.json().get("data") or {}
        # Two attested shapes: dict keyed by rendition ("360"/"720"/"1080")
        # or a flat list. Handle both — quality comes from the key when
        # the source gives one, otherwise it stays 0 (never invented).
        renditions = data.values() if isinstance(data, dict) else data
        results: list[Source] = []
        for key, entry in (
            data.items() if isinstance(data, dict) else enumerate(data)
        ):
            if not isinstance(entry, dict) or not entry.get("kwik"):
                continue
            try:
                resolution = int(key) if isinstance(key, str) and key.isdigit() else 0
            except (TypeError, ValueError):
                resolution = 0
            results.append(
                Source(
                    url=str(entry["kwik"]),
                    resolution=resolution,
                    audio=str(entry.get("audio") or "jpn"),
                    fansub="AnimePahe",
                    size=f"{entry['filesize']}MB" if entry.get("filesize") else "",
                )
            )
        logger.info("m=links returned %d renditions", len(results))
        return results

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        # m=links first (one cheap JSON call, richer payload); the
        # play-page scrape stays as the fallback — never removed.
        try:
            results = await self._sources_via_links(anime_session, episode_session)
        except Exception as ex:
            logger.warning("m=links failed (%s) — play-page fallback", ex)
            results = []
        if results:
            return results
        return await self.scraper.sources(anime_session, episode_session)

    async def episodes_for_title(self, title: str) -> list[Episode]:
        results, _ = await self.scraper.search(title, 1)
        for anime in results:
            if anime.title.strip().lower() == title.strip().lower():
                episodes, _ = await self.scraper.episodes(anime.session, 1)
                return episodes
        return []

    async def sources_for_title(self, title: str, episode: int) -> list[Source]:
        results, _ = await self.scraper.search(title, 1)
        for anime in results:
            if anime.title.strip().lower() == title.strip().lower():
                for ep in (await self.scraper.episodes(anime.session, 1))[0]:
                    if ep.episode == episode:
                        return await self.sources(anime.session, ep.session)
        return []

    def clear_cache(self) -> None:
        self.scraper.clear_cache()

    async def close(self) -> None:
        await self.scraper.close()
