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

import pytest

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
    ],
)
async def test_wp_providers_discover_their_own_categories(module_name, class_name, api_base):
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
    """The option lists come off the site's OWN /filter form controls —
    the input names and values the server actually accepts (genre[]=1,
    term_type[]=Movie, status[]=..., season[]=...). The old slug scraping
    read /genre/action links, which the filter endpoint ignores; every
    genre click returned the unfiltered grid."""
    from services.providers.anikato import AniKatoProvider

    form = (
        '<input type="checkbox" id="genre-1" name="genre[]" value="1" />'
        '<label for="genre-1"> Action </label>'
        '<input type="checkbox" id="genre-2" name="genre[]" value="2344" />'
        '<label for="genre-2"> Action &amp; Adventure </label>'
        '<input type="checkbox" id="t-m" name="term_type[]" value="Movie" />'
        '<label for="t-m"> Movie </label>'
        '<input type="checkbox" id="s-fin" name="status[]" value="finished-airing" />'
        '<label for="s-fin"> Finished Airing </label>'
        '<input type="checkbox" id="se-fall" name="season[]" value="fall" />'
        '<label for="se-fall"> Fall </label>'
    )
    client = _Client({"/filter": _Resp(text=form)})
    provider = AniKatoProvider(client=client)
    spec = await provider.filters()

    keys = {s["key"] for s in spec}
    assert keys == {"genre", "type", "status", "season", "sort", "ep_min"}
    genre = next(s for s in spec if s["key"] == "genre")
    assert genre["options"] == [
        {"value": "1", "label": "Action"},
        {"value": "2344", "label": "Action & Adventure"},
    ]
    assert next(s for s in spec if s["key"] == "type")["options"] == [
        {"value": "Movie", "label": "Movie"}
    ]
    assert next(s for s in spec if s["key"] == "status")["options"] == [
        {"value": "finished-airing", "label": "Finished Airing"}
    ]
    assert next(s for s in spec if s["key"] == "season")["options"] == [
        {"value": "fall", "label": "Fall"}
    ]
    assert next(s for s in spec if s["key"] == "sort")["options"]


@pytest.mark.asyncio
async def test_anikato_browse_maps_the_filter_params():
    from services.providers.anikato import AniKatoProvider

    client = _Client({"/filter": _Resp(text="")})
    provider = AniKatoProvider(client=client)
    await provider.browse(
        {
            "genre": "1",
            "type": "Movie",
            "status": "finished-airing",
            "season": "fall",
            "sort": "score",
            "ep_min": "12",
        },
        3,
    )

    (url, _params) = client.calls[-1]
    # The site's own form names ride once-encoded; only selections with a
    # value ride — no empty params.
    assert url == (
        "https://anikototv.to/filter?page=3&genre%5B%5D=1&term_type%5B%5D=Movie"
        "&status%5B%5D=finished-airing&season%5B%5D=fall&sort=score&ep_min=12"
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
    from services.providers.base import BrowserProvider
    from services.providers.base import Provider as _P

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


# ---------------------------------------------------------------------------
# 2026-10-19 — the string-vs-list filter shape (owner's DVD report)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_string_filter_value_is_never_char_iterated():
    """The owner: "I see DVD 2, but then I open DVD and there are more than
    that." The dropdown emits one string; `browse` joins a LIST. Joining the
    raw string iterated its CHARACTERS: DVD=14893 became categories=1,4,8,9,3
    — five unrelated categories. Both the screen and the provider now coerce
    the shape, so the honest two are returned."""
    from services.providers.animeout import AnimeOutProvider

    client = _Client(
        {
            "/categories": _Resp(json_data=WP_CATEGORIES),
            "/posts": _Resp(json_data=[]),
        }
    )
    provider = AnimeOutProvider(client=client)
    await provider.browse({"categories": "14893"}, 1)
    params = next(c[1] for c in client.calls if "/posts" in c[0])
    assert params["categories"] == "14893", (
        "a bare string filter value must be sent intact, never char-joined"
    )


def test_the_screen_shapes_dropdown_values_to_the_protocol():
    """The screen's _pick wraps the MULTI-VALUED keys in a list and passes
    scalars through — and which keys are multi-valued is read from the
    PROVIDER'S SPEC, not from a hardcoded list in the UI.

    The hardcoded list was wrong the moment it was written: it wrapped
    AniKato's genre/status/season in a list the site's form never wanted
    (the request became ``genre[]=['1']`` and the grid came back empty —
    2026-10-19), and it missed WordPress's "type" key. The provider
    declares the shape; the screen renders it."""
    import screens.discover_screen as ds

    spec = [
        {"key": "categories", "kind": "choice", "multi": True, "options": []},
        {"key": "orderby", "kind": "choice", "options": [{"value": "modified"}]},
    ]
    multi = ds._multi_valued_keys(spec)
    assert "categories" in multi
    assert "orderby" not in multi, "a sort is a single value"

    shaped = lambda key, value: {key: [value] if key in multi else value}
    assert shaped("categories", "14893")["categories"] == ["14893"]
    assert shaped("orderby", "date")["orderby"] == "date"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_name, class_name",
    [
        ("services.providers.animeout", "AnimeOutProvider"),
        ("services.providers.kayoanime", "KayoanimeProvider"),
    ],
)
async def test_the_providers_declare_their_own_filter_shapes(module_name, class_name):
    """Each provider says what its keys mean: "multi" for the ones that
    take several values, "direction" for the ones whose sort can be
    flipped. The screen reads those flags, so a provider that changes its
    own vocabulary needs no UI change."""
    import importlib

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    client = _Client({"/categories": _Resp(json_data=WP_CATEGORIES)})
    provider = cls(client=client)
    provider._cache_get = lambda key: None
    provider._cache_put = lambda key, value, ttl: None

    spec = await provider.filters()
    by_key = {s["key"]: s for s in spec}
    assert by_key["categories"].get("multi") is True, (
        "the category key takes several values — the screen must send a list"
    )
    assert by_key["orderby"].get("direction") is True, (
        "WordPress's orderby has a direction (asc/desc) the screen may toggle"
    )


