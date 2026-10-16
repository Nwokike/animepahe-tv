"""primp 2.0.1 client-lifecycle regressions.

The bug class: primp 2.0.1's AsyncClient exposes ONLY the context-manager
protocol (__aenter__/__aexit__) — no aclose(), no close(), no is_closed.
Code calling those raised AttributeError at runtime while the test suite
passed, because every fake client in the suite implemented aclose() only.
These tests pin the real client shape (context-manager-only) so a
regression to aclose()/is_closed fails loudly here instead of in prod.
"""

import primp
import pytest

from services.animeout_solver import AnimeOutSolver
from services.hls_proxy import REASON_PHRASES, HLSProxy
from services.providers.anikato import AniKatoProvider
from services.providers.animeout import AnimeOutProvider
from services.providers.base import close_client
from services.providers.kayoanime import KayoanimeProvider


def test_installed_primp_client_has_no_aclose():
    """Ground truth for this whole file: pinned against the installed wheel."""
    assert not hasattr(primp.AsyncClient, "aclose")
    assert not hasattr(primp.AsyncClient, "close")
    assert hasattr(primp.AsyncClient, "__aenter__")
    assert hasattr(primp.AsyncClient, "__aexit__")


class _RealShapedClient:
    """The installed primp 2.0.1 shape: context-manager protocol ONLY."""

    def __init__(self):
        self.exited = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.exited += 1

    async def get(self, url, **kwargs):
        class _Resp:
            status_code = 200
            text = "just a page"

        return _Resp()


class _FakeShapedClient:
    """The test-suite shape: aclose() only (what fakes used to call)."""

    def __init__(self):
        self.closed = 0

    async def aclose(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_close_client_prefers_dunder_exit_on_real_shape():
    client = _RealShapedClient()
    await close_client(client)
    assert client.exited == 1


@pytest.mark.asyncio
async def test_close_client_falls_back_to_aclose_on_fake_shape():
    client = _FakeShapedClient()
    await close_client(client)
    assert client.closed == 1


@pytest.mark.asyncio
async def test_close_client_none_is_a_noop():
    await close_client(None)


@pytest.mark.asyncio
async def test_provider_close_tolerates_real_shaped_client():
    """Provider close() with a context-manager-only client must not raise."""
    for provider in (
        AnimeOutProvider(client=_RealShapedClient()),
        AniKatoProvider(client=_RealShapedClient()),
        KayoanimeProvider(client=_RealShapedClient()),
    ):
        await provider.close()


@pytest.mark.asyncio
async def test_provider_close_still_works_with_fake_client():
    client = _FakeShapedClient()
    provider = AnimeOutProvider(client=client)
    await provider.close()
    assert client.closed == 1


@pytest.mark.asyncio
async def test_animeout_probe_releases_its_client(monkeypatch):
    """The probe creates its own client — release must use the real API."""
    created: list[_RealShapedClient] = []

    def _factory(*args, **kwargs):
        client = _RealShapedClient()
        created.append(client)
        return client

    monkeypatch.setattr(primp, "AsyncClient", _factory)
    solver = AnimeOutSolver(store=None)
    # A non-challenge page means the clearance is still good.
    assert await solver._probe({"cookies": "a=b", "user_agent": "ua"}) is True
    assert created and created[0].exited == 1


@pytest.mark.asyncio
async def test_send_response_names_unlisted_cdn_codes():
    """429/418 (what CDNs actually answer with) must not render as 'Unknown'
    — strict players reject that phrase."""
    proxy = HLSProxy()

    class _Writer:
        def __init__(self):
            self.buf = b""

        def write(self, data):
            self.buf += data

        async def drain(self):
            pass

    for code in (429, 418, 206):
        writer = _Writer()
        await proxy._send_response(writer, code, "text/plain", b"x")
        assert f"HTTP/1.1 {code} {REASON_PHRASES[code]}".encode() in writer.buf


def test_reason_table_has_no_unknown_for_common_codes():
    for code in (200, 206, 403, 404, 429, 500, 502, 503):
        assert REASON_PHRASES.get(code, "Unknown") != "Unknown"
