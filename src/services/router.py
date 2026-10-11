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

import asyncio
import logging
import time

from core.config import (
    BREAKER_FAIL_THRESHOLD,
    BREAKER_HALF_OPEN_TRIALS,
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
    if isinstance(result, tuple) and len(result) >= 1 and isinstance(result[0], (list, tuple)):
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

    def _record_health(self, provider: Provider, *, ok: bool, latency_ms: float, error: str = "") -> None:
        rec = self._health[provider.name]
        rec.state = self._breakers[provider.name].state
        rec.latency_ms = latency_ms if ok else rec.latency_ms
        rec.last_error = "" if ok else (error or "probe failed")[:200]
        rec.checked_at = time.time()

    # ------------------------------------------------------------------
    # The failover chain
    # ------------------------------------------------------------------

    async def _run(self, op: str, *args, force: bool = False, owner: str | None = None):
        owner = owner or self._pin
        providers = self._providers
        if owner:
            providers = [p for p in providers if p.name == owner] + [
                p for p in providers if p.name != owner
            ]
        last_error: Exception | None = None
        for idx, provider in enumerate(providers):
            is_last = idx == len(providers) - 1
            breaker = self._breakers[provider.name]
            if not force and not breaker.allow():
                logger.debug("router: skip %s (breaker %s)", provider.name, breaker.state)
                continue
            started = self._clock()
            try:
                result = await getattr(provider, op)(*args)
            except Exception as ex:  # transport or parse failure -> fail over
                breaker.record_failure()
                self._record_health(provider, ok=False, latency_ms=(self._clock() - started) * 1000.0, error=str(ex))
                last_error = ex
                logger.info("router: %s failed on %s: %s", op, provider.name, ex)
                continue
            breaker.record_success()
            self._record_health(provider, ok=True, latency_ms=(self._clock() - started) * 1000.0)
            if not _is_empty(result) or is_last:
                self.last_winner = provider.name
                return result
            logger.debug("router: %s empty on %s — trying next", op, provider.name)
        if not providers:
            raise RouterError("no providers configured")
        if last_error is not None:
            raise RouterError(f"all providers failed for {op}") from last_error
        raise RouterError(f"no provider answered for {op}")

    # ------------------------------------------------------------------
    # Public API — the router IS the app's data layer
    # ------------------------------------------------------------------

    async def latest_releases(self, page: int) -> tuple[list, bool]:
        return await self._run("latest_releases", page)

    async def search(self, query: str, page: int) -> tuple[list, bool]:
        return await self._run("search", query, page)

    async def episodes(self, session: str, page: int) -> tuple[list, bool]:
        return await self._run("episodes", session, page, owner=owner_of(session))

    async def episodes_forced(self, session: str, page: int) -> tuple[list, bool]:
        """'Try another source' — bypass OPEN breakers for this call."""
        return await self._run("episodes", session, page, force=True, owner=owner_of(session))

    async def sources(self, anime_session: str, episode_session: str) -> list:
        return await self._run("sources", anime_session, episode_session, owner=owner_of(anime_session))

    async def sources_forced(self, anime_session: str, episode_session: str) -> list:
        return await self._run(
            "sources", anime_session, episode_session, force=True, owner=owner_of(anime_session)
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
                    provider, ok=False, latency_ms=(self._clock() - started) * 1000.0, error=str(ex)
                )
                logger.info("episodes_for_title failed on %s: %s", provider.name, ex)
                continue
            breaker.record_success()
            self._record_health(provider, ok=True, latency_ms=(self._clock() - started) * 1000.0)
            if not _is_empty(result):
                self.last_winner = provider.name
                return (result, False)
        return ([], False)

    # ------------------------------------------------------------------
    # Startup probe race — non-blocking, budget-capped
    # ------------------------------------------------------------------

    async def probe_all(self) -> dict[str, bool]:
        """Race every provider's cheap probe in parallel. Never raises;
        a failed probe records one breaker failure (of three)."""
        if not self._providers:
            return {}
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(self._probe_one(p) for p in self._providers),
                    return_exceptions=True,
                ),
                timeout=STARTUP_PROBE_BUDGET,
            )
        except asyncio.TimeoutError:
            results = [None] * len(self._providers)
        ok: dict[str, bool] = {}
        for provider, result in zip(self._providers, results):
            ok[provider.name] = bool(result is True)
            if not ok[provider.name]:
                self._breakers[provider.name].record_failure()
        return ok

    async def _probe_one(self, provider: Provider) -> bool:
        started = self._clock()
        try:
            ok = await asyncio.wait_for(provider.probe(), timeout=STARTUP_PROBE_TIMEOUT)
        except Exception as ex:
            self._record_health(provider, ok=False, latency_ms=(self._clock() - started) * 1000.0, error=str(ex))
            return False
        self._record_health(provider, ok=bool(ok), latency_ms=(self._clock() - started) * 1000.0)
        return bool(ok)

    async def close(self) -> None:
        for provider in self._providers:
            try:
                await provider.close()
            except Exception:
                pass


__all__ = ["ProviderRouter", "RouterError", "ProviderHealth", "CLOSED", "OPEN", "HALF_OPEN"]
