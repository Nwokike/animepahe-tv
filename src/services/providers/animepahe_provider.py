"""AnimePahe provider — the app's proven source as provider #1.

An adapter over the EXISTING AnimePaheScraper: same shapes, same cache,
plus the m=links stream API the scraper never called (per-rendition
audio/kwik/filesize — attested by six independent clients in the
backend map). AnimePahe is complete (catalog, episodes, files via kwik)
and stays the safety net. Its session strings stay BARE (no namespace)
so the user's existing store, history and continue-watching keys keep
working unchanged.

Source-specific limits (documented in backend-animepahe.md, three
converging evidence lines each): English hardsub — NO subtitle tracks
exist (never will via the API; subs are burned in); no schedule API
(m=schedule has zero evidence anywhere); no watchlist/history API (our
store IS that feature). Dub = separate renditions at the m=links level,
correctly modelled on Source.audio.

DEVICE-VERIFY checklist (the site is CF-walled from the dev machine —
every m=links behavior verified through the app's own clearance on
hardware): (1) play an episode — m=links renditions appear in the
dialog with sizes; (2) a dubbed episode shows the DUB (ENG) group
after SUB; (3) download sizes display; (4) details screen shows the
synopsis block; (5) kwik.si Referer in the logs.
"""

import logging
from typing import ClassVar

from core.state import Anime, Episode, LatestRelease, Source
from services.animepahe import BASE as ANIMEPAHE_BASE
from services.animepahe import AnimePaheScraper
from services.providers.base import all_episodes

logger = logging.getLogger("animepahe.provider.animepahe")


