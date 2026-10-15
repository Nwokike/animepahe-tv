"""Discover: the filter vocabulary comes from the PROVIDING source, and a
source without a browse surface is never asked.

Nothing about genres, categories, types or sorts is hardcoded in the UI —
these tests pin both directions: the provider parses its own site's lists
into the filter spec, and browse() maps the selections onto the documented
request shape.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-discover-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

import pytest  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class _Resp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class _Client:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params or {}))
        for needle, resp in self.routes.items():
            if needle in url:
                return resp
        return _Resp(404)

    async def aclose(self):
        pass


WP_CATEGORIES = [
    {"id": 9, "name": "Action", "count": 263},
    {"id": 10, "name": "Adventure", "count": 179},
    {"id": 2, "name": "Anime Movie", "count": 62},
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_name, class_name, api_base",
    [
        ("services.providers.animeout", "AnimeOutProvider", "animeout.xyz"),
        ("services.providers.kayoanime", "KayoanimeProvider", "kayoanime"),
        ("services.providers.kusonime", "KusonimeProvider", "kusonime"),
    ],
)
async def test_wp_providers_discover_their_own_categories(
    module_name, class_name, api_base
):
    """The category list (with counts) is READ from the site, so a new
    bucket appears without a code change."""
    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    client = _Client({"/categories": _Resp(json_data=WP_CATEGORIES)})
    provider = cls(client=client)
    spec = await provider.filters()

    cat = next(s for s in spec if s["key"] == "categories")
    assert cat["kind"] == "choice"
    assert cat["options"] == [
        {"value": "9", "label": "Action (263)"},
        {"value": "10", "label": "Adventure (179)"},
        {"value": "2", "label": "Anime Movie (62)"},
    ]
    assert any(s["key"] == "orderby" for s in spec)


@pytest.mark.asyncio
async def test_wp_browse_maps_selections_onto_the_documented_params():
    from services.providers.kayoanime import KayoanimeProvider

    client = _Client(
        {
            "/categories": _Resp(json_data=WP_CATEGORIES),
            "/posts": _Resp(json_data=[]),
        }
    )
    provider = KayoanimeProvider(client=client)
    await provider.browse({"categories": ["9"], "orderby": "title"}, 2)

    posts = [c for c in client.calls if "/posts" in c[0]]
    assert len(posts) == 1
    params = posts[0][1]
    assert params["categories"] == "9"
    assert params["orderby"] == "title"
    assert params["page"] == "2"


@pytest.mark.asyncio
async def test_anikato_filters_are_discovered_not_embedded():
    """The genre slugs and the type/status option lists come off the home
    page; only the sort enum (which has no page to read it from) is a
    constant in the provider."""
    from services.providers.anikato import AniKatoProvider

    home = (
        '<a href="https://anikototv.to/genre/action">Action</a>'
        '<a href="https://anikototv.to/genre/award-winning">Award Winning</a>'
        '<a href="https://anikototv.to/type/tv">TV</a>'
        '<a href="https://anikototv.to/status/finished-airing">Finished</a>'
    )
    client = _Client({"/home": _Resp(text=home)})
    provider = AniKatoProvider(client=client)
    spec = await provider.filters()

    keys = {s["key"] for s in spec}
    assert keys == {"genre", "type", "status", "sort", "ep_min"}
    genre = next(s for s in spec if s["key"] == "genre")
    assert genre["options"] == [
        {"value": "action", "label": "Action"},
        {"value": "award-winning", "label": "Award Winning"},
    ]
    status = next(s for s in spec if s["key"] == "status")
    assert status["options"] == [{"value": "finished-airing", "label": "Finished"}]
    assert next(s for s in spec if s["key"] == "sort")["options"]


@pytest.mark.asyncio
async def test_anikato_browse_maps_the_filter_params():
    from services.providers.anikato import AniKatoProvider

    client = _Client({"/filter": _Resp(text="")})
    provider = AniKatoProvider(client=client)
    await provider.browse(
        {"genre": "action", "type": "tv", "sort": "score", "ep_min": "12"}, 3
    )

    (url, _params) = client.calls[-1]
    # only the selections that have a value ride — no empty params
    assert url == (
        "https://anikototv.to/filter?page=3&genre=action&type=tv&sort=score&ep_min=12"
    )


@pytest.mark.asyncio
async def test_a_provider_without_a_browse_route_is_never_asked():
    """animepahe's catalog is the airing page: it has no filters()/browse(),
    and the protocol treats that as 'skip', not as an error."""
    from services.providers.animepahe_provider import AnimePaheProvider

    provider = AnimePaheProvider(scraper=object())
    assert not hasattr(provider, "browse")
    assert not hasattr(provider, "filters")

    router = _router_with(provider)
    assert router.discover_provider() is None
    name, spec = await router.discover_filters()
    assert (name, spec) == ("", [])


class _FakeRouterProvider:
    def __init__(self, name, has_browse=True, items=None):
        self.name = name
        self._items = items or []
        if has_browse:
            self.capabilities = {}
            # a concrete browse surface
            self.browse = self._browse
            self.filters = self._filters

    async def _filters(self):
        return [{"key": "genre", "label": "Genre", "kind": "choice", "options": []}]

    async def _browse(self, filters, page):
        return (list(self._items), False)


def _router_with(*providers):
    from services.router import ProviderRouter

    return ProviderRouter(list(providers))


@pytest.mark.asyncio
async def test_discover_provider_picks_the_first_that_can_browse():
    from services.providers.animepahe_provider import AnimePaheProvider

    can = _FakeRouterProvider("canbrowse")
    router = _router_with(AnimePaheProvider(scraper=object()), can)
    assert router.discover_provider() is can
    # by name, when it can't browse, is None — never a fallback surprise
    assert router.discover_provider("animepahe") is None


def test_the_protocol_declares_the_optional_methods():
    """The route: duck-typed like schedule_tabs/random_slug, so a provider
    is free not to implement them — the CORE Provider must not declare
    them (runtime_checkable isinstance would then demand them and reject
    every provider without a browse surface). BrowserProvider carries the
    shape for the ones that do."""
    from services.providers.base import BrowserProvider, Provider as _P

    assert not hasattr(_P, "filters")
    assert not hasattr(_P, "browse")
    assert hasattr(BrowserProvider, "filters")
    assert hasattr(BrowserProvider, "browse")


def test_provider_without_browse_still_satisfies_the_protocol():
    """The exact regression: animepahe defines neither filters nor browse
    and must still pass the isinstance gate."""
    from services.providers.animepahe_provider import AnimePaheProvider
    from services.providers.base import Provider as _P

    assert isinstance(AnimePaheProvider(scraper=object()), _P)
