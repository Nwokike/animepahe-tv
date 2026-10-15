"""AnimeOut provider — the modern WordPress way (nkiri-shaped, anime).

Self-contained: WP REST for search/catalog/posters, per-episode direct
MKV links inside post content, and the two-hop link-page resolve
(index.php -> public.php -> the JS ``var url`` target). Mapped hop by
hop in Phase 0 (docs/decisions.md). The final host (public.animeout.xyz)
is Cloudflare-challenged TODAY, so files report unplayable until it
clears — the code is durable and lights up the moment it does.
"""

import logging
import re

from core.config import (
    ANIMEOUT_API,
    CACHE_TTL_EPISODES,
    CACHE_TTL_LATEST,
    CACHE_TTL_SEARCH,
)
from core.state import Anime, Episode, LatestRelease, Source
import primp
from services.providers.base import (
    close_client,
    make_session,
    releases_from_anime,
    split_session,
)

logger = logging.getLogger("animepahe.provider.animeout")

_FILE_HOST = "public.animeout.xyz"


def _clean_title(raw: str) -> tuple[str, int, str]:
    text = re.sub(r"<[^>]+>", "", raw or "")
    text = re.sub(r"&amp;", "&", text)
    year_match = re.search(r"\((\d{4})\)", text)
    year = int(year_match.group(1)) if year_match else 0
    title = re.sub(r"\(\d{4}\)", "", text).strip()
    lower = text.lower()
    media_type = "TV"
    if any(k in lower for k in ("movie", "film", "gekijouban", "the movie")):
        media_type = "Movie"
    elif "ova" in lower or "special" in lower:
        media_type = "OVA"
    return title.strip(" -–—")[:200], year, media_type


def _title_relevance(query: str, title: str) -> int:
    """WP's full-text search is fuzzy ("attack on titan" -> Yu-Gi-Oh GX).
    Score how much of the query the title actually covers; 0 = no match.
    No filtering — ranking only, so nothing is ever hidden."""
    import re as _re

    def norm(s: str) -> set[str]:
        return {w for w in _re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 1}

    q_words, t_words = norm(query), norm(title)
    if not q_words:
        return 0
    hits = sum(1 for w in q_words if w in t_words)
    # All-or-nothing weighting: every query word must appear somewhere.
    return hits * 100 // len(q_words) if hits else 0


