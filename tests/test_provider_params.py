"""Provider params must be strings — the owner's live-run bug.

AnimeOut's browse passed int `per_page`/`page` into primp, which raised
"'int' object is not an instance of 'str'" on every call; three failures
tripped its breaker and the log then showed searches failing with "no
provider available (all circuits open)". These tests capture every params
dict the WP providers send and assert no value is a non-string.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.providers.animeout import AnimeOutProvider  # noqa: E402
from services.providers.kayoanime import KayoanimeProvider  # noqa: E402
from services.providers.kusonime import KusonimeProvider  # noqa: E402


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _RecClient:
    def __init__(self):
        self.param_sets = []

    async def get(self, url, params=None, **kwargs):
        self.param_sets.append(dict(params or {}))
        return _Resp([])


def _assert_all_strings(param_sets, provider_name):
    for params in param_sets:
        bad = {k: v for k, v in params.items() if not isinstance(v, str)}
        assert not bad, f"{provider_name} sent non-string params: {bad}"


def test_animeout_every_param_is_a_string():
    client = _RecClient()
    provider = AnimeOutProvider(client=client)
    asyncio.run(provider.browse({}, 2))
    asyncio.run(provider.latest_releases(1))
    asyncio.run(provider.search("x", 3))
    assert client.param_sets, "the provider actually called out"
    _assert_all_strings(client.param_sets, "animeout")
    # The exact regression: the browse page must arrive as a string.
    assert any(p.get("page") == "2" for p in client.param_sets)


def test_kusonime_every_param_is_a_string():
    client = _RecClient()
    provider = KusonimeProvider(client=client)
    asyncio.run(provider.browse({}, 2))
    asyncio.run(provider.latest_releases(1))
    asyncio.run(provider.search("x", 3))
    _assert_all_strings(client.param_sets, "kusonime")


def test_kayoanime_every_param_is_a_string():
    client = _RecClient()
    provider = KayoanimeProvider(client=client)
    asyncio.run(provider.browse({}, 2))
    asyncio.run(provider.latest_releases(1))
    asyncio.run(provider.search("x", 3))
    _assert_all_strings(client.param_sets, "kayoanime")
