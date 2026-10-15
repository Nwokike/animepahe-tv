"""The provider router — ordered failover with per-provider breakers.

The app's data layer: the controller asks the ROUTER, the router asks
providers in editorial order until one answers. Design (verified in
docs/decisions.md):

- Static editorial order with health-gated skipping. Providers are
  never locked — failover is per request, because backends differ in
  coverage, not just health.
- Per-provider circuit breaker: 3 consecutive transport/parse failures
  -> OPEN (fail fast, no network), 30s cooldown, then ONE half-open
  trial; only a failed trial doubles the cooldown (cap 5min).
- An empty answer from one provider is not an answer (complete
  providers have different catalogs) — the chain continues. The last
  provider's empty is final.
- force=True bypasses an OPEN breaker ("Try another source").
- The startup probe race marks health non-blockingly; the app never
  waits for it.
- Bare sessions route to AnimePahe (legacy compatibility); namespaced
  sessions ("animeout:123") route to their owner first.
"""

import logging
import time

import anyio

from core.config import (
    BREAKER_FAIL_THRESHOLD,
    BREAKER_OPEN_MAX_SECONDS,
    BREAKER_OPEN_SECONDS,
    STARTUP_PROBE_BUDGET,
)
from services.providers.base import Provider, owner_of

logger = logging.getLogger("animepahe.router")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

STARTUP_PROBE_TIMEOUT = 4.0  # probes are short — dead != slow


class ProviderHealth:
    """Runtime-discovered health for one provider (surfaced in Settings)."""

    __slots__ = ("state", "latency_ms", "last_error", "checked_at")

    def __init__(self):
        self.state = "unknown"
        self.latency_ms: float | None = None
        self.last_error: str = ""
        self.checked_at: float = 0.0


class RouterError(Exception):
    """Every provider failed (or none are configured)."""


class _Breaker:
    __slots__ = ("state", "failures", "opened_at", "cooldown", "_now")

    def __init__(self, now):
        self.state = CLOSED
        self.failures = 0
        self.opened_at = 0.0
        self.cooldown = BREAKER_OPEN_SECONDS
        self._now = now

    def allow(self) -> bool:
        if self.state == CLOSED:
            return True
        if self.state == OPEN:
            if self._now() - self.opened_at >= self.cooldown:
                self.state = HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: trial requests allowed

    def record_success(self) -> None:
        self.failures = 0
        self.state = CLOSED
        self.cooldown = BREAKER_OPEN_SECONDS

    def record_failure(self) -> None:
        was_half_open = self.state == HALF_OPEN
        self.failures += 1
        if was_half_open or self.failures >= BREAKER_FAIL_THRESHOLD:
            self.state = OPEN
            self.opened_at = self._now()
            # Only a FAILED TRIAL escalates the cooldown (few seconds ->
            # few minutes). The first trip keeps the base cooldown.
            if was_half_open:
                self.cooldown = min(self.cooldown * 2, BREAKER_OPEN_MAX_SECONDS)


def _is_empty(result) -> bool:
    """An answer counts as empty when its PAYLOAD is empty. Providers
    return (items, has_more) tuples or lists — tuples are always truthy,
    so inspect the first element."""
    if (
        isinstance(result, tuple)
        and len(result) >= 1
        and isinstance(result[0], (list, tuple))
    ):
        return not result[0]
    return not result