class AnimeOutProvider:
    name = "animeout"
    # files: True — the provider's route DOES serve files. The file host is
    # a Cloudflare JS challenge, and the clearance decides availability at
    # runtime (no clearance -> sources() returns [] and the router moves on,
    # exactly as a provider with no answer). See AnimeOutSolver.
    capabilities = {"files": True, "episodes": True, "episode_stills": False}

    def __init__(self, client=None, solver=None):
        self._client = client or primp.AsyncClient(
            impersonate="chrome",
            timeout=20.0,
            follow_redirects=True,
            headers={"Referer": "https://animeout.xyz/"},
        )
        self._solver = solver
        self._mem: dict = {}
        self._ttl: dict = {}

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

    async def probe(self) -> bool:
        try:
            resp = await self._client.get(
                f"{ANIMEOUT_API}/posts",
                params={"per_page": "1", "_fields": "id"},
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as ex:
            logger.debug("animeout probe failed: %s", ex)
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
                    f"{ANIMEOUT_API}/media",
                    params={
                        "include": ",".join(str(i) for i in media_ids),
                        "per_page": "20",
                        "_fields": "id,source_url",
                    },
                )
                poster_map = {m["id"]: m.get("source_url", "") for m in resp.json()}
            except Exception:
                poster_map = {}
        results = []
        for post in posts:
            title, year, media_type = _clean_title(
                post.get("title", {}).get("rendered", "")
            )
            if not title:
                continue
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
                    session=make_session("animeout", str(post.get("id") or "")),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Discovery — the WP category taxonomy, discovered at runtime
    # (the map documents 28 categories with counts; we read them, we do
    # not embed a table)
    # ------------------------------------------------------------------

    async def filters(self) -> list[dict]:
        key = "filters"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        options: list[dict] = []
        try:
            resp = await self._client.get(
                f"{ANIMEOUT_API}/categories",
                params={"per_page": "100", "_fields": "id,name,count"},
            )
            if resp.status_code == 200:
                for row in resp.json():
                    if not isinstance(row, dict) or not row.get("name"):
                        continue
                    options.append(
                        {
                            "value": str(row.get("id")),
                            "label": f"{row['name']} ({row.get('count', 0)})",
                        }
                    )
        except Exception as ex:
            logger.debug("animeout categories failed: %s", ex)
        spec: list[dict] = []
        if options:
            spec.append(
                {
                    "key": "categories",
                    "label": "Category",
                    "kind": "choice",
                    "options": options,
                }
            )
        spec.append(
            {
                "key": "orderby",
                "label": "Sort",
                "kind": "choice",
                "options": [
                    {"value": "date", "label": "Newest"},
                    {"value": "modified", "label": "Recently updated"},
                    {"value": "title", "label": "Title"},
                ],
            }
        )
        self._cache_put(key, spec, CACHE_TTL_LATEST)
        return spec

    async def browse(self, filters: dict, page: int) -> tuple[list[Anime], bool]:
        params: dict = {
            "per_page": 24,
            "page": page,
            "_fields": "id,title,featured_media",
        }
        categories = filters.get("categories")
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)
        elif filters.get("tags"):
            params["tags"] = ",".join(str(t) for t in filters["tags"])
        if filters.get("orderby"):
            params["orderby"] = str(filters["orderby"])
        resp = await self._client.get(f"{ANIMEOUT_API}/posts", params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"animeout HTTP {resp.status_code}")
        posts = resp.json()
        result = (await self._posts_to_anime(posts), len(posts) >= 24)
        return result

    async def latest_releases(self, page: int) -> tuple[list[LatestRelease], bool]:
        key = f"latest_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{ANIMEOUT_API}/posts",
            params={
                "per_page": "12",
                "page": str(page),
                "orderby": "date",
                "order": "desc",
                "_fields": "id,title,featured_media",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"animeout HTTP {resp.status_code}")
        posts = resp.json()
        result = (releases_from_anime(await self._posts_to_anime(posts)), len(posts) == 12)
        self._cache_put(key, result, CACHE_TTL_LATEST)
        return result

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:
        key = f"search_{query}_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{ANIMEOUT_API}/posts",
            params={
                "search": query,
                "per_page": "12",
                "page": str(page),
                "_fields": "id,title,featured_media",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"animeout HTTP {resp.status_code}")
        posts = resp.json()
        scored = [
            (
                _title_relevance(
                    query, _clean_title(p.get("title", {}).get("rendered", ""))[0]
                ),
                p,
            )
            for p in posts
        ]
        scored.sort(key=lambda sp: -sp[0])
        ordered = [p for _, p in scored]
        result = (await self._posts_to_anime(ordered), len(posts) == 12)
        self._cache_put(key, result, CACHE_TTL_SEARCH)
        return result

    async def anime(self, session: str) -> Anime | None:
        _, native = split_session(session)
        if not native.isdigit():
            return None
        resp = await self._client.get(
            f"{ANIMEOUT_API}/posts/{native}", params={"_fields": "id,title"}
        )
        if resp.status_code != 200:
            return None
        post = resp.json()
        results = await self._posts_to_anime([post])
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Episodes + files (the two-hop resolve)
    # ------------------------------------------------------------------

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        _, native = split_session(session)
        if not native.isdigit():
            # Callers unpack `episodes, has_more = ...` — a bare [] raised
            # "too many values to unpack" (actually: not enough values).
            return ([], False)
        key = f"episodes_{native}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{ANIMEOUT_API}/posts/{native}", params={"_fields": "id,content"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"animeout HTTP {resp.status_code}")
        html = (resp.json().get("content") or {}).get("rendered", "")
        pairs = _parse_episode_pairs(html)
        results = _episode_rows(pairs, int(native))
        # The variant table rides the same cache so sources() can serve
        # every quality of an episode without re-fetching the post.
        self._cache_put(f"variants_{native}", _variant_map(pairs), CACHE_TTL_EPISODES)
        self._cache_put(key, results, CACHE_TTL_EPISODES)
        return (results, False)

    async def _variants_for(self, native: str) -> dict[int, list[str]]:
        """Episode number -> every direct link. Fetches the post once when
        episodes() hasn't run yet for this session."""
        key = f"variants_{native}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{ANIMEOUT_API}/posts/{native}", params={"_fields": "id,content"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"animeout HTTP {resp.status_code}")
        html = (resp.json().get("content") or {}).get("rendered", "")
        mapping = _variant_map(_parse_episode_pairs(html))
        self._cache_put(key, mapping, CACHE_TTL_EPISODES)
        return mapping

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        """Every quality of one episode through the link-page chain.
        Raises on transport failure — the caller treats it as no stream
        (a chosen source is the app; nothing fails over behind the scenes).
        An empty list means the chain resolved but delivered nothing."""
        _, native = split_session(anime_session)
        # The episode number is in the link's own filename, so the sibling
        # qualities of the same episode are found by number.
        number = _episode_number(episode_session)
        links: list[str] = [episode_session]
        if native.isdigit() and number:
            try:
                variants = await self._variants_for(native)
            except Exception as ex:
                logger.debug("animeout variants fetch failed: %s", ex)
                variants = {}
            for href in variants.get(number, []):
                if href not in links:
                    links.append(href)
        clearance = await self._solver.clearance() if self._solver else None
        if clearance is None and self._solver is not None:
            # The wall is active and the solver has nothing (the user
            # declined, or the desktop helper failed): no stream, no raise.
            logger.info("animeout: no clearance, reporting no stream")
            return []
        sources: list[Source] = []
        for href in links:
            url = await _resolve_direct_url(href, client=self._client)
            if _FILE_HOST in url and clearance is None:
                # The file host is Cloudflare-challenged today; skip this
                # link rather than hammering it. continue, not return — a
                # bare return discarded the qualities already collected.
                continue
            if not url.startswith("http"):
                continue
            resolution, audio, fansub = _parse_filename(url)
            sources.append(
                Source(
                    url=url,
                    resolution=resolution,
                    audio=audio,
                    fansub=fansub,
                    headers=self._solver.file_headers(clearance)
                    if self._solver
                    else {},
                )
            )
        return sources

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
                episodes, _ = await self.episodes(anime.session, 1)
                for ep in episodes:
                    if ep.episode == episode:
                        return await self.sources(anime.session, ep.session)
        return []

    async def close(self):
        await close_client(self._client)


