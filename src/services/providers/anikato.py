"""AniKato provider — the modern JSON+SSR way, complete.

Self-contained (title in, catalog/episodes/files out) over anikototv.to:

- Catalog: server-rendered search/new-release pages (plain HTML).
- Episodes: the site's AJAX list, unlocked by its own VRF scheme —
  ``base64(RC4("simple-hash", id))`` with the key hardcoded in the site's
  public JS (services/aes.py's sibling trick: a fixed transform, not a
  moving target). Verified live in Phase 0.
- Files: per-episode SUB and DUB servers resolve to MegaPlay embed URLs;
  MegaPlay's ``getSources`` returns an AES-256-CBC ``enc`` token whose
  plaintext is the manifest URL — decrypted with the keys hardcoded in
  MegaPlay's own public JS. Result: DIRECT playable m3u8 URLs (verified
  #EXTM3U VOD) with per-source headers (Referer megaplay.buzz) and skip
  data. primp's Chrome impersonation is the HTTP edge throughout.
"""

import base64
import json
import logging
import re
import time

import primp

from core.config import CACHE_TTL_EPISODES, CACHE_TTL_LATEST, CACHE_TTL_SEARCH
from core.state import Anime, Episode, Source
from services.aes import aes_cbc_decrypt
from services.providers.base import make_session, split_session

logger = logging.getLogger("animepahe.provider.anikato")

BASE = "https://anikototv.to"
MEGAPLAY = "https://megaplay.buzz"
MEGAPLAY_REFERER = "https://megaplay.buzz/"

# MegaPlay's own public JS ships these constants (newclient.min.js).
_AES_KEY = b"i?LMTAx0Q6,:}50U".ljust(32, b"\x00")
_AES_IV = b"W0;27ToaUpl_P%'c"


def _vrf(value) -> str:
    """The site's VRF: base64(RC4("simple-hash", str(value)))."""
    return base64.b64encode(_rc4("simple-hash", str(value).encode())).decode()


def _rc4(key: str, data: bytes) -> bytes:
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + ord(key[i % len(key)])) % 256
        S[i], S[j] = S[j], S[i]
    out = bytearray()
    i = j = 0
    for b in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) % 256])
    return bytes(out)


# ----------------------------------------------------------------------
# Pure parsers (fixture-tested, no I/O)
# ----------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def _parse_items(html: str) -> list[Anime]:
    """Catalog items: #list-items > .item blocks (search and new-release
    share the structure). Every field is best-effort — a missing field is
    empty, never a crash, and nothing is filtered."""
    results: list[Anime] = []
    blocks = re.split(r'<div class="item(?:\s[^"]*)?">', html)[1:]
    for block in blocks:
        slug_m = re.search(r'href="[^"]*?/watch/([a-z0-9\-]+)', block)
        if not slug_m:
            continue
        slug = slug_m.group(1)
        title_m = re.search(r'class="name d-title"[^>]*>([^<]+)<', block)
        title = _clean(title_m.group(1)) if title_m else ""
        if not title:
            continue
        poster_m = re.search(r'<img src="([^"]+)"', block)
        id_m = re.search(r'class="ani poster tip" data-tip="(\d+)"', block)
        sub_m = re.search(r'ep-status sub"><span>\s*(\d+)', block)
        type_m = re.search(r'<div class="right">([^<]+)</div>', block)
        score_m = re.search(r'm-item rated[^>]*>\s*<span>\s*([\d.]+)', block)
        results.append(
            Anime(
                id=int(id_m.group(1)) if id_m else 0,
                title=title[:200],
                type=_clean(type_m.group(1)) if type_m else "TV",
                episodes=int(sub_m.group(1)) if sub_m else 0,
                status="",
                season="",
                year=0,
                score=round(float(score_m.group(1)), 1) if score_m else 0.0,
                poster=poster_m.group(1) if poster_m else "",
                session=make_session("anikato", slug),
            )
        )
    return results


def _parse_watch(html: str) -> dict:
    """The watch page: anime id (drives the VRF episode list) + metadata.
    The id sits on #watch-main with other attributes between, so scope
    the search after the marker."""
    watch_pos = html.find('id="watch-main"')
    scope = html[watch_pos : watch_pos + 600] if watch_pos >= 0 else html
    id_m = re.search(r'data-id="(\d+)"', scope)
    poster_m = re.search(r'img itemprop="image" src="([^"]+)"', html)
    title_m = re.search(r'itemprop="name"[^>]*>([^<]+)<', html)
    synopsis_m = re.search(r'class="synopsis[^"]*">\s*<div class="content">\s*(.*?)</div>', html, re.S)
    return {
        "anime_id": int(id_m.group(1)) if id_m else 0,
        "poster": poster_m.group(1) if poster_m else "",
        "title": _clean(title_m.group(1)) if title_m else "",
        "synopsis": _clean(synopsis_m.group(1))[:800] if synopsis_m else "",
    }


