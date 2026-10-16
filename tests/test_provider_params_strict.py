"""primp-bound query params must be strings — the fake-client blind spot.

primp 2.0.1's Rust layer rejects non-string params with
`'int' object is not an instance of 'str'`. The injected test fakes accept
anything, so animeout's integer params (`per_page: 12`, `page: page`)
shipped broken: the flet run log showed
`episodes_for_title failed on animeout: 'int' object is not an instance of 'str'`.

This file uses a STRICT fake that mirrors primp's type check, and drives
every provider op that passes query params through it.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class _StrictResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = ""
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class StrictParamsClient:
    """Mirrors primp's contract: every param VALUE must be a str."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, params=None, headers=None, **kwargs):
        for key, value in (params or {}).items():
            if not isinstance(value, str):
                raise TypeError(
                    f"'{type(value).__name__}' object is not an instance of 'str'"
                )
        self.calls.append((url, dict(params or {})))
        return _StrictResp(200, [])


def test_animeout_every_params_path_is_string_typed():
    from services.providers.animeout import AnimeOutProvider

    client = StrictParamsClient()
    provider = AnimeOutProvider(client=client)

    # probe / per_page=1
    assert asyncio.run(provider.probe()) is True
    # latest / per_page + page
    asyncio.run(provider.latest_releases(2))
    # search / search + per_page + page
    asyncio.run(provider.search("frieren", 1))
    # filters / per_page=100
    asyncio.run(provider.filters())
    assert len(client.calls) >= 4


def test_kayoanime_params_are_string_typed():
    from services.providers.kayoanime import KayoanimeProvider

    kayo_client = StrictParamsClient()
    kayo = KayoanimeProvider(client=kayo_client)
    asyncio.run(kayo.latest_releases(1))
    asyncio.run(kayo.search("x", 1))
    asyncio.run(kayo.filters())
