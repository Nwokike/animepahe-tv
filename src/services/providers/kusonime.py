"""Kusonime provider — WordPress + own page + direct file hosts.

Self-contained (nkiri-shaped): WP REST for search/catalog/posters, the
post's HTML page for download links, and a direct-file resolve. Its
files are BATCH archives (one rar per quality, "01-16" in the filename)
via hosts with public APIs — pixeldrain verified clean (200 + range
support, no challenge). That makes kusonime the provider that actually
DELIVERS files today (download-first; an episode inside a batch is
fetched by the downloader, not streamed).
"""

import logging
import re

from core.config import CACHE_TTL_EPISODES, CACHE_TTL_LATEST, CACHE_TTL_SEARCH
from core.state import Anime, Episode, Source
import primp
from services.providers.base import make_session, split_session

logger = logging.getLogger("animepahe.provider.kusonime")

KUSONIME_API = "https://kusonime.com/wp-json/wp/v2"
KUSONIME_BASE = "https://kusonime.com"

# Hosts with a public, direct, documented API (verified in Phase 0).
# Anything else on the page is ignored — no fragile leecher resolvers.
_SUPPORTED_HOSTS = ("pixeldrain.com",)


def _clean_title(raw: str) -> tuple[str, int, str]:
    text = re.sub(r"<[^>]+>", "", raw or "").replace("&amp;", "&")
    year_match = re.search(r"\((\d{4})\)", text)
    year = int(year_match.group(1)) if year_match else 0
    title = re.sub(r"\(\d{4}\)", "", text).strip()
    lower = text.lower()
    media_type = "TV"
    if "movie" in lower or "film" in lower:
        media_type = "Movie"
    return title.strip(" -–—|")[:200], year, media_type


def _title_relevance(query: str, title: str) -> int:
    def norm(s: str) -> set[str]:
        return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 1}

    q_words, t_words = norm(query), norm(title)
    if not q_words:
        return 0
    hits = sum(1 for w in q_words if w in t_words)
    return hits * 100 // len(q_words) if hits else 0


def _batch_range(filename: str) -> tuple[int, int]:
    """'[Kusonime] Title BD 01-16 360p.rar' -> (1, 16)."""
    m = re.search(r"\b(\d{1,4})\s*-\s*(\d{1,4})\b", filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d{1,4})\b", filename)
    if m:
        return int(m.group(1)), int(m.group(1))
    return 1, 1


def _quality(filename: str) -> int:
    m = re.search(r"(\d{3,4})p", filename, re.I)
    return int(m.group(1)) if m else 0


