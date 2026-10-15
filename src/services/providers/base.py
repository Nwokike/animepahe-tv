"""The provider protocol — one shape, many complete backends.

Every provider is a WHOLE app in its own way (nkiri-shaped): title in,
catalog/episodes/files out. The method shapes mirror the app's existing
AnimePaheScraper exactly, so the existing AnimePahe machinery slots in
as provider #1 and the controller's call sites swap 1:1.

Sessions are namespaced for everything EXCEPT AnimePahe (whose bare
session strings already live in the user's store and history — those
keep working unchanged). ``animeout:123`` routes to the animeout
provider; a bare session routes to AnimePahe.
"""

from typing import Protocol, runtime_checkable

from core.state import Anime, Episode, LatestRelease, Source

DEFAULT_OWNER = "animepahe"

# One page of an episode grid (Prev · Page N · Next). AnimePahe pages this
# server-side (30/page — its own shape); the providers whose sources return
# the whole list in one shot slice it to this cap so no screen ever renders
# a 170-episode (or kusonime's 1000-episode) dump at once.
EPISODES_PER_PAGE = 24


def page_slice(items: list, page: int) -> tuple[list, bool]:
    """One page of an all-at-once list, in the protocol's page shape."""
    start = max(page - 1, 0) * EPISODES_PER_PAGE
    window = items[start : start + EPISODES_PER_PAGE]
    return window, start + EPISODES_PER_PAGE < len(items)


async def all_episodes(provider, session: str, *, max_pages: int = 100) -> list[Episode]:
    """Every episode across the provider's pages.

    The title-keyed lookups and the new-episode checker need the whole
    list, not page 1. Providers whose source returns everything at once
    slice their cache, so the walk costs one fetch; server-paged providers
    (animepahe) pay one call per page. The cap is defensive only — a buggy
    has_more must never loop forever."""
    episodes: list[Episode] = []
    page = 1
    while page <= max_pages:
        chunk, has_more = await provider.episodes(session, page)
        episodes.extend(chunk)
        if not has_more:
            break
        page += 1
    return episodes


def make_session(provider_name: str, native_id: str) -> str:
    return f"{provider_name}:{native_id}"


def split_session(session: str) -> tuple[str, str]:
    """'animeout:123' -> ('animeout', '123'); bare -> ('', session) —
    bare sessions belong to AnimePahe (legacy compatibility)."""
    if ":" in session:
        name, _, rest = session.partition(":")
        return name, rest
    return "", session


def owner_of(session: str) -> str:
    name, _ = split_session(session)
    return name or DEFAULT_OWNER


async def close_client(client) -> None:
    """Release a primp client. primp 2.0.1's AsyncClient exposes ONLY the
    context-manager protocol (``__aenter__``/``__aexit__``) — there is no
    ``aclose()``/``close()``/``is_closed`` (calling one is an AttributeError
    at runtime; the old code did exactly that on every close path). Test
    fakes implement ``aclose()`` only, so prefer ``__aexit__`` and fall
    back to it."""
    if client is None:
        return
    aexit = getattr(client, "__aexit__", None)
    if aexit is not None:
        await aexit(None, None, None)
        return
    aclose = getattr(client, "aclose", None)
    if aclose is not None:
        await aclose()


def releases_from_anime(items: list) -> list:
    """Catalog rows -> the release-grid shape the home screen reads.

    ``latest_releases`` must return ``LatestRelease`` rows (anime_session /
    anime_title / snapshot / episode / session) — the WP-shaped providers
    used to return raw ``Anime`` rows, and the home grid crashed on
    ``release.anime_session`` the first time one of them won the race.
    episode=0 and session="" say "per-anime row, no specific episode",
    which is the truth for a new-release grid; nothing is invented."""
    return [
        LatestRelease(
            anime_id=a.id,
            anime_title=a.title,
            anime_session=a.session,
            episode=0,
            snapshot=a.poster,
            session="",
            created_at="",
        )
        for a in items
    ]


@runtime_checkable
class Provider(Protocol):
    name: str
    capabilities: dict

    async def probe(self) -> bool:
        """Cheap liveness check for the startup race (short timeout)."""
        ...

    async def latest_releases(self, page: int) -> tuple[list[LatestRelease], bool]: ...

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]: ...

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]: ...

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        """Playable URLs for one episode. Empty means genuinely none —
        that is a RESULT, not a failure, and does not fail over."""
        ...

    # The router's title-keyed failover calls these on every provider —
    # they were missing from this Protocol entirely while all five
    # providers implemented them and router.py called them at :307/:343.
    async def episodes_for_title(self, title: str) -> list[Episode]: ...

    async def sources_for_title(self, title: str, episode: int) -> list[Source]: ...

    async def close(self) -> None: ...


@runtime_checkable
class BrowserProvider(Protocol):
    """Discovery surface a provider exposes only when its source has one.
    Kept separate from ``Provider`` because ``isinstance`` against a
    runtime_checkable Protocol checks attribute presence — declaring these
    as required members made valid providers (e.g. animepahe) fail the
    check. The router's duck-typed hasattr probing is the right gate; this
    Protocol only documents the shape."""

    async def filters(self) -> list[dict]:
        """The filter vocabulary THIS provider's source offers, as
        ``[{"key", "label", "kind": "choice"|"number", "options":
        [{"value", "label"}]}]``. Values come from the provider's own
        site at runtime — nothing is hardcoded in the UI. A provider
        without a browse route omits this entirely."""
        ...

    async def browse(self, filters: dict, page: int) -> tuple[list[Anime], bool]:
        """Filtered catalog: the selections dict maps filter keys to the
        chosen values (radio semantics per key). Empty means nothing
        matched — a RESULT, not a failure."""
        ...


__all__ = [
    "Provider",
    "BrowserProvider",
    "DEFAULT_OWNER",
    "EPISODES_PER_PAGE",
    "all_episodes",
    "make_session",
    "page_slice",
    "split_session",
    "owner_of",
    "close_client",
    "releases_from_anime",
]
