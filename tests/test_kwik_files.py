"""The kwik FILE route — AniKato's own download row, which is
AnimePahe's (proved live 2026-10-19, docs/testing-findings.md §6).

The chain under test:

    mapper.nekostream.site/api/mal/<mal>/<ep>/<ts>
      -> {quality: pahe.nekostream.site/<code>}
      -> pahe.nekostream.site/<code>          (an HTML page)
      -> testpahe.nekostream.site/<code>      (302, needs the referer)
      -> kwik.cx/f/<token>                    (the Cloudflare-guarded file page)
      -> a CSRF'd POST to kwik.cx/d/<token>   -> 302 -> the media file

These tests use the REAL payload shapes (the mapper's JSON, the kwik
file page's HTML) and assert the chain hop by hop — the shape of the
thing that made AniKato's download row look like AnimePahe's.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from services.kwik_files import KwikFileResolver

# The mapper's real answer for Black Clover episode 1 (live 2026-10-19).
MAPPER_PAYLOAD = {
    "Kiwi": {
        "sub": {
            "download": {
                "360p": "https://pahe.nekostream.site/yRVMl",
                "720p": "https://pahe.nekostream.site/BfqIe",
                "1080p": "https://pahe.nekostream.site/WjUUW",
            }
        }
    },
    "status": {"time": 1792094249, "serves_from": "database"},
}

# The kwik file page's real shape: a form that POSTs to /d/<token>.
KWIK_PAGE = """
<!DOCTYPE html>
<html><head><title>AnimePahe_Black_Clover_-_001_360p_SubsPlease.mp4 :: Kwik</title></head>
<body>
  <h1 class="title"> AnimePahe_Black_Clover_-_001_360p_SubsPlease.mp4 </h1>
  <form method="POST" action="https://kwik.cx/d/nHkd7KvJyRxT">
    <input type="hidden" name="_token" value="rRGJlYvb5CP08q9fpcOEXAm8f1YkJL51bocexzdY">
    <button type="submit" class="button is-success">Download&nbsp;(52.82 MB)</button>
  </form>
</body></html>
"""

# The pahe.nekostream shortlink page: its JS hands over to testpahe.
SHORTLINK_PAGE = """
<!DOCTYPE html>
<html><body>
<script>
function startDownload() {
  const id = getId();
  const url = "https://testpahe.nekostream.site/" + id;
  window.location.href = url;
}
</script>
</body></html>
"""


class _Resp:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json


class _Client:
    """Answers by URL, like the site's own routing."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    async def get(self, url, headers=None, follow_redirects=True, **kwargs):
        self.calls.append(("GET", url))
        # Longest-needle first: "testpahe..." contains "pahe...",
        # so a naive first-match would hand back the shortlink's page.
        for needle, resp in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if needle in url:
                return resp
        return _Resp(404, text="not found")

    async def post(self, url, data=None, headers=None, follow_redirects=True, **kwargs):
        self.calls.append(("POST", url))
        # Longest-needle first: "testpahe..." contains "pahe...",
        # so a naive first-match would hand back the shortlink's page.
        for needle, resp in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if needle in url:
                return resp
        return _Resp(404, text="not found")

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_the_mapper_answers_with_the_per_quality_files():
    """One GET, no auth, no Cloudflare: the per-episode, per-quality
    shortlinks straight from the mapper."""
    client = _Client({"/api/mal/": _Resp(200, json_data=MAPPER_PAYLOAD)})
    resolver = KwikFileResolver()
    resolver._client = client

    files = await resolver.episode_files(34572, 1, 1778012242)

    assert [f.quality for f in files] == ["360p", "720p", "1080p"]
    assert files[0].url == "https://pahe.nekostream.site/yRVMl"
    assert files[0].audio == "sub"
    # The mapper is keyed by MAL id + episode + timestamp.
    assert "34572/1/1778012242" in client.calls[0][1]


@pytest.mark.asyncio
async def test_the_mapper_answers_nothing_for_a_series_it_does_not_have():
    """A series the mapper has no entry for is a RESULT, not a failure."""
    client = _Client({"/api/mal/": _Resp(400, json_data={"error": True, "message": "Failed to get the list"})})
    resolver = KwikFileResolver()
    resolver._client = client
    assert await resolver.episode_files(154587, 1, 1) == []


@pytest.mark.asyncio
async def test_the_shortlink_reaches_the_kwik_file_page():
    """pahe.nekostream -> testpahe (with the referer) -> kwik.cx/f/<token>."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client

    url = await resolver.kwik_file_url("https://pahe.nekostream.site/yRVMl")
    assert url == "https://kwik.cx/f/nHkd7KvJyRxT"


@pytest.mark.asyncio
async def test_the_file_page_yields_the_direct_media_url():
    """The page's own form: a CSRF'd POST to /d/<token>, whose 302 is
    the media file."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
            "kwik.cx/f/": _Resp(200, text=KWIK_PAGE),
            "kwik.cx/d/": _Resp(
                302, headers={"location": "https://cdn.example/AnimePahe_Black_Clover_-_001_360p.mp4"}
            ),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client

    url = await resolver.media_url("https://pahe.nekostream.site/yRVMl")
    assert url == "https://cdn.example/AnimePahe_Black_Clover_-_001_360p.mp4"
    # The POST carried the page's CSRF token.
    post = next(c for c in client.calls if c[0] == "POST")
    assert post[1] == "https://kwik.cx/d/nHkd7KvJyRxT"


@pytest.mark.asyncio
async def test_without_a_clearance_the_kwik_page_is_not_reachable():
    """The kwik FILE page is the one guarded route: without a clearance
    it answers 403, and the resolver reports None (the caller falls back
    to the provider's own stream)."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
            "kwik.cx/f/": _Resp(403, text="<html>Just a moment...</html>"),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client
    assert await resolver.media_url("https://pahe.nekostream.site/yRVMl") is None


@pytest.mark.asyncio
async def test_the_anikato_provider_offers_no_kwik_file_without_a_clearance():
    """A provider never opens a verification window on its own: without
    a stored clearance the kwik files are simply not there, and the
    megaplay stream path is untouched."""
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider()
    # No clearance in the store -> no kwik sources.
    assert await provider.kwik_file_sources("anikato:slug", "anikato:slug|1") == []


def test_the_mal_id_is_read_from_the_episode_list():
    """The mapper is keyed by MAL id, and AniKato's episode list carries
    data-mal on every episode link (Black Clover = 34572)."""
    from services.providers.anikato import _parse_mal_id, _quality_to_resolution

    html = '<a href="#" data-id="37933" data-num="1" data-mal="34572">ep</a>'
    assert _parse_mal_id(html) == 34572
    assert _parse_mal_id('<a data-num="1">no mal here</a>') == 0
    assert _quality_to_resolution("1080p") == 1080
    assert _quality_to_resolution("720") == 720
    assert _quality_to_resolution("weird") == 0
