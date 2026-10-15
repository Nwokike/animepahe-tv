"""The image route — Phase 3 Step 4.

The owner's web run showed zero images: the browser refuses every
cross-origin image URL (no CORS headers on the art hosts), and AnimeOut's
host answers a Cloudflare "Just a moment" 403 to anything but a browser
session (live probe 2026-10-15: anikato/kusonime/kayoanime CDNs are 200
bare and with referer; www.animeout.xyz 403s either way). The loopback
proxy's GET /image (b64 url + referer, content-type forward, 8 MB cap, mem
cache, ACAO) is the one path that fixes CORS everywhere and can ever carry
headers/clearance for a guarded host.

The wrap happens at the DISPLAY edge (`image_url()`), never on provider
data — so nothing persisted can ever carry a loopback port.
"""

import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from components.artwork_card import card_media  # noqa: E402
from components.result_card import result_card  # noqa: E402
from core.artwork import PORTRAIT, PROBE_REFERERS  # noqa: E402
from core.state import Anime  # noqa: E402
from services.hls_proxy import (  # noqa: E402
    MAX_IMAGE_BYTES,
    HLSProxy,
    _b64_decode,
    image_url,
    set_display_context,
)

BASE = "http://127.0.0.1:9999"


@pytest.fixture(autouse=True)
def _clean_ctx():
    """The display context is process-wide — never leak it into other tests."""
    yield
    set_display_context(None, False)


def _payload(src: str) -> tuple[str, str]:
    """(url, referer) decoded out of a wrapped /image src."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(src).query)
    return _b64_decode(q["url"][0]), _b64_decode(q["referer"][0]) if q.get("referer") else ""


# ---------------------------------------------------------------------------
# image_url() — the display decision
# ---------------------------------------------------------------------------


def test_passthrough_when_no_context_or_no_wrap_needed():
    set_display_context(None, False)
    assert image_url("http://cdn/x.jpg") == "http://cdn/x.jpg"
    assert image_url("") == ""
    assert image_url("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"
    set_display_context(BASE, False)
    # Native + a plain host: raw (nothing to fix).
    assert image_url("http://cdn/x.jpg", "anikato") == "http://cdn/x.jpg"


def test_web_wraps_every_host_with_the_provider_referer():
    set_display_context(BASE, True)
    wrapped = image_url("https://cdn.anipixcdn.co/thumbnail/x.jpg", "anikato")
    assert wrapped.startswith(f"{BASE}/image?")
    url, referer = _payload(wrapped)
    assert url == "https://cdn.anipixcdn.co/thumbnail/x.jpg"
    assert referer == PROBE_REFERERS["anikato"]
    # data: URIs (animepahe's) never double-wrap.
    assert image_url("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"
    # Unknown provider: wrapped, but with no fabricated referer.
    wrapped = image_url("https://cdn/x.jpg", "")
    assert "referer" not in urllib.parse.parse_qs(
        urllib.parse.urlparse(wrapped).query
    )


def test_native_wraps_only_guarded_hosts():
    set_display_context(BASE, False)
    wrapped = image_url("https://www.animeout.xyz/wp-content/uploads/a.png", "animeout")
    assert wrapped.startswith(f"{BASE}/image?")
    url, _ = _payload(wrapped)
    assert url == "https://www.animeout.xyz/wp-content/uploads/a.png"
    # Subdomains match; lookalikes do not.
    assert image_url("https://cdn.animeout.xyz/x.png").startswith(BASE)
    assert image_url("https://animeout.xyz.evil.com/x.png") == (
        "https://animeout.xyz.evil.com/x.png"
    )


# ---------------------------------------------------------------------------
# The route itself
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, status, body=b"", ctype="image/jpeg"):
        self.status_code = status
        self.content = body
        self.headers = {"content-type": ctype}


class _FakeClient:
    def __init__(self, resp):
        self.resp = resp
        self.calls = 0

    async def get(self, url, **kwargs):
        self.calls += 1
        return self.resp


class _Writer:
    def __init__(self):
        self.buf = b""

    def write(self, chunk):
        self.buf += chunk

    async def drain(self):
        pass


def _run_image(proxy, url, referer=""):
    import asyncio

    writer = _Writer()
    headers = {"User-Agent": "UA"}
    if referer:
        headers["Referer"] = referer
    asyncio.run(proxy._handle_image(writer, url, headers))
    return writer.buf


def test_fetch_forwards_type_cors_and_caches():
    proxy = HLSProxy()
    client = _FakeClient(_Resp(200, b"\xff\xd8jpegbytes", "image/jpeg"))
    proxy._http_client = client
    head = _run_image(proxy, "https://cdn/x.jpg", "https://site/")
    assert head.startswith(b"HTTP/1.1 200 OK")
    assert b"Content-Type: image/jpeg" in head
    assert b"Access-Control-Allow-Origin: *" in head
    assert head.endswith(b"\xff\xd8jpegbytes")
    # Second request: cache hit, no second upstream call.
    again = _run_image(proxy, "https://cdn/x.jpg", "https://site/")
    assert again == head
    assert client.calls == 1


def test_non_image_upstream_is_forwarded_as_bytes():
    proxy = HLSProxy()
    proxy._http_client = _FakeClient(_Resp(200, b"<html>err</html>", "text/html"))
    head = _run_image(proxy, "https://cdn/x.jpg")
    assert b"Content-Type: application/octet-stream" in head
    assert head.endswith(b"<html>err</html>")


def test_caps_and_upstream_errors_are_502():
    proxy = HLSProxy()
    proxy._http_client = _FakeClient(_Resp(200, b"x" * (MAX_IMAGE_BYTES + 1)))
    assert b"502" in _run_image(proxy, "https://cdn/big.jpg")
    proxy._http_client = _FakeClient(_Resp(403, b"Just a moment...", "text/html"))
    out = _run_image(proxy, "https://cdn/blocked.jpg")
    assert b"502" in out and b"Upstream 403" in out
    proxy._http_client = None
    assert b"500" in _run_image(proxy, "https://cdn/x.jpg")


# ---------------------------------------------------------------------------
# The display sites wrap through the context
# ---------------------------------------------------------------------------


def _first_image(control, found=None):
    import flet as ft

    found = [] if found is None else found
    if control is None or found:
        return found
    if isinstance(control, ft.Image):
        found.append(control)
        return found
    for attr in ("content", "controls", "actions", "title"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                _first_image(item, found)
        elif isinstance(child, ft.Control):
            _first_image(child, found)
    return found


def test_card_media_wraps_on_web_keeps_shape_from_the_raw_url():
    set_display_context(BASE, True)
    media = card_media("https://cdn/x.jpg", PORTRAIT)
    assert media.src.startswith(f"{BASE}/image?")
    url, _ = _payload(media.src)
    assert url == "https://cdn/x.jpg"


def test_result_card_carries_the_provider_referer():
    set_display_context(BASE, True)
    anime = Anime(
        id=1,
        title="Black Clover",
        type="TV",
        episodes=0,
        status="",
        season="",
        year=2024,
        score=None,
        poster="https://cdn.anipixcdn.co/thumbnail/x.jpg",
        session="anikato:black-clover",
    )
    card = result_card(anime, lambda *_: None, provider="anikato")
    image = _first_image(card)
    assert image, "the card renders an image"
    url, referer = _payload(image[0].src)
    assert url == "https://cdn.anipixcdn.co/thumbnail/x.jpg"
    assert referer == PROBE_REFERERS["anikato"]
