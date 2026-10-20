"""The AnimePahe FILE route on kwik — the one AniKato's own download row
uses, and the one the owner asked for ("the download part kwik").

THE CHAIN (proved live 2026-10-19 with the app's own anime, Black
Clover; the full evidence is in docs/testing-findings.md §6):

    the site's own script (anikoto/js/mapper.js)
      -> https://mapper.nekostream.site/api/mal/<mal>/<episode>/<timestamp>
      -> {"Kiwi": {"sub": {"download": {"360p": "https://pahe.nekostream.site/<code>",
                                        "720p": "...",
                                        "1080p": "..."}}}}
      -> pahe.nekostream.site/<code>          (an HTML page; its JS hands over)
      -> testpahe.nekostream.site/<code>      (302 — needs the pahe.nekostream referer)
      -> https://kwik.cx/f/<token>             (the kwik FILE page)
      -> the page's own form: a CSRF'd POST to https://kwik.cx/d/<token>
      -> 302 -> the media file

Two facts that decide how this is wired:

* "Kiwi" IS AnimePahe. The mapper's own normalizer maps
  ``kiwi-stream`` -> ``animepahe`` -> the label ``Kiwi-Stream``, and the
  file it returns is an AnimePahe file (the mapper hands out the same
  ``pahe.win/<code>`` link AnimePahe's own ``m=links`` payload carries
  as ``kwik_pahewin``). The mapper is MAL-keyed and source-agnostic —
  it answers for series AniKato does not even list.

* The kwik routes are not equally walled (live probes, primp chrome
  impersonation): the landing page is 200, the ``/e/`` STREAM page is NOT
  challenged (that is what AnimePahe streams through, and it needs no
  clearance), but the ``/f/`` FILE page IS challenged
  (``403 cf-mitigated: challenge``; it clears in a real browser and the
  clearance then persists). The ``/d/`` download endpoint is not
  challenged at all — it answers ``419 Page Expired`` (Laravel's CSRF
  check) with no Cloudflare involved.

So the FILE route needs one Cloudflare clearance on kwik.cx, exactly the
mechanism the app already ships for AnimePahe — on a different host, and
the store already keeps a clearance PER HOST.
"""

from __future__ import annotations

import logging
import re

import primp

logger = logging.getLogger(__name__)

__all__ = ["KwikFile", "KwikFileResolver"]

# The mapper's per-episode endpoint (the same one the site's own script
# calls).
MAPPER_API = "https://mapper.nekostream.site/api/mal/{mal}/{episode}/{timestamp}"

# The kwik host that serves the files today (2026-10-19: kwik.cx is the
# only live one — kwik.si is a parked domain, kwik.pw/to/la/icu are
# DNS-dead).
KWIK_HOST = "kwik.cx"

# The kwik file page's form: <form action="https://kwik.cx/d/<token>">
# with a hidden _token (Laravel's CSRF token) inside.
_FORM_ACTION = re.compile(r'action="([^"]*/d/[^"]+)"')
_FORM_TOKEN = re.compile(r'name="_token"\s+value="([^"]+)"')


class KwikFile:
    """One downloadable rendition: a quality label and the URL of the
    shortlink that leads to the file."""

    __slots__ = ("audio", "quality", "url")

    def __init__(self, quality: str, url: str, audio: str = "sub"):
        self.quality = quality
        self.url = url
        self.audio = audio

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"KwikFile({self.quality!r}, {self.audio!r}, {self.url!r})"