def _parse_episode_list(html: str) -> list[tuple[int, str]]:
    """Episode entries: data-num + data-ids (the server-list key)."""
    entries: list[tuple[int, str]] = []
    for m in re.finditer(r'data-num="(\d+)"[^>]*data-ids="([^"]+)"', html):
        entries.append((int(m.group(1)), m.group(2)))
    # Some layouts order the attributes the other way around.
    for m in re.finditer(r'data-ids="([^"]+)"[^>]*data-num="(\d+)"', html):
        entry = (int(m.group(2)), m.group(1))
        if entry not in entries:
            entries.append(entry)
    entries.sort(key=lambda e: e[0])
    return entries


def _parse_servers(html: str) -> list[tuple[str, str]]:
    """Server groups: (type 'sub'|'dub', link-id) — both groups, nothing
    dropped."""
    groups = re.split(r'<div class="type" data-type="', html)[1:]
    servers: list[tuple[str, str]] = []
    for group in groups:
        type_m = re.match(r'(sub|dub)"', group)
        if not type_m:
            continue
        for link_id in re.findall(r'data-link-id="([^"]+)"', group):
            servers.append((type_m.group(1), link_id))
    return servers


def _megaplay_params(url: str) -> tuple[str, str, str] | None:
    """https://megaplay.buzz/[videojs/]stream/s-2/{realid}/{sub|dub}?s=tcdn
    -> (realid, type, s)."""
    m = re.search(r"/stream/(?:s-\d+/)?(\d+)/(sub|dub)(?:\?(.*))?$", url)
    if not m:
        return None
    query = m.group(3) or ""
    s_m = re.search(r"s=([^&]+)", query)
    return m.group(1), m.group(2), (s_m.group(1) if s_m else "")


def _decrypt_manifest(enc: str) -> str:
    """getSources' enc token -> the manifest URL."""
    raw = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4))
    plain = aes_cbc_decrypt(_AES_KEY, _AES_IV, raw)
    try:
        return str(json.loads(plain).get("file") or "")
    except Exception:
        m = re.search(r"https?://[^\s\"']+", plain.decode("utf-8", "ignore"))
        return m.group(0) if m else ""


# ----------------------------------------------------------------------
# The provider
# ----------------------------------------------------------------------