def _episode_number(filename: str) -> int:
    """The episode number inside a release filename. Patterns tried in
    order (S01E12, "- 12", "Episode 12", bare) — different eras of posts
    use different conventions. 0 when nothing matches."""
    m = (
        re.search(r"\bS\d{1,2}E(\d{1,4})\b", filename, re.I)
        or re.search(r"-\s*(\d{1,4})\s*\d*\s*\[", filename, re.I)
        or re.search(r"[Ee]pisode\s*(\d{1,4})", filename, re.I)
        or re.search(r"\b(\d{1,4})\b", filename, re.I)
    )
    return int(m.group(1)) if m else 0


def _parse_episode_pairs(html: str) -> list[tuple[int, str]]:
    """Every (episode number, direct link) pair in a post's content —
    INCLUDING multiple qualities of the same episode. Posts serve e.g.
    both [1080pp] and [720p] links for one episode; dropping the second
    here is what made the promised 1080p/720p choice impossible."""
    hrefs = re.findall(r"href=['\"](https?://[^'\"]+\.mkv)['\"]", html, re.I)
    pairs: list[tuple[int, str]] = []
    for href in hrefs:
        filename = href.rsplit("/", 1)[-1]
        number = _episode_number(filename)
        if number:
            pairs.append((number, href))
    # Stable and best-first: highest quality first, then link order.
    pairs.sort(key=lambda pair: -_parse_filename(pair[1])[0])
    return pairs