class KwikFileResolver:
    """Resolve an AnimePahe file (the kwik ``/f/`` route) to a direct
    media URL.

    ``clearance`` is the ``(cookies, user_agent)`` pair for kwik.cx — the
    host-keyed clearance the store keeps. ``solve`` is an optional
    async callable that opens the verification window; it is the
    CALLER's decision whether that is allowed (a verification window is
    a deliberate, user-visible act), so this service never opens one on
    its own.
    """

    def __init__(self, clearance: tuple[str, str] | None = None, solve=None):
        self._clearance = clearance
        self._solve = solve
        self._client: primp.AsyncClient | None = None

    def _get_client(self) -> primp.AsyncClient:
        if self._client is None:
            self._client = primp.AsyncClient(timeout=20, impersonate="chrome")
        return self._client

    def set_clearance(self, cookies: str, user_agent: str) -> None:
        """Adopt a clearance (the caller solved it)."""
        self._clearance = (cookies, user_agent)

    def _headers(self, referer: str) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
        }
        if self._clearance:
            cookies, ua = self._clearance
            if cookies:
                headers["Cookie"] = cookies
            if ua:
                headers["User-Agent"] = ua
        return headers

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    # ------------------------------------------------------------------
    # 1. The mapper: the per-episode, per-quality shortlinks
    # ------------------------------------------------------------------
    async def episode_files(
        self, mal_id: int, episode: int, timestamp: int | str
    ) -> list[KwikFile]:
        """The downloadable renditions of one episode, straight from the
        mapper (no auth, no Cloudflare, one GET).

        Returns an empty list when the mapper has no entry for the
        series — a result, not a failure.
        """
        url = MAPPER_API.format(
            mal=mal_id, episode=episode, timestamp=timestamp
        )
        try:
            resp = await self._get_client().get(
                url, headers={"Referer": "https://anikototv.to/"}
            )
        except Exception as ex:
            logger.info("kwik files: mapper request failed: %s", ex)
            return []
        if resp.status_code != 200:
            logger.info("kwik files: mapper HTTP %s", resp.status_code)
            return []
        try:
            payload = resp.json()
        except Exception:
            logger.info("kwik files: mapper answered with non-JSON")
            return []
        if not isinstance(payload, dict) or payload.get("error"):
            return []

        files: list[KwikFile] = []
        for source_name, source in payload.items():
            if source_name == "status" or not isinstance(source, dict):
                continue
            for audio, body in source.items():
                if not isinstance(body, dict):
                    continue
                download = body.get("download")
                if not isinstance(download, dict):
                    continue
                for quality, link in download.items():
                    if not link:
                        continue
                    files.append(KwikFile(str(quality), str(link), str(audio)))
        return files

    # ------------------------------------------------------------------
    # 2. The shortlink -> the kwik file page
    # ------------------------------------------------------------------
    async def kwik_file_url(self, shortlink: str) -> str | None:
        """The kwik ``/f/`` page behind a shortlink, or None.

        Two hops: the pahe.nekostream page (whose JS names the
        testpahe host) and then the testpahe redirect, which needs the
        pahe.nekostream referer or it answers 403.
        """
        code = shortlink.rstrip("/").rsplit("/", 1)[-1]
        if not code:
            return None
        client = self._get_client()
        try:
            page = await client.get(shortlink, headers=self._headers("https://anikototv.to/"))
        except Exception as ex:
            logger.info("kwik files: shortlink fetch failed: %s", ex)
            return None
        if page.status_code != 200:
            logger.info("kwik files: shortlink HTTP %s", page.status_code)
            return None
        body = page.text or ""
        hop = "https://testpahe.nekostream.site/" + code
        if "testpahe.nekostream.site" in body:
            match = re.search(r"https://testpahe\.nekostream\.site/[^\"'\s<]+", body)
            # The page builds the URL by concatenation, so a regex
            # captures only the prefix; only use it when it carries a code.
            if match and match.group(0).rstrip('/') != 'https://testpahe.nekostream.site':
                hop = match.group(0)
        try:
            resp = await client.get(
                hop,
                headers=self._headers("https://pahe.nekostream.site/"),
                follow_redirects=False,
            )
        except Exception as ex:
            logger.info("kwik files: testpahe fetch failed: %s", ex)
            return None
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location") or ""
            if location.startswith("/"):
                location = f"https://testpahe.nekostream.site{location}"
            return location or None
        logger.info("kwik files: testpahe answered %s", resp.status_code)
        return None

    # ------------------------------------------------------------------
    # 3. The kwik file page -> the direct media URL
    # ------------------------------------------------------------------
    async def media_url(self, shortlink: str) -> str | None:
        """The direct media URL behind a shortlink.

        The kwik file page holds a CSRF'd form; POSTing it answers a
        302 to the file itself. The page needs a kwik.cx clearance, so
        without one this returns None and the caller falls back to the
        provider's own stream.
        """
        file_url = await self.kwik_file_url(shortlink)
        if not file_url:
            return None
        client = self._get_client()
        try:
            page = await client.get(file_url, headers=self._headers(f"https://{KWIK_HOST}/"))
        except Exception as ex:
            logger.info("kwik files: page fetch failed: %s", ex)
            return None
        if page.status_code != 200:
            logger.info("kwik files: the kwik page answered %s", page.status_code)
            return None
        body = page.text or ""
        action = _FORM_ACTION.search(body)
        token = _FORM_TOKEN.search(body)
        if not action or not token:
            logger.info("kwik files: the kwik page carried no download form")
            return None
        try:
            resp = await client.post(
                action.group(1).replace("&amp;", "&"),
                data={"_token": token.group(1)},
                headers=self._headers(file_url),
                follow_redirects=False,
            )
        except Exception as ex:
            logger.info("kwik files: the download POST failed: %s", ex)
            return None
        if resp.status_code in (301, 302, 303, 307, 308):
            return resp.headers.get("location") or None
        logger.info("kwik files: the download POST answered %s", resp.status_code)
        return None
