"""Kayoanime provider — WordPress + Google Drive, complete from day one.

Self-contained (title in → catalog/posters/episodes/files out), per the
certified backend map (docs/reference/backend-kayoanime.md):

- Catalog: WordPress REST — search (noisy: WP full-text matches inside
  post content, so results are title-ranked client-side), the
  orderby=modified feed for "latest", categories for browse.
- Files: post content's Drive folder anchors are the organization
  ((folderId, label) pairs; BOX N = contiguous episode ranges). Folders
  are FLAT — .mkv per episode, one quality per post (1080p HEVC).
- Streaming: each episode file is a direct 206-serving URL (keyed
  alt=media route + keyless usercontent route, both verified with
  range seeks including tail). No proxy, no unpack — ready files.
- Downloads: the keyless route carries the real filename.
- Restrictions: `[Private Drive]` folders (Google-Group gated) surface
  honestly and are NEVER retried; `href="#"` / zero folder ids means
  links-under-maintenance.
"""

import logging
import re

import primp

from core.config import (
    KAYOANIME_API,
    CACHE_TTL_EPISODES,
    CACHE_TTL_LATEST,
    CACHE_TTL_SEARCH,
    DRIVE_API,
    DRIVE_REFERER,
    DRIVE_WEB_KEY,
)
from core.state import Anime, Episode, LatestRelease, Source
from services.providers.base import (
    close_client,
    make_session,
    releases_from_anime,
    split_session,
)

logger = logging.getLogger("animepahe.provider.kayoanime")

# Files smaller than this are almost certainly not episodes.
_MIN_EPISODE_BYTES = 5 * 1024 * 1024


def _clean_title(raw: str) -> tuple[str, int, str]:
    text = re.sub(r"<[^>]+>", "", raw or "").replace("&amp;", "&")
    year_match = re.search(r"\((\d{4})\)", text)
    year = int(year_match.group(1)) if year_match else 0
    title = re.sub(r"\(\d{4}\)", "", text).strip()
    title = re.sub(r"\|\s*Kayoanime\s*$", "", title, flags=re.I).strip()
    lower = text.lower()
    media_type = "TV"
    if "movie" in lower or "gekijouban" in lower:
        media_type = "Movie"
    return title.strip(" -–—")[:200], year, media_type


def _title_relevance(query: str, title: str) -> int:
    """WP full-text matches inside CONTENT, so search noise is real
    ("one piece" → Barakamon). Score = how much of the query the title
    covers; ranking only — nothing is filtered out."""

    def norm(s: str) -> set[str]:
        return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 1}

    q_words, t_words = norm(query), norm(title)
    if not q_words:
        return 0
    hits = sum(1 for w in q_words if w in t_words)
    return hits * 100 // len(q_words) if hits else 0


def _folder_pairs(content_html: str) -> list[tuple[str, str]]:
    """(folderId, label) from the post content's Drive folder anchors —
    the labels ARE the organization metadata."""
    pairs: list[tuple[str, str]] = []
    for href, label in re.findall(
        r'<a\b[^>]*href="[^"]*drive\.google\.com/drive/folders/([A-Za-z0-9_\-]{20,})[^"]*"[^>]*>(.*?)</a>',
        content_html,
        re.S,
    ):
        clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        pairs.append((href, clean[:120]))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for fid, label in pairs:
        if fid not in seen:
            seen.add(fid)
            unique.append((fid, label))
    return unique


def _looks_like_drive_file_id(session: str) -> bool:
    """A Google Drive file id is [A-Za-z0-9_-]+. Anything with a pipe,
    slash or whitespace is another provider's session shape (kusonime's
    "post|ep", anikato's tokens) and can never be a Drive file."""
    return bool(session) and re.fullmatch(r"[A-Za-z0-9_-]+", session) is not None


def _episode_key(filename: str) -> tuple[int, int] | None:
    """(season, episode) — the three observed shapes, in the map's order:
    `[Kayoanime] Show - NNN.mkv` → `- 274.mkv` trailing number (season 1,
    the default when the name carries no SxxExx),
    `[Kayoanime] Show - S02E05.mkv` → the season-episode form,
    movies (`- Movie 08 - Film.mkv`) → extras, no number.

    The key keeps the SEASON: a flat episode number collided across
    multi-season posts (Dandadan S1 and S2 both had "episode 5"), and the
    dedupe silently kept only one of them."""
    name = filename.rsplit("/", 1)[-1]
    se = re.search(r"\bS(\d{1,2})E(\d{1,3})\b", name, re.I)
    if se:
        return int(se.group(1)), int(se.group(2))
    if re.search(r"\bmovie\b", name, re.I):
        return None
    trailing = re.search(r"-\s*(\d{1,4})\s*\.(?:mkv|mp4)$", name, re.I)
    if trailing:
        return 1, int(trailing.group(1))
    loose = re.search(r"\b(\d{1,4})\s*\.(?:mkv|mp4)$", name, re.I)
    return int(loose.group(1)) if loose else None