class AnimePaheProvider:
    name = "animepahe"
    capabilities: ClassVar[dict] = {
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
        """Liveness only — and liveness NEVER solves a challenge.

        The api is Cloudflare-walled. A plain GET that bypasses the solver
        answers 200 (open), 403 (walled), 429 (rate-limited) or 503 — all
        REACHABLE, all healthy. Only a transport failure (DNS, refused,
        timeout) marks the provider down. Solving belongs to a deliberate
        user action: the startup probe must never open a verification
        window for a provider that is last in line for exactly that
        reason."""
        import primp

        try:
            async with primp.AsyncClient(impersonate="chrome", timeout=8.0) as client:
                resp = await client.get(
                    f"{ANIMEPAHE_BASE}/api",
                    params={"m": "airing", "page": "1"},
                    headers={"Accept": "application/json"},
                )
                # Any answer at all means the host is alive: 200 (open), 403
                # (the wall we deliberately did not solve), 429 (rate limit).
                # Only a transport failure answers nothing.
                _ = resp
                return True
        except Exception as ex:
            logger.info("animepahe probe: %s", ex)
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
        m=release (carried on the episodes we already loaded).

        `kwik_pahewin` is the pahe.win share link for that rendition — the
        site's own download offering, read verbatim onto the Source as
        ``download_url`` so the download path uses what the source gave
        rather than inventing a route."""
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
        results: list[Source] = []
        for key, entry in data.items() if isinstance(data, dict) else enumerate(data):
            if not isinstance(entry, dict) or not entry.get("kwik"):
                continue
            try:
                if isinstance(key, str) and key.isdigit():
                    resolution = int(key)
                elif (
                    isinstance(entry.get("quality"), (int, str))
                    and str(entry.get("quality")).isdigit()
                ):
                    resolution = int(entry.get("quality"))
                elif (
                    isinstance(entry.get("resolution"), (int, str))
                    and str(entry.get("resolution")).isdigit()
                ):
                    resolution = int(entry.get("resolution"))
                else:
                    resolution = 0
            except (TypeError, ValueError):
                resolution = 0
            # hd rides the fansub label the way the play-page scrape
            # carries " AV1" — visible in the quality list, no new field.
            # The site serves it as the STRING "0"/"1", so a bare
            # truthiness test would mark every rendition HD.
            fansub = "AnimePahe"
            if entry.get("hd") not in (None, "", "0", 0, False):
                fansub += " HD"
            results.append(
                Source(
                    url=str(entry["kwik"]),
                    resolution=resolution,
                    audio=str(entry.get("audio") or "jpn"),
                    fansub=fansub,
                    size=f"{entry['filesize']}MB" if entry.get("filesize") else "",
                    # the site's own download link for this rendition,
                    # read verbatim (it is what the pick menu serves)
                    download_url=str(entry.get("kwik_pahewin") or ""),
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

    async def anime(self, session: str) -> Anime | None:
        """The /anime/{session} details page — synopsis, genres, studios,
        aired range, external ids (the detail screen's Phase-3 note)."""
        try:
            resp = await self.scraper.ddos.get(f"{ANIMEPAHE_BASE}/anime/{session}")
            if resp is None or resp.status_code != 200:
                return None
            return _parse_details(resp.text, session)
        except Exception as ex:
            logger.info("animepahe details failed for %s: %s", session, ex)
            return None

    async def episodes_for_title(self, title: str) -> list[Episode]:
        results, _ = await self.scraper.search(title, 1)
        for anime in results:
            if anime.title.strip().lower() == title.strip().lower():
                return await all_episodes(self.scraper, anime.session)
        return []

    async def sources_for_title(self, title: str, episode: int) -> list[Source]:
        results, _ = await self.scraper.search(title, 1)
        for anime in results:
            if anime.title.strip().lower() == title.strip().lower():
                episodes = await all_episodes(self, anime.session)
                for ep in episodes:
                    if ep.episode == episode:
                        return await self.sources(anime.session, ep.session)
        return []

    def clear_cache(self) -> None:
        self._anime_ids.clear()
        self.scraper.clear_cache()

    async def close(self) -> None:
        await self.scraper.close()


def _parse_details(html: str, session: str) -> Anime | None:
    """The /anime/{session} page, per the three-convergent-selectors map
    (Juro / CloudStream-3 / consumet agree on every field). Pure function —
    fixture-tested; nothing invented when a field is absent."""
    import re

    def text(pattern: str) -> str:
        m = re.search(pattern, html, re.DOTALL)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    title = text(r"title-wrapper[^>]*>\s*<h1[^>]*>\s*<span[^>]*>([^<]+)</span>") or text(
        r"header[^>]*>\s*<h1[^>]*>\s*<span[^>]*>([^<]+)</span>"
    )
    if not title:
        return None
    poster = text(r'anime-poster[^>]*>\s*<a href="([^"]+)"') or text(
        r'header[^>]*>\s*<img[^>]*data-src="([^"]+)"'
    )
    # The page's own cover: body > section > article > div.header-wrapper
    # [data-src] (the map's verified selector). Absent = "" and the detail
    # screen blurs the poster, as before.
    cover_m = re.search(r'<div class="header-wrapper"[^>]*\bdata-src="([^"]+)"', html)
    backdrop = cover_m.group(1).strip() if cover_m else ""
    synopsis_raw = text(r'class="anime-synopsis[^"]*"[^>]*>(.*?)</div>') or text(
        r"anime-summary[^>]*>\s*<div[^>]*>(.*?)</div>"
    )
    synopsis = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", synopsis_raw)).strip()
    # anime-info holds only <p> rows (no nested divs) — the first
    # closing div is its own.
    info_html_m = re.search(r'class="anime-info">(.*?)</div>', html, re.DOTALL)
    info_html = info_html_m.group(1) if info_html_m else ""

    def info(label: str) -> str:
        m = re.search(label + r":\s*</b>\s*([^<]+)", info_html, re.IGNORECASE) or re.search(
            label + r":\s*([^<\n]+)", info_html, re.IGNORECASE
        )
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    # Scope to the genre block first, then each anchor (the anchor wraps
    # an <li>; strip tags for the clean name — the title attribute
    # carries "X movies").
    genre_block = re.search(r"anime-genre(.*?)</ul>", html, re.DOTALL)
    genres = (
        [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", g)).strip()
            for g in re.findall(r"<a[^>]*>(.*?)</a>", genre_block.group(1), re.DOTALL)
        ]
        if genre_block
        else []
    )
    external = re.findall(r'href="(https://(?:anilist\.co|myanimelist\.net)/anime/(\d+))"', html)
    ani_id = next((int(i) for url, i in external if "anilist" in url), 0)
    mal_id = next((int(i) for url, i in external if "myanimelist" in url), 0)
    id_m = re.search(r"release&id=(\d+)&l=", html)
    episodes_raw = info("Episodes")
    year_m = re.search(r"(19|20)\d{2}", info("Aired") or info("Season"))
    # A co-production lists several studios ("C2C, SoftBank") — keep them
    # all, split on the separator the page uses.
    studios = [s.strip() for s in re.split(r"[,/]", info("Studio")) if s.strip()]
    return Anime(
        id=int(id_m.group(1)) if id_m else 0,
        title=title[:200],
        type=info("Type"),
        episodes=int(episodes_raw) if episodes_raw.isdigit() else 0,
        status=info("Status"),
        season=info("Season"),
        year=int(year_m.group(0)) if year_m else 0,
        score=0.0,  # the page carries no score — MAL/AniList do
        poster=poster[:500],
        session=session,
        backdrop=backdrop[:500],
        synopsis=synopsis[:1200],
        genres=genres,
        mal_id=mal_id,
        anilist_id=ani_id,
        studios=studios,
        aired=info("Aired"),
    )