class ProviderRouter:
    def __init__(self, providers: list[Provider] | None = None, *, clock=None):
        # Editorial priority order — first answering provider wins.
        self._providers: list[Provider] = list(providers or [])
        self._clock = clock or time.monotonic
        self._pin: str | None = None
        self.last_winner: str | None = None
        self._breakers: dict[str, _Breaker] = {}
        self._health: dict[str, ProviderHealth] = {}
        for provider in self._providers:
            self._breakers[provider.name] = _Breaker(self._clock)
            self._health[provider.name] = ProviderHealth()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def add_provider(self, provider: Provider) -> None:
        self._providers.append(provider)
        self._breakers[provider.name] = _Breaker(self._clock)
        self._health[provider.name] = ProviderHealth()

    def get(self, name: str) -> Provider | None:
        for provider in self._providers:
            if provider.name == name:
                return provider
        return None

    def set_pin(self, name: str | None) -> None:
        """'auto' (None) keeps the editorial order; a provider name sends
        it first for every operation — still with full failover."""
        self._pin = None if not name or name == "auto" else name

    @property
    def pin(self) -> str | None:
        return self._pin

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    # ------------------------------------------------------------------
    # Health (Settings reads this)
    # ------------------------------------------------------------------

    def health(self) -> dict[str, ProviderHealth]:
        return dict(self._health)

    def _record_health(
        self, provider: Provider, *, ok: bool, latency_ms: float, error: str = ""
    ) -> None:
        rec = self._health[provider.name]
        rec.state = self._breakers[provider.name].state
        rec.latency_ms = latency_ms if ok else rec.latency_ms
        rec.last_error = "" if ok else (error or "probe failed")[:200]
        rec.checked_at = time.time()

    # ------------------------------------------------------------------
    # The failover chain
    # ------------------------------------------------------------------

    async def _attempt(self, op: str, provider: Provider, args) -> object:
        """One provider attempt through its breaker; records health and
        breaker events. Raises on transport/parse failure."""
        breaker = self._breakers[provider.name]
        started = self._clock()
        try:
            result = await getattr(provider, op)(*args)
        except Exception:
            breaker.record_failure()
            self._record_health(
                provider,
                ok=False,
                latency_ms=(self._clock() - started) * 1000.0,
                error="failed",
            )
            raise
        breaker.record_success()
        self._record_health(
            provider, ok=True, latency_ms=(self._clock() - started) * 1000.0
        )
        return result

    async def _run(
        self,
        op: str,
        *args,
        force: bool = False,
        owner: str | None = None,
        session_owned: bool = False,
    ):
        """Try providers in editorial order (owner first when it owns the
        session); first provider with an actual ANSWER wins.

        Every provider is a COMPLETE app in its own right (nkiri-shaped:
        title in, catalog/posters/episodes/files out). They have different
        catalogs and different file walls, so an empty answer from one is
        not an answer — the chain continues.

        The candidates race: while they run together the worst case is
        max(fastest, deadline) instead of the sum of the chain's
        timeouts, so a walled provider no longer sits at the front of
        the wait. The first ANSWER (non-empty) cancels the rest.

        session_owned: the op takes a session string that NAMES its
        provider — only that provider is asked. Racing the others was
        wasted work AND dangerous (flet run log, 2026-10-15): a provider
        that returns unvalidated URLs (kayoanime probes nothing) won the
        race with a stream built from another provider's session string,
        and the ownerless lookups tripped animepahe's CF-clearing path
        on every call. Title-keyed ops (episodes_for_title_any /
        sources_for_title_any) are the sanctioned cross-provider path."""
        owner = owner or self._pin
        providers = self._providers
        if session_owned and owner:
            providers = [p for p in providers if p.name == owner]
            if not providers:
                raise RouterError(f"no provider owns the session for {op}")
        elif owner:
            providers = [p for p in providers if p.name == owner] + [
                p for p in providers if p.name != owner
            ]
        if not providers:
            raise RouterError("no providers configured")
        eligible = [p for p in providers if force or self._breakers[p.name].allow()]
        if not eligible:
            raise RouterError("no provider available (all circuits open)")
        # The first eligible provider (the owner when the session is
        # owned) answers alone — editorial order governs the common path
        # and no extra requests go out. Only when it fails or answers
        # empty does the rest race: the worst case is then
        # max(fastest, deadline) instead of the sum of the timeouts.
        first = eligible[0]
        try:
            result = await self._attempt(op, first, args)
        except Exception as ex:
            results_errors: list[Exception] = [ex]
        else:
            self.last_winner = first.name
            if not _is_empty(result):
                return result
            results_answers = {first.name: result}
            results_errors = []
        rest = eligible[1:]
        if not rest:
            if results_errors:
                raise RouterError(f"all providers failed for {op}") from results_errors[
                    0
                ]
            return results_answers[first.name]
        outcomes: dict[str, object] = (
            dict(results_answers) if not results_errors else {}
        )
        errors: list[Exception] = list(results_errors)
        winner: Provider | None = None

        async def _attempt_one(provider: Provider, tg) -> None:
            nonlocal winner
            try:
                result = await self._attempt(op, provider, args)
            except Exception as ex:
                errors.append(ex)
                return
            outcomes[provider.name] = result
            if not _is_empty(result):
                winner = provider
                tg.cancel_scope.cancel()  # the rest stand down

        async with anyio.create_task_group() as tg:
            for provider in rest:
                tg.start_soon(_attempt_one, provider, tg)

        if winner is not None:
            self.last_winner = winner.name
            return outcomes[winner.name]
        if outcomes:
            # The last provider that ANSWERED. Indexing by eligible[-1]
            # assumed it answered — a later provider that raised (and so
            # cancelled the group) is not in outcomes, and that indexing
            # raised KeyError on the empty-then-raise path.
            last_answered_name = list(outcomes)[-1]
            final_name = (
                eligible[-1].name
                if eligible[-1].name in outcomes
                else last_answered_name
            )
            self.last_winner = final_name
            return outcomes[final_name]
        if errors:
            raise RouterError(f"all providers failed for {op}") from errors[-1]
        raise RouterError(f"no provider answered for {op}")

    # ------------------------------------------------------------------
    # Public API — the router IS the app's data layer
    # ------------------------------------------------------------------

    async def latest_releases(self, page: int) -> tuple[list, bool]:
        return await self._run("latest_releases", page)

    async def search(self, query: str, page: int) -> tuple[list, bool]:
        return await self._run("search", query, page)

    async def episodes(self, session: str, page: int) -> tuple[list, bool]:
        return await self._run(
            "episodes",
            session,
            page,
            owner=owner_of(session),
            session_owned=True,
        )

    async def sources(self, anime_session: str, episode_session: str) -> list:
        return await self._run(
            "sources",
            anime_session,
            episode_session,
            owner=owner_of(anime_session),
            session_owned=True,
        )

    async def episodes_for_title_any(
        self, title: str, skip: str | None = None
    ) -> tuple[list, bool]:
        """'Try another source': ask every OTHER provider (title in ->
        episodes out; each is self-contained, no id glue). Breaker-aware;
        an empty answer moves on."""
        for provider in self._providers:
            if provider.name == skip:
                continue
            breaker = self._breakers[provider.name]
            if not breaker.allow():
                continue
            started = self._clock()
            try:
                result = await provider.episodes_for_title(title)
            except Exception as ex:
                breaker.record_failure()
                self._record_health(
                    provider,
                    ok=False,
                    latency_ms=(self._clock() - started) * 1000.0,
                    error=str(ex),
                )
                logger.info("episodes_for_title failed on %s: %s", provider.name, ex)
                continue
            breaker.record_success()
            self._record_health(
                provider, ok=True, latency_ms=(self._clock() - started) * 1000.0
            )
            if not _is_empty(result):
                self.last_winner = provider.name
                return (result, False)
        return ([], False)

    async def sources_for_title_any(
        self, title: str, episode: int, skip: str | None = None, *, force: bool = False
    ) -> list:
        """'Try another source' for PLAYBACK: ask every OTHER provider for
        this title's episode sources (title in -> sources out; each is
        self-contained, no id glue). Breaker-aware unless force — the user
        asking to watch something overrides a tripped breaker."""
        results: list = []
        for provider in self._providers:
            if provider.name == skip:
                continue
            breaker = self._breakers[provider.name]
            if not force and not breaker.allow():
                continue
            started = self._clock()
            try:
                result = await provider.sources_for_title(title, episode)
            except Exception as ex:
                if not force:
                    breaker.record_failure()
                self._record_health(
                    provider,
                    ok=False,
                    latency_ms=(self._clock() - started) * 1000.0,
                    error=str(ex),
                )
                logger.info("sources_for_title failed on %s: %s", provider.name, ex)
                continue
            breaker.record_success()
            self._record_health(
                provider, ok=True, latency_ms=(self._clock() - started) * 1000.0
            )
            if not _is_empty(result):
                self.last_winner = provider.name
                results = result
                break
        return results

    # ------------------------------------------------------------------
    # Discovery — the provider whose source has a browse surface
    # ------------------------------------------------------------------

    def discover_provider(self, name: str | None = None) -> "Provider | None":
        """The provider that serves Discover: the named one when it can
        browse, otherwise the first in editorial order that can.

        A provider without a browse route (animepahe's catalog is the
        airing page) simply has no filters()/browse() — it is skipped,
        never asked."""
        if name:
            provider = self.get(name)
            if provider is not None and hasattr(provider, "browse"):
                return provider
            return None
        for provider in self._providers:
            if hasattr(provider, "browse"):
                return provider
        return None

    async def discover_filters(self, name: str | None = None) -> tuple[str, list[dict]]:
        """(provider name, its filter vocabulary). Empty when no provider
        can browse."""
        provider = self.discover_provider(name)
        if provider is None:
            return ("", [])
        try:
            spec = await provider.filters()
        except Exception as ex:
            logger.info("discover filters failed on %s: %s", provider.name, ex)
            return ("", [])
        return (provider.name, spec)

    async def browse(
        self, name: str, filters: dict, page: int
    ) -> tuple[str, list, bool]:
        """Filtered catalog from the named provider. Same breaker-aware
        shape as the rest of the router: an empty answer is a RESULT."""
        provider = self.discover_provider(name)
        if provider is None:
            return ("", [], False)
        breaker = self._breakers[provider.name]
        if not breaker.allow():
            return ("", [], False)
        started = self._clock()
        try:
            result = await provider.browse(filters, page)
        except Exception as ex:
            breaker.record_failure()
            self._record_health(
                provider,
                ok=False,
                latency_ms=(self._clock() - started) * 1000.0,
                error=str(ex),
            )
            logger.info("browse failed on %s: %s", provider.name, ex)
            return ("", [], False)
        breaker.record_success()
        self._record_health(
            provider, ok=True, latency_ms=(self._clock() - started) * 1000.0
        )
        items, has_more = result
        if _is_empty(items):
            return (provider.name, [], False)
        self.last_winner = provider.name
        return (provider.name, items, has_more)

    # ------------------------------------------------------------------
    # Startup probe race — non-blocking, budget-capped
    # ------------------------------------------------------------------

    async def probe_all(self) -> dict[str, bool]:
        """Race every provider's cheap probe in parallel under one
        deadline. Never raises; a failed probe records one breaker
        failure (of three). A deadline hit no longer fabricates failures
        — a provider that simply didn't answer in time is left as it
        was (the half-open machinery retries it later)."""
        if not self._providers:
            return {}
        ok: dict[str, bool] = {}
        with anyio.move_on_after(STARTUP_PROBE_BUDGET):
            async with anyio.create_task_group() as tg:
                for provider in self._providers:
                    tg.start_soon(self._probe_record, provider, ok)
        return ok

    async def _probe_record(self, provider: Provider, ok: dict) -> None:
        try:
            ok[provider.name] = await self._probe_one(provider)
        except Exception:
            ok[provider.name] = False

    async def _probe_one(self, provider: Provider) -> bool:
        started = self._clock()
        try:
            with anyio.fail_after(STARTUP_PROBE_TIMEOUT):
                ok = await provider.probe()
        except TimeoutError:
            self._record_health(
                provider,
                ok=False,
                latency_ms=(self._clock() - started) * 1000.0,
                error="timeout",
            )
            return False
        except Exception as ex:
            self._record_health(
                provider,
                ok=False,
                latency_ms=(self._clock() - started) * 1000.0,
                error=str(ex),
            )
            return False
        self._record_health(
            provider, ok=bool(ok), latency_ms=(self._clock() - started) * 1000.0
        )
        return bool(ok)

    async def close(self) -> None:
        for provider in self._providers:
            try:
                await provider.close()
            except Exception:
                pass


__all__ = [
    "ProviderRouter",
    "RouterError",
    "ProviderHealth",
    "CLOSED",
    "OPEN",
    "HALF_OPEN",
]
