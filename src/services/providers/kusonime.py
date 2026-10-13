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
# Hosts with a verified public direct route: pixeldrain (its /api/file
# route, 206-verified) and Google Drive (usercontent, 206-verified).
_SUPPORTED_HOSTS = ("pixeldrain.com",)
_SUPPORTED_DRIVE = ("drive.usercontent.google.com", "drive.google.com/uc")


def _pixeldrain_id(url: str) -> str:
    m = re.search(r"pixeldrain\.com/u/([A-Za-z0-9]+)", url)
    return m.group(1) if m else ""


def _drive_file_id(url: str) -> str:
    """The file id out of any of Drive's page shapes (/file/d/ID/view,
    open?id=ID, uc?id=ID). Empty for folders — those are not streamable."""
    m = re.search(r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)", url) or re.search(
        r"[?&]id=([A-Za-z0-9_-]+)", url
    )
    return m.group(1) if m else ""


def _drive_direct(url: str) -> str:
    """The keyless usercontent route for a Drive file link — the shape
    kayoanime verified (206 with seek, no key, no consent). The raw page
    href is HTML, so it is never playable as-is."""
    file_id = _drive_file_id(url)
    if not file_id:
        return ""
    return (
        "https://drive.usercontent.google.com/download"
        f"?id={file_id}&export=download&confirm=t"
    )


def _human_size(size) -> str:
    try:
        n = int(size or 0)
    except (TypeError, ValueError):
        return ""
    return f"{n // (1024 * 1024)}MB" if n >= 1024 * 1024 else ""


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


def _block_quality(header: str) -> int:
    """The .smokeurlrh block's <strong> header IS the quality — the
    anchor text is only a host label. Both header shapes the site has
    served: the '360P' form and the pixel-dimension form ('848×352',
    '1280×720') whose HEIGHT is the quality."""
    m = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", header or "")
    if m:
        return int(m.group(2))
    m = re.search(r"(\d{3,4})\s*p", header or "", re.I)
    return int(m.group(1)) if m else 0


def _quality_from_slug(url: str) -> int:
    """acefile slugs end with the range+quality+extension
    ('...-01-15-480p-rar')."""
    m = re.search(r"-(\d{3,4})p-(?:mkv|mp4|rar)", url or "", re.I)
    return int(m.group(1)) if m else 0


