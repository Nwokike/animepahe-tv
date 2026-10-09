import logging
import re
import time
import base64
import asyncio
from bs4 import BeautifulSoup
from core.state import Anime, Episode, Source, LatestRelease
from services.ddos_solver import DDoSSolver

logger = logging.getLogger(__name__)

BASE = "https://animepahe.com"


class AnimePaheScraper:
    def __init__(self):
        self.ddos = DDoSSolver()
        self._mem_cache: dict = {}
        self._mem_ttl: dict = {}

    async def _get_image_base64(self, url: str) -> str:
        if not url:
            return ""
        if "animepahe" in url:
            try:
                resp = await self.ddos.get(url, headers={"Accept": "image/*"})
                if resp.status_code == 200:
                    encoded = base64.b64encode(resp.content).decode()
                    ct = resp.headers.get("content-type", "image/jpeg")
                    return f"data:{ct};base64,{encoded}"
                else:
                    logger.warning(
                        "Failed to proxy image %s: status=%d", url, resp.status_code
                    )
            except Exception as ex:
                logger.error("Error proxying image %s: %s", url, ex)
        return url

    def _get_mem(self, key: str, ttl: int = 300):
        if key in self._mem_cache and key in self._mem_ttl:
            if time.time() < self._mem_ttl[key]:
                logger.debug("Cache HIT for %s", key)
                return self._mem_cache[key]
            logger.debug("Cache EXPIRED for %s", key)
            del self._mem_cache[key]
            del self._mem_ttl[key]
        logger.debug("Cache MISS for %s", key)
        return None

    def _set_mem(self, key: str, value, ttl: int = 300):
        self._mem_cache[key] = value
        self._mem_ttl[key] = time.time() + ttl

    async def _fetch_api(self, params: dict):
        """Fetch from animepahe API. Returns response on success, None on failure."""
        logger.info("FETCH params=%s", params)
        try:
            resp = await self.ddos.get(
                f"{BASE}/api",
                params=params,
                headers={"Accept": "application/json"},
            )
            logger.info("FETCH status=%s len=%s", resp.status_code, len(resp.text))

            # The /api endpoint always returns JSON. A 200 with HTML content
            # (or an empty body) means we actually received a Cloudflare
            # interstitial that slipped past the status-based detection — e.g.
            # a challenge page served with HTTP 200. Returning None here lets
            # the caller fall through to its empty-handling path, which is the
            # right behaviour (the self-healing path in ddos_solver will have
            # already re-solved on the next request).
            body_start = resp.text.lstrip()[:1]
            is_html_or_empty = body_start not in ("{", "[")
            if is_html_or_empty:
                logger.warning(
                    "FETCH got non-JSON response (likely Cloudflare interstitial), "
                    "treating as no data. status=%s body start: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

            if resp.status_code == 200:
                logger.debug("FETCH SUCCESS — first 200 chars: %s", resp.text[:200])
                return resp
            logger.warning(
                "FETCH returned %s, response start: %s",
                resp.status_code,
                resp.text[:200],
            )
        except Exception as ex:
            logger.error("FETCH FAILED: %s", ex)
        return None

    async def latest_releases(self, page: int = 1) -> tuple[list[LatestRelease], bool]:
        cache_key = f"latest_{page}"
        cached = self._get_mem(cache_key, ttl=300)
        if cached:
            logger.info("LATEST returning %d items from cache", len(cached[0]))
            return cached

        logger.info("LATEST fetching page %d", page)
        resp = await self._fetch_api({"m": "airing", "page": str(page)})
        if resp is None:
            logger.error("LATEST no response from any strategy")
            return [], False

        try:
            data = resp.json()
            logger.info("LATEST got JSON keys=%s", list(data.keys()))
        except ValueError as ex:
            logger.error(
                "LATEST JSON decode failed: %s — body start: %s", ex, resp.text[:300]
            )
            return [], False

        # Resolve snapshots to base64 in parallel to bypass client-side Cloudflare blocks
        tasks = [
            self._get_image_base64(item.get("snapshot", ""))
            for item in data.get("data", [])
        ]
        snapshots = await asyncio.gather(*tasks)

        results = []
        for i, item in enumerate(data.get("data", [])):
            results.append(
                LatestRelease(
                    anime_id=item.get("anime_id", 0),
                    anime_title=item.get("anime_title", ""),
                    anime_session=item.get("anime_session", ""),
                    episode=item.get("episode", 0),
                    snapshot=snapshots[i],
                    session=item.get("session", ""),
                    created_at=item.get("created_at", ""),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        logger.info("LATEST parsed %d items, has_more=%s", len(results), has_more)
        result = (results, has_more)
        self._set_mem(cache_key, result, ttl=300)
        return result

    async def search(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        cache_key = f"search_{query}_{page}"
        cached = self._get_mem(cache_key, ttl=600)
        if cached:
            logger.info("SEARCH returning %d items from cache", len(cached[0]))
            return cached

        logger.info("SEARCH query=%s page=%d", query, page)
        results, has_more = await self._search_api(query, page)
        if results:
            logger.info("SEARCH API returned %d results", len(results))
            result = (results, has_more)
            self._set_mem(cache_key, result, ttl=600)
            return result
        logger.warning("SEARCH API returned 0 results, trying HTML fallback")
        results, has_more = await self._search_html(query, page)
        logger.info("SEARCH HTML fallback returned %d results", len(results))
        result = (results, has_more)
        self._set_mem(cache_key, result, ttl=600)
        return result

    async def _search_api(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        logger.info("SEARCH_API q=%s page=%d", query, page)
        resp = await self._fetch_api({"m": "search", "q": query, "page": str(page)})
        if resp is None:
            return [], False
        try:
            data = resp.json()
            logger.info(
                "SEARCH_API got keys=%s data_len=%s",
                list(data.keys()),
                len(data.get("data", [])),
            )
        except ValueError as ex:
            logger.error("SEARCH_API JSON decode failed: %s", ex)
            return [], False
        # Resolve posters to base64 in parallel to bypass client-side Cloudflare blocks
        tasks = [
            self._get_image_base64(item.get("poster", ""))
            for item in data.get("data", [])
        ]
        posters = await asyncio.gather(*tasks)

        results = []
        for i, item in enumerate(data.get("data", [])):
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
                    poster=posters[i],
                    session=item.get("session", ""),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        logger.info("SEARCH_API parsed %d results, has_more=%s", len(results), has_more)
        return results, has_more

    async def _search_html(self, query: str, page: int = 1) -> tuple[list[Anime], bool]:
        logger.info("SEARCH_HTML q=%s page=%d", query, page)
        try:
            resp = await self.ddos.get(
                f"{BASE}/", params={"search": query, "page": page}
            )
            logger.info(
                "SEARCH_HTML status=%s len=%s", resp.status_code, len(resp.text)
            )
            if resp.status_code != 200:
                logger.warning("SEARCH_HTML not 200, body start: %s", resp.text[:200])
                return [], False
        except Exception as ex:
            logger.error("SEARCH_HTML fetch failed: %s", ex)
            return [], False
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(".anime-card")

        # Resolve posters to base64 in parallel to bypass client-side Cloudflare blocks
        tasks = [self._get_image_base64(card.get("data-poster", "")) for card in cards]
        posters = await asyncio.gather(*tasks)

        results = []
        for i, card in enumerate(cards):
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
                    poster=posters[i],
                    session=card.get("data-session", ""),
                )
            )
        has_more = bool(soup.select(".pagination .next"))
        logger.info(
            "SEARCH_HTML parsed %d results, has_more=%s", len(results), has_more
        )
        return results, has_more

    async def episodes(
        self, anime_session: str, page: int = 1
    ) -> tuple[list[Episode], bool]:
        cache_key = f"episodes_{anime_session}_{page}"
        cached = self._get_mem(cache_key, ttl=600)
        if cached:
            logger.info("EPISODES returning %d items from cache", len(cached[0]))
            return cached

        logger.info("EPISODES session=%s page=%d", anime_session, page)
        results, has_more = await self._episodes_api(anime_session, page)
        if results:
            logger.info("EPISODES API returned %d results", len(results))
            result = (results, has_more)
            self._set_mem(cache_key, result, ttl=600)
            return result
        logger.warning("EPISODES API returned 0, trying HTML fallback")
        results, has_more = await self._episodes_html(anime_session, page)
        logger.info("EPISODES HTML fallback returned %d results", len(results))
        result = (results, has_more)
        self._set_mem(cache_key, result, ttl=600)
        return result

    async def _episodes_api(
        self, anime_session: str, page: int = 1
    ) -> tuple[list[Episode], bool]:
        logger.info("EPISODES_API session=%s page=%d", anime_session, page)
        resp = await self._fetch_api(
            {
                "m": "release",
                "id": anime_session,
                "page": str(page),
                "sort": "episode_asc",
            }
        )
        if resp is None:
            return [], False
        try:
            data = resp.json()
            logger.info(
                "EPISODES_API got keys=%s data_len=%s",
                list(data.keys()),
                len(data.get("data", [])),
            )
        except ValueError as ex:
            logger.error("EPISODES_API JSON decode failed: %s", ex)
            return [], False
        # Resolve snapshots to base64 in parallel to bypass client-side Cloudflare blocks
        tasks = [
            self._get_image_base64(item.get("snapshot", ""))
            for item in data.get("data", [])
        ]
        snapshots = await asyncio.gather(*tasks)

        results = []
        for i, item in enumerate(data.get("data", [])):
            results.append(
                Episode(
                    id=item.get("id", 0),
                    anime_id=item.get("anime_id", 0),
                    episode=item.get("episode", 0),
                    title=item.get("title", ""),
                    snapshot=snapshots[i],
                    disc=item.get("disc", ""),
                    audio=item.get("audio", ""),
                    duration=item.get("duration", ""),
                    session=item.get("session", ""),
                    filler=bool(item.get("filler", 0)),
                )
            )
        has_more = data.get("current_page", 1) < data.get("last_page", 1)
        logger.info(
            "EPISODES_API parsed %d results, has_more=%s", len(results), has_more
        )
        return results, has_more

    async def _episodes_html(
        self, anime_session: str, page: int = 1
    ) -> tuple[list[Episode], bool]:
        logger.warning("EPISODES_HTML not implemented for session=%s", anime_session)
        return [], False

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        cache_key = f"sources_{anime_session}_{episode_session}"
        cached = self._get_mem(cache_key, ttl=300)
        if cached:
            logger.info("SOURCES returning %d items from cache", len(cached))
            return cached

        logger.info("SOURCES session=%s episode=%s", anime_session, episode_session)
        results = await self._sources_data_src(anime_session, episode_session)
        if results:
            logger.info("SOURCES data-src returned %d results", len(results))
            self._set_mem(cache_key, results, ttl=300)
            return results
        logger.warning("SOURCES data-src empty, trying regex fallback")
        results = await self._sources_regex(anime_session, episode_session)
        logger.info("SOURCES regex returned %d results", len(results))
        self._set_mem(cache_key, results, ttl=300)
        return results

    async def _sources_data_src(
        self, anime_session: str, episode_session: str
    ) -> list[Source]:
        url = f"{BASE}/play/{anime_session}/{episode_session}"
        logger.info("SOURCES_DATA_SRC fetching %s", url)
        try:
            resp = await self.ddos.get(url)
            logger.info(
                "SOURCES_DATA_SRC status=%s len=%s", resp.status_code, len(resp.text)
            )
            if resp.status_code != 200:
                logger.warning("SOURCES_DATA_SRC not 200, body: %s", resp.text[:200])
                return []
        except Exception as ex:
            logger.error("SOURCES_DATA_SRC fetch failed: %s", ex)
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
        logger.info("SOURCES_DATA_SRC found %d kwik sources", len(sources))
        return sources

    async def _sources_regex(
        self, anime_session: str, episode_session: str
    ) -> list[Source]:
        url = f"{BASE}/play/{anime_session}/{episode_session}"
        logger.info("SOURCES_REGEX fetching %s", url)
        try:
            resp = await self.ddos.get(url)
            logger.info(
                "SOURCES_REGEX status=%s len=%s", resp.status_code, len(resp.text)
            )
            if resp.status_code != 200:
                return []
        except Exception as ex:
            logger.error("SOURCES_REGEX fetch failed: %s", ex)
            return []
        urls = re.findall(r"https?://kwik\.[a-z]+/(?:e|f|d)/[A-Za-z0-9_-]+", resp.text)
        seen = set()
        sources = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                sources.append(Source(url=url, resolution=0, audio="jpn", fansub=""))
        logger.info("SOURCES_REGEX found %d kwik URLs", len(sources))
        return sources

    def clear_cache(self):
        self._mem_cache.clear()
        self._mem_ttl.clear()
        logger.info("CACHE cleared")

    async def close(self):
        await self.ddos.close()