@pytest.mark.asyncio
async def test_anikato_declares_no_direction_because_its_form_has_none():
    """AniKato's own /filter form has NO order parameter (verified live
    2026-10-19: genre[], term_type[], status[], season[], sort, ep_min,
    ep_max, year[], rating[], source[], language[]). A direction toggle
    there flips an arrow and changes nothing — so the provider declares
    none, and the screen shows no toggle."""
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider()
    provider._cache_get = lambda key: None
    provider._cache_put = lambda key, value, ttl: None

    async def _options():
        return (
            [{"value": "1", "label": "Action"}],
            [{"value": "tv", "label": "TV"}],
            [{"value": "finished-airing", "label": "Finished"}],
            [{"value": "fall", "label": "Fall"}],
        )

    provider._discover_filter_options = _options
    spec = await provider.filters()
    by_key = {s["key"]: s for s in spec}
    for key in ("genre", "type", "status", "season"):
        assert by_key[key].get("multi") is True, (
            f"{key} is an ARRAY input on the site's form — the screen must send a list"
        )
    assert "direction" not in by_key["sort"], (
        "AniKato's form has no order parameter — declaring a direction "
        "would put a dead control on the screen"
    )


def test_the_sort_default_is_what_the_request_carries():
    """The dropdown shows the site's first sort option when nothing is
    picked, so the REQUEST must carry it — a displayed value that is never
    sent is a lie (the owner's "the numbering... does not update",
    2026-10-19)."""
    import screens.discover_screen as ds

    filters = [
        {"key": "orderby", "kind": "choice", "options": [{"value": "modified"}]},
    ]
    assert ds._sort_defaults(filters) == {"orderby": "modified"}
    assert ds._effective_selections({}, filters) == {"orderby": "modified"}
    # An explicit pick is never overwritten.
    assert ds._effective_selections({"orderby": "date"}, filters) == {"orderby": "date"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters, expected",
    [
        ({"genre": ["1"], "type": "tv"}, ["genre%5B%5D=1", "term_type%5B%5D=tv"]),
        ({"genre": "1"}, ["genre%5B%5D=1"]),
        ({"status": ["fall", "winter"]}, ["status%5B%5D=fall", "status%5B%5D=winter"]),
    ],
)
async def test_anikato_sends_its_array_filters_as_repeated_parameters(filters, expected):
    """The site's form takes genre[]=1&genre[]=2, not a stringified list.

    Stringifying the list outright sent ``genre[]=%5B%271%27%5D`` — the
    site matched nothing and the grid came back empty (2026-10-19)."""
    from services.providers.anikato import AniKatoProvider

    client = _Client({"/filter": _Resp(text="<html></html>")})
    provider = AniKatoProvider(client=client)
    await provider.browse(filters, 1)
    url = client.calls[0][0]
    for part in expected:
        assert part in url, url
    assert "genre%5B%5D=%5B" not in url, "a stringified list matches nothing on the site"