def _range_from_slug(url: str) -> tuple[int, int] | None:
    """'...-01-15-480p-rar' -> (1, 15)."""
    m = re.search(r"-(\d{1,4})-(\d{1,4})-\d{3,4}p-(?:mkv|mp4|rar)", url or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _range_from_text(page_text: str) -> tuple[int, int] | None:
    """A textual 'Episode 01-12' fragment on the page."""
    m = re.search(r"Episode\s*(\d{1,4})\s*[-–]\s*(\d{1,4})", page_text or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _batch_range(filename: str) -> tuple[int, int] | None:
    """The rar NAME when it carries the range — the last resort; pixeldrain
    names are often range-less."""
    m = re.search(r"\b(\d{1,4})\s*-\s*(\d{1,4})\b", filename or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _is_archive(name: str) -> bool:
    return name.lower().endswith(".rar")


def _is_video(name: str) -> bool:
    return name.lower().endswith((".mkv", ".mp4"))


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
            resp = await self._client.get(
                f"{KUSONIME_API}/posts",
                params={"per_page": "1", "_fields": "id"},
                timeout=10.0,
            )
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
                    params={
                        "include": ",".join(str(i) for i in media_ids),
                        "per_page": 20,
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

    # ------------------------------------------------------------------
    # Discovery — the WP category taxonomy (8 categories + franchise tags,
    # both discovered at runtime)
    # ------------------------------------------------------------------

    async def filters(self) -> list[dict]:
        key = "filters"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        options: list[dict] = []
        try:
            resp = await self._client.get(
                f"{KUSONIME_API}/categories",
                params={"per_page": 100, "_fields": "id,name,count"},
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
            logger.debug("kusonime categories failed: %s", ex)
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
        params = {
            "per_page": "12",
            "page": str(page),
            "orderby": str(filters.get("orderby") or "date"),
            "order": "desc",
            "_fields": "id,title,featured_media,link",
        }
        if filters.get("categories"):
            params["categories"] = ",".join(str(c) for c in filters["categories"])
        resp = await self._client.get(f"{KUSONIME_API}/posts", params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"kusonime HTTP {resp.status_code}")
        posts = resp.json()
        return (await self._posts_to_anime(posts), len(posts) == 12)

    async def latest_releases(self, page: int) -> tuple[list[Anime], bool]:
        key = f"latest_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KUSONIME_API}/posts",
            params={
                "per_page": "12",
                "page": str(page),
                "orderby": "date",
                "order": "desc",
                "_fields": "id,title,featured_media,link",
            },
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
            params={
                "search": query,
                "per_page": "12",
                "page": str(page),
                "_fields": "id,title,featured_media,link",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"kusonime HTTP {resp.status_code}")
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

    async def _pixeldrain_info(self, file_id: str) -> dict:
        """pixeldrain's public file record — the TRUE name+extension
        (site-visible names are host labels or range-less)."""
        key = f"pd_info_{file_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        try:
            resp = await self._client.get(
                f"https://pixeldrain.com/api/file/{file_id}/info"
            )
            if resp.status_code != 200:
                return {}
            info = resp.json()
        except Exception as ex:
            logger.debug("pixeldrain info failed: %s", ex)
            return {}
        self._cache_put(key, info, CACHE_TTL_EPISODES)
        return info

    def _parse_download_blocks(self, html: str) -> list[dict]:
        """#dl's .smokeurlrh blocks — quality from the <strong> header,
        links per block. Returns [{quality, href, host_kind}] for the
        hosts we can resolve (pixeldrain, Drive). The pixeldrain id is
        the dedup key (the map caught the same id under two blocks)."""
        dl = re.search(
            r'id="dl"[^>]*>(.*?)(?:id="dl-notif"|<footer|</body)', html, re.S
        )
        section = dl.group(1) if dl else html
        files: list[dict] = []
        seen_pd: set[str] = set()
        for block in re.split(r'<div class="smokeurlrh">', section)[1:]:
            strong = re.match(r"\s*<strong>([^<]*)</strong>", block)
            quality = _block_quality(strong.group(1)) if strong else 0
            for href in re.findall(r'href="(https?://[^"]+)"', block):
                pd_id = _pixeldrain_id(href)
                if pd_id:
                    if pd_id in seen_pd:
                        continue
                    seen_pd.add(pd_id)
                    files.append(
                        {
                            "url": href,
                            "quality": quality,
                            "kind": "pixeldrain",
                            "pixeldrain_id": pd_id,
                            "filename": "",
                        }
                    )
                elif any(h in href for h in _SUPPORTED_DRIVE):
                    files.append(
                        {
                            "url": href,
                            "quality": _quality_from_slug(href) or quality,
                            "kind": "drive",
                            "filename": "",
                        }
                    )
        return files

    async def _batch_files(self, native_id: str) -> list[dict]:
        """The post's files: block quality, host-resolved names, and the
        episode range from real evidence (acefile slug, textual fragment,
        or the rar name) — never block order."""
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
        files = self._parse_download_blocks(page.text)
        text_range = _range_from_text(page.text)
        for f in files:
            name = ""
            if f["kind"] == "pixeldrain":
                info = await self._pixeldrain_info(f["pixeldrain_id"])
                name = info.get("name", "")
                f["size_bytes"] = info.get("size")
            f["filename"] = name or f["url"].rsplit("/", 1)[-1]
            if name or _is_video(name):
                # Movie/special detection needs the true extension.
                f["video"] = _is_video(name)
                f["archive"] = _is_archive(name)
            else:
                f["video"] = _is_video(f["url"])
                f["archive"] = _is_archive(f["url"])
            f.setdefault("size_bytes", None)
            rng = _range_from_slug(f["url"])
            if rng is None and f.get("pixeldrain_id"):
                rng = _batch_range(name)
            if rng is None:
                rng = text_range
            f["range"] = None if f["video"] else (rng or (1, 1))
        self._cache_put(key, files, CACHE_TTL_EPISODES)
        return files

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        """Series posts synthesize their episodes from the archives'
        evidence ranges; movie/special posts surface as ONE playable
        episode (the film) — never a batch."""
        _, native = split_session(session)
        if not native.isdigit():
            return []
        key = f"episodes_{native}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        files = await self._batch_files(native)
        results: list[Episode] = []
        if any(f.get("video") for f in files):
            # Movie / special / single video: one episode, all qualities.
            results.append(
                Episode(
                    id=1,
                    anime_id=int(native),
                    episode=1,
                    title="Movie",
                    snapshot="",
                    disc="",
                    audio="jpn",
                    duration="",
                    session=f"{native}|movie",
                    filler=False,
                )
            )
        else:
            seen: set[int] = set()
            for f in files:
                for ep in range(f["range"][0], f["range"][1] + 1):
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
        """Movies stream (direct per-quality files, pixeldrain 206
        verified); series episodes resolve to the archive that covers
        them (download flow). Only verified hosts are claimed."""
        _, native = split_session(anime_session)
        episode = _parse_episode_session(episode_session)
        is_movie = (episode_session or "").endswith("|movie")
        files = await self._batch_files(native)
        matches = []
        for f in files:
            drive = (
                _drive_direct(f["url"])
                if any(h in f["url"] for h in _SUPPORTED_DRIVE)
                else ""
            )
            # A Drive file streams like a movie file (it IS one) — the
            # page shape just never says "video" the way a .rar does.
            if is_movie and (f.get("video") or drive):
                matches.append(f)
            elif not is_movie and not f.get("video") and episode and f["range"]:
                if f["range"][0] <= episode <= f["range"][1]:
                    matches.append(f)
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
                        size=_human_size(f.get("size_bytes")),
                    )
                )
            else:
                keyless = _drive_direct(f["url"])
                if keyless:
                    # The usercontent route (206-verified, same shape as
                    # kayoanime's keyless download) rather than the page
                    # href, which is HTML.
                    results.append(
                        Source(
                            url=keyless,
                            resolution=f["quality"],
                            audio="jpn",
                            fansub="Kusonime",
                            headers={"Referer": "https://drive.google.com/"},
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