class KusonimeProvider:
    name = "kusonime"
    capabilities = {"files": True, "episodes": True, "episode_stills": False}

    def __init__(self, client=None, page_client=None):
        self._client = client or primp.AsyncClient(
            impersonate="chrome", timeout=20.0, follow_redirects=True
        )
        self._page_client = page_client
        self._mem: dict = {}
        self._ttl: dict = {}
        self._slugs: dict[str, str] = {}

    def _cache_get(self, key: str):
        import time

        item = self._mem.get(key)
        if item is not None and time.time() < self._ttl.get(key, 0):
            return item
        self._mem.pop(key, None)
        return None

    def _cache_put(self, key: str, value, ttl: int) -> None:
        import time

        self._mem[key] = value
        self._ttl[key] = time.time() + ttl

    def _page(self):
        if self._page_client is None:
            self._page_client = primp.AsyncClient(
                impersonate="chrome", timeout=20.0, follow_redirects=True
            )
        return self._page_client

    async def probe(self) -> bool:
        try:
            resp = await self._client.get(f"{KUSONIME_API}/posts", params={"per_page": 1, "_fields": "id"}, timeout=10.0)
            return resp.status_code == 200
        except Exception as ex:
            logger.debug("kusonime probe failed: %s", ex)
            return False

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    async def _posts_to_anime(self, posts: list[dict]) -> list[Anime]:
        media_ids = [p["featured_media"] for p in posts if p.get("featured_media")]
        poster_map: dict[int, str] = {}
        if media_ids:
            try:
                resp = await self._client.get(
                    f"{KUSONIME_API}/media",
                    params={"include": ",".join(str(i) for i in media_ids), "per_page": 20, "_fields": "id,source_url"},
                )
                poster_map = {m["id"]: m.get("source_url", "") for m in resp.json()}
            except Exception:
                poster_map = {}
        results = []
        for post in posts:
            title, year, media_type = _clean_title(post.get("title", {}).get("rendered", ""))
            if not title:
                continue
            slug = _post_slug(post)
            results.append(
                Anime(
                    id=int(post.get("id") or 0),
                    title=title,
                    type=media_type,
                    episodes=0,
                    status="",
                    season="",
                    year=year,
                    score=0.0,
                    poster=poster_map.get(post.get("featured_media"), ""),
                    session=make_session("kusonime", str(post.get("id") or "")),
                    # slug rides on the session's carrier for the page fetch
                    # (stored in _slugs); kept off the domain object.
                )
            )
            if slug:
                self._slugs[str(post.get("id"))] = slug
        return results

    _slugs: dict[str, str] = {}

    async def latest_releases(self, page: int) -> tuple[list[Anime], bool]:
        key = f"latest_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KUSONIME_API}/posts",
            params={"per_page": 12, "page": page, "orderby": "date", "order": "desc", "_fields": "id,title,featured_media,link"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"kusonime HTTP {resp.status_code}")
        posts = resp.json()
        result = (await self._posts_to_anime(posts), len(posts) == 12)
        self._cache_put(key, result, CACHE_TTL_LATEST)
        return result

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:
        key = f"search_{query}_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KUSONIME_API}/posts",
            params={"search": query, "per_page": 12, "page": page, "_fields": "id,title,featured_media,link"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"kusonime HTTP {resp.status_code}")
        posts = resp.json()
        scored = [
            (_title_relevance(query, _clean_title(p.get("title", {}).get("rendered", ""))[0]), p)
            for p in posts
        ]
        scored.sort(key=lambda sp: -sp[0])
        result = (await self._posts_to_anime([p for _, p in scored]), len(posts) == 12)
        self._cache_put(key, result, CACHE_TTL_SEARCH)
        return result

    async def anime(self, session: str) -> Anime | None:
        _, native = split_session(session)
        if not native.isdigit():
            return None
        resp = await self._client.get(
            f"{KUSONIME_API}/posts/{native}", params={"_fields": "id,title,link"}
        )
        if resp.status_code != 200:
            return None
        results = await self._posts_to_anime([resp.json()])
        return results[0] if results else None

    async def _post_url(self, native_id: str) -> str:
        """The post's HTML page carries the download links (wp-json's
        content is a stub for this site)."""
        slug = self._slugs.get(native_id)
        if slug:
            return f"{KUSONIME_BASE}/{slug}/"
        resp = await self._client.get(
            f"{KUSONIME_API}/posts/{native_id}", params={"_fields": "id,link"}
        )
        if resp.status_code != 200:
            return ""
        link = resp.json().get("link", "")
        return link or ""

    async def _batch_files(self, native_id: str) -> list[dict]:
        """Download links from the post page, restricted to hosts with a
        public direct API. Returns [{url, quality, filename}]."""
        key = f"files_{native_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        url = await self._post_url(native_id)
        if not url:
            return []
        try:
            page = await self._page().get(url)
            if page.status_code != 200:
                return []
        except Exception as ex:
            logger.debug("kusonime page fetch failed: %s", ex)
            return []
        files = []
        # The filename lives in the anchor TEXT (pixeldrain URLs end in an
        # opaque id), so pairs of (href, text) are needed.
        for href, text in re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]*)</a>', page.text):
            if not any(host in href for host in _SUPPORTED_HOSTS):
                continue
            filename = (text or href.rsplit("/", 1)[-1]).strip()
            files.append({"url": href, "quality": _quality(filename), "filename": filename})
        self._cache_put(key, files, CACHE_TTL_EPISODES)
        return files

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        _, native = split_session(session)
        if not native.isdigit():
            return []
        key = f"episodes_{native}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        files = await self._batch_files(native)
        results: list[Episode] = []
        seen: set[int] = set()
        for f in files:
            lo, hi = _batch_range(f["filename"])
            for ep in range(lo, hi + 1):
                if ep in seen:
                    continue
                seen.add(ep)
                results.append(
                    Episode(
                        id=ep,
                        anime_id=int(native),
                        episode=ep,
                        title=f"Episode {ep}",
                        snapshot="",
                        disc=f["quality"] and f"{f['quality']}p",
                        audio="jpn",
                        duration="",
                        session=f"{native}|{ep}",  # resolved to a file in sources()
                        filler=False,
                    )
                )
        results.sort(key=lambda e: e.episode)
        self._cache_put(key, results, CACHE_TTL_EPISODES)
        return (results, False)

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        _, native = split_session(anime_session)
        episode = _parse_episode_session(episode_session)
        files = await self._batch_files(native)
        matches = []
        for f in files:
            lo, hi = _batch_range(f["filename"])
            if episode and lo <= episode <= hi:
                matches.append(f)
        if not matches:
            return []
        results = []
        for f in matches:
            direct = _pixeldrain_direct(f["url"])
            if direct:
                results.append(
                    Source(
                        url=direct,
                        resolution=f["quality"],
                        audio="jpn",
                        fansub="Kusonime",
                    )
                )
        return results

    async def episodes_for_title(self, title: str) -> list[Episode]:
        results, _ = await self.search(title, 1)
        for anime in results:
            if _title_relevance(title, anime.title) >= 100:
                episodes, _ = await self.episodes(anime.session, 1)
                return episodes
        return []

    async def sources_for_title(self, title: str, episode: int) -> list[Source]:
        results, _ = await self.search(title, 1)
        for anime in results:
            if _title_relevance(title, anime.title) >= 100:
                return await self.sources(anime.session, f"{anime.id}|{episode}")
        return []

    async def close(self):
        await self._client.aclose()
        if self._page_client and not self._page_client.is_closed:
            await self._page_client.aclose()


def _post_slug(post: dict) -> str:
    link = post.get("link") or ""
    m = re.match(r"https?://kusonime\.com/([^/]+)/?", link)
    return m.group(1) if m else ""


def _parse_episode_session(episode_session: str) -> int | None:
    """'12345|7' -> 7 (a plain number also passes through)."""
    if "|" in episode_session:
        _, _, tail = episode_session.rpartition("|")
        return int(tail) if tail.isdigit() else None
    return int(episode_session) if str(episode_session).isdigit() else None


def _pixeldrain_direct(url: str) -> str:
    """pixeldrain.com/u/{id} -> pixeldrain.com/api/file/{id} (direct, no
    challenge, range-supported — verified in Phase 0)."""
    m = re.search(r"pixeldrain\.com/u/([A-Za-z0-9]+)", url)
    return f"https://pixeldrain.com/api/file/{m.group(1)}" if m else ""
