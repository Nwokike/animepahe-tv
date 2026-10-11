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


@runtime_checkable
class Provider(Protocol):
    name: str
    capabilities: dict

    async def probe(self) -> bool:
        """Cheap liveness check for the startup race (short timeout)."""
        ...

    async def latest_releases(self, page: int) -> tuple[list[LatestRelease], bool]:
        ...

    async def search(self, query: str, page: int) -> tuple[list[Anime], bool]:
        ...

    async def episodes(self, session: str, page: int) -> tuple[list[Episode], bool]:
        ...

    async def sources(self, anime_session: str, episode_session: str) -> list[Source]:
        """Playable URLs for one episode. Empty means genuinely none —
        that is a RESULT, not a failure, and does not fail over."""
        ...

    async def close(self) -> None:
        ...


__all__ = [
    "Provider",
    "DEFAULT_OWNER",
    "make_session",
    "split_session",
    "owner_of",
]