def _extract_resolution(title: str) -> int:
    """The post title's resolution ("1080p"/"720p") — the folders hold
    exactly one quality per post."""
    m = re.search(r"(\d{3,4})p", title or "", re.I)
    return int(m.group(1)) if m else 0


class KayoanimeProvider:
    name = "kayoanime"
    capabilities = {
        "files": True,
        "episodes": True,
        "episode_stills": False,  # no per-episode stills exist — poster only
        "kwik_resolve": False,  # ready direct files
        "subtitles": False,  # dual-audio/sub tracks are inside the MKV
    }

    def __init__(self, client=None):
        self._client = client or primp.AsyncClient(
            impersonate="chrome", timeout=30.0, follow_redirects=True
        )
        self._mem: dict = {}
        self._ttl: dict = {}
        # post_id -> [(folderId, label)] — the resolved organization.
        self._folders: dict[str, list] = {}
        # file_id -> (episode num, filename, size) for the open post.
        self._files: dict[str, dict] = {}
        # post_id -> [(folderId, label)] the walk could NOT open.
        self._gated: dict[str, list] = {}
        # post_id -> resolution parsed from the post's title (never invented).
        self._quality: dict[str, int] = {}

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

    # ------------------------------------------------------------------
    # WordPress catalog
    # ------------------------------------------------------------------

    def _to_anime(self, post: dict) -> Anime:
        title, year, media_type = _clean_title(
            post.get("title", {}).get("rendered", "")
        )
        poster = self._poster(post)
        post_id = str(post.get("id") or "")
        return Anime(
            id=int(post.get("id") or 0),
            title=title,
            type=media_type,
            episodes=0,
            status="",
            season="",
            year=year,
            score=0.0,
            poster=poster,
            session=make_session("kayoanime", post_id),
        )

    @staticmethod
    def _poster(post: dict) -> str:
        """prefer the yoast og_image (present even with _fields), then the
        featured media record."""
        og = (post.get("yoast_head_json") or {}).get("og_image") or []
        if og and og[0].get("url"):
            return og[0]["url"]
        featured = post.get("featured_media")
        if isinstance(featured, dict):
            return featured.get("source_url", "")
        return ""

    # ------------------------------------------------------------------
    # Discovery — the WP category taxonomy (27 buckets, discovered at
    # runtime; the map documents them, we don't embed them)
    # ------------------------------------------------------------------

    async def filters(self) -> list[dict]:
        key = "filters"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        options: list[dict] = []
        try:
            resp = await self._client.get(
                f"{KAYOANIME_API}/categories",
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
            logger.debug("kayoanime categories failed: %s", ex)
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
                    {"value": "modified", "label": "Recently updated"},
                    {"value": "date", "label": "Newest"},
                    {"value": "title", "label": "Title"},
                ],
            }
        )
        self._cache_put(key, spec, CACHE_TTL_LATEST)
        return spec

    async def browse(self, filters: dict, page: int) -> tuple[list[Anime], bool]:
        params = {
            "per_page": "30",
            "page": str(page),
            "orderby": str(filters.get("orderby") or "modified"),
            "order": "desc",
            "_fields": "id,title,featured_media,modified,yoast_head_json",
        }
        if filters.get("categories"):
            params["categories"] = ",".join(str(c) for c in filters["categories"])
        resp = await self._client.get(f"{KAYOANIME_API}/posts", params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"kayoanime HTTP {resp.status_code}")
        posts = resp.json()
        result = ([self._to_anime(p) for p in posts], len(posts) >= 30)
        self._cache_put(
            f"browse_{filters.get('categories')}_{filters.get('orderby')}_{page}",
            result,
            CACHE_TTL_LATEST,
        )
        return result

    async def latest_releases(self, page: int) -> tuple[list[LatestRelease], bool]:
        key = f"latest_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KAYOANIME_API}/posts",
            params={
                "orderby": "modified",
                "order": "desc",
                "per_page": "30",
                "page": str(page),
                "_fields": "id,title,featured_media,modified,yoast_head_json",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"kayoanime HTTP {resp.status_code}")
        posts = resp.json()
        result = (
            releases_from_anime([self._to_anime(p) for p in posts]),
            len(posts) >= 30,
        )
        self._cache_put(key, result, CACHE_TTL_LATEST)
        return result

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:

        key = f"search_{query}_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KAYOANIME_API}/posts",
            params={
                "search": query,
                "per_page": "20",
                "page": str(page),
                "_fields": "id,title,featured_media,modified,yoast_head_json",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"kayoanime HTTP {resp.status_code}")
        posts = resp.json()
        scored = [
            (_title_relevance(query, a.title), a) for a in map(self._to_anime, posts)
        ]
        scored.sort(key=lambda sa: -sa[0])
        result = ([a for _, a in scored], len(posts) >= 20)
        self._cache_put(key, result, CACHE_TTL_SEARCH)
        return result

    async def anime(self, session: str) -> Anime | None:
        """Full post (with content) — poster, and the folder organization
        the episode flow needs."""
        _, post_id = split_session(session)
        if not post_id.isdigit():
            return None
        key = f"post_{post_id}"
        cached = self._cache_get(key)
        if cached is not None:
            # The cache holds the ANIME only — it used to hold the
            # (anime, folders) tuple, so the second call handed a tuple
            # to callers typed for Anime.
            return cached
        resp = await self._client.get(
            f"{KAYOANIME_API}/posts/{post_id}",
            params={"context": "view"},
        )
        if resp.status_code != 200:
            return None
        post = resp.json()
        anime = self._to_anime(post)
        content = (post.get("content") or {}).get("rendered", "")
        self._folders[post_id] = _folder_pairs(content)
        # The post title carries its one quality — the sources() path reads
        # this even when episodes() never ran (detail-then-play), so it is
        # populated here too, not only in _folders_for().
        self._quality[post_id] = _extract_resolution(
            post.get("title", {}).get("rendered", "")
        )
        self._cache_put(key, anime, CACHE_TTL_EPISODES)
        return anime

    async def probe(self) -> bool:
        try:
            resp = await self._client.get(
                f"{KAYOANIME_API}/posts",
                params={"per_page": "1", "_fields": "id"},
            )
            return resp.status_code == 200
        except Exception as ex:
            logger.debug("kayoanime probe failed: %s", ex)
            return False

    # ------------------------------------------------------------------
    # Google Drive layer (Step 2)
    # ------------------------------------------------------------------

    async def _list_folder(self, folder_id: str) -> list[dict]:
        """D1: the keyed listing. `files: []` + files.get 404 = restricted
        (Google-Group gated) — surfaced, never retried."""
        key = f"dir_{folder_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{DRIVE_API}/files",
            params={
                "q": f"'{folder_id}' in parents",
                "fields": "files(id,name,mimeType,size)",
                "pageSize": "1000",
                "key": DRIVE_WEB_KEY,
            },
            headers={"Referer": DRIVE_REFERER},
        )
        if resp.status_code != 200:
            return []
        files = [
            f
            for f in resp.json().get("files", [])
            if f.get("mimeType") != "application/vnd.google-apps.folder"
        ]
        self._cache_put(key, files, CACHE_TTL_EPISODES)
        return files

    async def _folders_for(self, post_id: str) -> list[tuple[str, str]]:
        cached = self._folders.get(post_id)
        if cached is not None:
            return cached
        resp = await self._client.get(
            f"{KAYOANIME_API}/posts/{post_id}", params={"context": "view"}
        )
        if resp.status_code != 200:
            return []
        post = resp.json()
        pairs = _folder_pairs((post.get("content") or {}).get("rendered", ""))
        self._folders[post_id] = pairs
        # the post title carries its one quality — carried, never assumed
        self._quality[post_id] = _extract_resolution(
            post.get("title", {}).get("rendered", "")
        )
        return pairs

    async def _is_restricted(self, folder_id: str) -> bool:
        """D2: an empty listing is ambiguous — confirm with files.get.
        404 means the Group-gated private folders; 200 means genuinely
        empty. Restricted folders are surfaced, never retried."""
        resp = await self._client.get(
            f"{DRIVE_API}/files/{folder_id}",
            params={"fields": "id,name,mimeType", "key": DRIVE_WEB_KEY},
            headers={"Referer": DRIVE_REFERER},
        )
        return resp.status_code == 404

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        _, post_id = split_session(session)
        if not post_id.isdigit():
            return ([], False)
        key = f"episodes_{post_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        folders = await self._folders_for(post_id)
        if not folders:
            # href="#" / zero folder ids = links under maintenance.
            return ([], False)
        # Walk every folder, collect (episode -> file), dedupe by number —
        # boxes overlap (Box 8 duplicates 6/7's range) and the larger file
        # is the complete copy. BOX labels are BATCH volumes, not seasons,
        # so they name a folder in the gated report rather than splitting
        # the episode list.
        by_episode: dict[tuple[int, int], dict] = {}
        restricted_folders: list[tuple[str, str]] = []
        for folder_id, label in folders:
            # One folder's transport error must not abort the whole walk
            # (it used to: the exception propagated out of episodes()).
            try:
                files = await self._list_folder(folder_id)
                if not files:
                    if await self._is_restricted(folder_id):
                        restricted_folders.append((folder_id, label))
                    continue
            except Exception as ex:
                logger.warning(
                    "kayoanime folder %s (%s) failed: %s", folder_id, label, ex
                )
                continue
            for f in files:
                ep_key = _episode_key(f.get("name", ""))
                if ep_key is None:
                    continue
                try:
                    size = int(f.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                if size and size < _MIN_EPISODE_BYTES:
                    continue
                prev = by_episode.get(ep_key)
                if prev is None or size > prev.get("size", 0):
                    by_episode[ep_key] = {
                        "file_id": f["id"],
                        "name": f.get("name", ""),
                        "size": size,
                    }
        self._files[post_id] = by_episode
        self._gated[post_id] = [
            (folder_id, label) for folder_id, label in restricted_folders
        ]
        results = [
            Episode(
                id=i,
                anime_id=int(post_id or 0),
                episode=key[1],
                title=f"Episode {key[1]}",
                snapshot="",
                disc="",
                audio="jpn",
                duration="",
                session=info["file_id"],  # the Drive file id IS the session
                filler=False,
            )
            for i, (key, info) in enumerate(sorted(by_episode.items()), start=1)
        ]
        result = (results, False)
        self._cache_put(key, result, CACHE_TTL_EPISODES)
        if self._gated[post_id]:
            # Group-gated folders are a silent gap in the episode list, so
            # they are named here (the settings health panel shows them)
            # instead of disappearing into a log line.
            logger.warning(
                "kayoanime post %s: Group-gated folders: %s",
                post_id,
                ", ".join(
                    f"{label or folder_id}" for folder_id, label in self._gated[post_id]
                ),
            )
        return result

    def gated_folders(self, anime_session: str) -> list[str]:
        """Folder labels this post's episode walk could not open. Empty
        unless episodes() ran and found some."""
        _, post_id = split_session(anime_session)
        return [label or folder_id for folder_id, label in self._gated.get(post_id, [])]

    def file_name(self, anime_session: str, episode_session: str) -> str | None:
        """The Drive file's real name for an episode — carried into the
        download so the saved copy keeps what the source called it."""
        _, post_id = split_session(anime_session)
        for row in (self._files.get(post_id) or {}).values():
            if row.get("file_id") == episode_session:
                return row.get("name") or None
        return None

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        """The episode's direct file on the two routes the map verified:
        keyed alt=media (206 with seek incl. tail) and the keyless
        usercontent download route (206, real filename — the download
        route). The file id IS the episode session."""
        if not _looks_like_drive_file_id(episode_session):
            # A session from another provider (namespaced "post|ep" shapes,
            # anything with a pipe or separators) is NOT a Drive file id.
            # Building /files/<junk> produced a stream that 404'd — and
            # because these URLs were returned UNVALIDATED, they used to
            # WON the router race over the real owner (flet run log,
            # 2026-10-15: kusonime's "48025|1" played as a Drive 404).
            # Empty is the honest answer; the owner gets the call.
            return []
        keyed = f"{DRIVE_API}/files/{episode_session}?alt=media&key={DRIVE_WEB_KEY}"
        keyless = (
            f"https://drive.usercontent.google.com/download"
            f"?id={episode_session}&export=download&confirm=t"
        )
        # One-per-post quality from the post's title; 0 only when unknown.
        _, post_id = split_session(anime_session)
        resolution = self._quality.get(post_id, 0)
        return [
            Source(
                url=keyed,
                resolution=resolution,
                audio="jpn",
                fansub="Kayoanime",
                headers={"Referer": DRIVE_REFERER},
            ),
            Source(
                url=keyless,
                resolution=resolution,
                audio="jpn",
                fansub="Kayoanime",
                headers={"Referer": DRIVE_REFERER},
            ),
        ]

    async def episodes_for_title(self, title: str) -> list[Episode]:
        results, _ = await self.search(title, 1)
        best = max(
            results, key=lambda a: _title_relevance(title, a.title), default=None
        )
        if best is None or _title_relevance(title, best.title) == 0:
            return []
        episodes, _ = await self.episodes(best.session, 1)
        return episodes

    async def sources_for_title(self, title: str, episode: int) -> list[Source]:
        results, _ = await self.search(title, 1)
        best = max(
            results, key=lambda a: _title_relevance(title, a.title), default=None
        )
        if best is None or _title_relevance(title, best.title) == 0:
            return []
        episodes, _ = await self.episodes(best.session, 1)
        # The episode session is the Drive file id — resolve it directly.
        ep = next((e for e in episodes if e.episode == episode), None)
        return await self.sources(best.session, ep.session) if ep else []

    async def close(self) -> None:
        # pass used to leak the pooled client; close_client releases a real
        # primp client (and tolerates the aclose-only test fakes).
        await close_client(self._client)