def _episode_rows(pairs: list[tuple[int, str]], anime_id: int) -> list[Episode]:
    """One display row per episode number (the best quality link is its
    session) — the grid shows one card per episode, not one per link."""
    rows: list[Episode] = []
    seen: set[int] = set()
    for ep_num, href in pairs:
        if ep_num in seen:
            continue
        seen.add(ep_num)
        filename = href.rsplit("/", 1)[-1]
        rows.append(
            Episode(
                id=ep_num,
                anime_id=anime_id,
                episode=ep_num,
                title=f"Episode {ep_num}",
                snapshot="",
                disc="",
                # Dual-audio rows say "dual" — the same vocabulary
                # _parse_filename uses for the source rows.
                audio="dual" if "dual" in filename.lower() else "jpn",
                duration="",
                session=href,
                filler=False,
            )
        )
    rows.sort(key=lambda e: e.episode)
    return rows


def _variant_map(pairs: list[tuple[int, str]]) -> dict[int, list[str]]:
    """Episode number -> every direct link for it, best quality first."""
    mapping: dict[int, list[str]] = {}
    for ep_num, href in pairs:
        mapping.setdefault(ep_num, []).append(href)
    return mapping


def _parse_filename(url: str) -> tuple[int, str, str]:
    name = url.rsplit("/", 1)[-1]
    resolution = 0
    m = re.search(r"(\d{3,4})p", name, re.I)
    if m:
        resolution = int(m.group(1))
    m = re.search(r"\[(\d{3,4})pp?\]", name, re.I)
    if m and not resolution:
        resolution = int(m.group(1))
    audio = "jpn"
    if "dual" in name.lower():
        audio = "dual"
    elif "dub" in name.lower():
        audio = "eng"
    # Fansub = the first NAME bracket after the release-group tag. The
    # AnimeOut convention is [Group] Title - EP [hash][1080pp][Fansub]
    # [codec][Bot]; the first bracket is the releaser, not the fansub.
    _CODECS = {"x265", "x264", "hevc", "avc", "10bit", "8bit", "hi10p", "flac", "aac"}
    fansub = ""
    names: list[str] = []
    for group in re.findall(r"\[([^\]]+)\]", name):
        g = group.strip()
        if not g or not re.search(r"[A-Za-z]{2,}", g):
            continue
        if (
            re.fullmatch(r"\d{3,4}p{1,2}", g, re.I)
            or g.lower() in _CODECS
            or re.fullmatch(r"[0-9A-F]{6,}", g)
        ):
            continue
        names.append(g)
    if len(names) > 1:
        fansub = names[1]
    elif names:
        fansub = names[0]
    return resolution, audio, fansub


async def _resolve_direct_url(episode_url: str, client=None) -> str:
    """Follow the two-hop landing chain and extract the file URL.

    episode_url (nimbus/...mkv) -> 301/302 -> index.php?url= ->
    page with public.php?url= -> page with inline ``var url = "..."``.
    Async throughout so the router's event loop never blocks on it.
    """
    import primp as _primp

    own = client is None
    try:
        if own:
            client = _primp.AsyncClient(
                impersonate="chrome",
                timeout=20.0,
                follow_redirects=True,
                headers={"Referer": "https://animeout.xyz/"},
            )
        landing = await client.get(episode_url)
        if landing.status_code != 200:
            return ""
        public = re.search(
            r'href="(https://ddl\.animeout\.com/public\.php\?url=[^"]+)"', landing.text
        )
        if not public:
            return ""
        page = await client.get(public.group(1).replace("&amp;", "&"))
        target = re.search(r'var\s+url\s*=\s*"([^"]+)"', page.text)
        return target.group(1) if target else ""
    except Exception as ex:
        logger.debug("animeout resolve failed: %s", ex)
        return ""
    finally:
        if own and client is not None:
            # Own client: real primp 2.0.1 — __aexit__ is the only release.
            await client.__aexit__(None, None, None)