class AniKatoProvider:
    name = "anikato"
    capabilities = {
        "files": True,
        "episodes": True,
        "episode_stills": True,
        "kwik_resolve": False,  # its source URLs are ready m3u8s
    }

    def __init__(self, client=None):
        self._client = client or primp.AsyncClient(
            impersonate="chrome", timeout=20.0, follow_redirects=True
        )
        self._mem: dict = {}
        self._ttl: dict = {}

    def _cache_get(self, key: str):
        item = self._mem.get(key)
        if item is not None and time.time() < self._ttl.get(key, 0):
            return item
        self._mem.pop(key, None)
        return None

    def _cache_put(self, key: str, value, ttl: int) -> None:
        self._mem[key] = value
        self._ttl[key] = time.time() + ttl

    async def _get_text(self, url: str, xhr: bool = False) -> str:
        headers = {}
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Referer"] = f"{BASE}/"
        resp = await self._client.get(url, headers=headers or None)
        if resp.status_code != 200:
            raise RuntimeError(f"anikato HTTP {resp.status_code} for {url}")
        return resp.text

    async def probe(self) -> bool:
        try:
            html = await self._get_text(f"{BASE}/home")
            return "just a moment" not in html.lower() and len(html) > 5000
        except Exception as ex:
            logger.debug("anikato probe failed: %s", ex)
            return False

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    async def latest_releases(self, page: int) -> tuple[list[Anime], bool]:
        key = f"latest_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = await self._get_text(f"{BASE}/new-release?page={page}")
        items = _parse_items(html)
        result = (items, len(items) >= 20)
        self._cache_put(key, result, CACHE_TTL_LATEST)
        return result

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:
        key = f"search_{query}_{page}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        from urllib.parse import quote

        html = await self._get_text(f"{BASE}/filter?keyword={quote(query)}&page={page}")
        items = _parse_items(html)
        result = (items, len(items) >= 20)
        self._cache_put(key, result, CACHE_TTL_SEARCH)
        return result

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    async def _watch_page(self, slug: str) -> dict:
        key = f"watch_{slug}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = await self._get_text(f"{BASE}/watch/{slug}")
        data = _parse_watch(html)
        if not data["anime_id"]:
            raise RuntimeError(f"anikato: no anime id on watch page {slug}")
        self._cache_put(key, data, CACHE_TTL_EPISODES)
        return data

    async def _episode_entries(self, anime_id: int) -> list[tuple[int, str]]:
        key = f"eplist_{anime_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = await self._get_text(
            f"{BASE}/ajax/episode/list/{anime_id}?style=list&vrf={_vrf(anime_id)}",
            xhr=True,
        )
        data = json.loads(html)
        if data.get("status") != 200:
            raise RuntimeError(f"anikato episode list: {data.get('result')}")
        entries = _parse_episode_list(data.get("result") or "")
        self._cache_put(key, entries, CACHE_TTL_EPISODES)
        return entries

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        _, slug = split_session(session)
        if not slug:
            return ([], False)
        key = f"episodes_{slug}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        watch = await self._watch_page(slug)
        entries = await self._episode_entries(watch["anime_id"])
        poster = watch["poster"]
        results = [
            Episode(
                id=num,
                anime_id=watch["anime_id"],
                episode=num,
                title=f"Episode {num}",
                snapshot=poster,
                disc="",
                audio="",
                duration="",
                session=f"{slug}|{num}",  # sources() resolves this server-side
                filler=False,
            )
            for num, _ids in entries
        ]
        result = (results, False)
        self._cache_put(key, result, CACHE_TTL_EPISODES)
        return result

    # ------------------------------------------------------------------
    # Files: episode entries -> servers -> megaplay getSources -> m3u8
    # ------------------------------------------------------------------

    async def _server_links(self, ids_token: str) -> list[tuple[str, str]]:
        key = f"servers_{ids_token[:40]}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = await self._get_text(f"{BASE}/ajax/server/list?servers={ids_token}", xhr=True)
        data = json.loads(html)
        if data.get("status") != 200:
            raise RuntimeError(f"anikato server list: {data.get('result')}")
        servers = _parse_servers(data.get("result") or "")
        self._cache_put(key, servers, CACHE_TTL_EPISODES)
        return servers

    async def _resolve_link(self, link_id: str) -> tuple[str, str, str] | None:
        """link-id -> megaplay embed -> (realid, type, s)."""
        key = f"link_{link_id[:40]}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = await self._get_text(f"{BASE}/ajax/server?get={link_id}", xhr=True)
        data = json.loads(html)
        if data.get("status") != 200:
            return None
        url = str((data.get("result") or {}).get("url") or "")
        params = _megaplay_params(url) if url else None
        if params:
            self._cache_put(key, params, CACHE_TTL_EPISODES)
        return params

    async def _manifest_for(self, realid: str, kind: str, s: str) -> str:
        key = f"manifest_{realid}_{kind}_{s}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        from urllib.parse import quote

        url = f"{MEGAPLAY}/stream/getSources?id={quote(realid)}&type={quote(kind)}"
        if s:
            url += f"&s={quote(s)}"
        resp = await self._client.get(
            url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": MEGAPLAY_REFERER,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"megaplay getSources HTTP {resp.status_code}")
        enc = str(resp.json().get("enc") or "")
        if not enc:
            raise RuntimeError("megaplay getSources: empty enc")
        manifest = _decrypt_manifest(enc)
        if manifest:
            self._cache_put(key, manifest, CACHE_TTL_EPISODES)
        return manifest

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        _, slug = split_session(anime_session)
        _, _, num_s = episode_session.rpartition("|")
        if not slug or not num_s.isdigit():
            return []
        num = int(num_s)
        watch = await self._watch_page(slug)
        entries = await self._episode_entries(watch["anime_id"])
        ids_token = next((ids for n, ids in entries if n == num), "")
        if not ids_token:
            return []  # genuinely no servers for this episode — a result
        servers = await self._server_links(ids_token)
        results: list[Source] = []
        for kind, link_id in servers:
            params = await self._resolve_link(link_id)
            if not params:
                continue
            realid, megaplay_kind, s = params
            try:
                manifest = await self._manifest_for(realid, megaplay_kind, s)
            except Exception as ex:
                logger.info("anikato manifest failed (%s/%s): %s", realid, megaplay_kind, ex)
                continue
            if not manifest:
                continue
            results.append(
                Source(
                    url=manifest,
                    resolution=0,  # master playlist — variants parsed at play
                    audio="eng" if kind == "dub" else "jpn",
                    fansub="AniKato",
                    headers={"Referer": MEGAPLAY_REFERER},
                )
            )
        return results

    async def episodes_for_title(self, title: str) -> list[Episode]:
        results, _ = await self.search(title, 1)
        for anime in results:
            if anime.title.lower() == title.lower():
                episodes, _ = await self.episodes(anime.session, 1)
                return episodes
        return []

    async def sources_for_title(self, title: str, episode: int) -> list[Source]:
        results, _ = await self.search(title, 1)
        for anime in results:
            if anime.title.lower() == title.lower():
                return await self.sources(anime.session, f"{anime.id}|{episode}")
        return []

    async def close(self) -> None:
        pass
