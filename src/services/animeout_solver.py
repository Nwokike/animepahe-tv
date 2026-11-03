"""Cloudflare clearance for AnimeOut's file host.

The wall is a real JS challenge (httpx and primp both get a 403 — see
``docs/decisions.md``), so it needs the same machinery that clears
AnimePahe's: ``WebViewSolver.solve_challenge`` takes any URL and returns
``(cookies, user_agent)``.

The shape follows ``DDoSSolver`` exactly, because that one is proven in
production: solve once, persist the clearance per host, and re-probe it
before use so a returning user never sees a verification window again.
"""

import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://public.animeout.xyz/"
_HOST = "public.animeout.xyz"


class AnimeOutSolver:
    """Owns the file host's clearance. Never raises: a failed solve means
    "no clearance", and the caller treats that as a no-stream."""

    def __init__(self, store=None):
        self._store = store
        self._clearance: dict | None = None

    @property
    def has_clearance(self) -> bool:
        """Sync view of the in-memory state — the capability flag reads
        this (it flips True after the first solve)."""
        return bool(self._clearance)

    async def clearance(self) -> dict | None:
        """A usable clearance or None. Order: in-memory, persisted
        (re-probed), then solve."""
        if self._clearance:
            return self._clearance
        if self._store is not None:
            try:
                stored = await self._store.get_clearance(_HOST)
            except Exception as ex:
                logger.debug("animeout clearance read failed: %s", ex)
                stored = None
            if stored and await self._probe(stored):
                self._clearance = stored
                logger.info("animeout reused the persisted clearance")
                return stored
        return await self.solve()

    def invalidate(self) -> None:
        """Drop the in-memory clearance so the next `clearance()` re-probes
        the stored cookie and, when it is dead, opens the solver again.
        The persisted cookie stays: the probe is its judge."""
        self._clearance = None

    async def solve(self) -> dict | None:
        """Run the challenge once. The window is the cost; the persisted
        cookie is what keeps it to once per expiry."""
        from state.app_state import state

        page = getattr(state, "page", None)
        if page is None:
            logger.info("animeout: no page to solve with")
            return None
        try:
            from services.webview_solver import WebViewSolver

            stored = await self._store.get_clearance(_HOST) if self._store else None
            prior_ua = (stored or {}).get("user_agent") or None
            cookies, user_agent = await WebViewSolver.solve_challenge(
                page, BASE_URL, user_agent=prior_ua
            )
        except Exception as ex:
            logger.info("animeout solve failed: %s", ex)
            return None
        if not cookies:
            return None
        clearance = {"cookies": cookies, "user_agent": user_agent}
        self._clearance = clearance
        if self._store is not None:
            try:
                await self._store.save_clearance(cookies, user_agent, _HOST)
                logger.info("animeout clearance persisted")
            except Exception as ex:
                logger.debug("animeout clearance save failed: %s", ex)
        return clearance

    async def _probe(self, clearance: dict) -> bool:
        """Is this clearance still good? One cheap GET decides.

        Note: public.animeout.xyz root / answers an nginx 403 Forbidden
        when cleared (directory listing is disabled). Only a real Cloudflare
        challenge (cf-mitigated header, or "Just a moment...") means the
        clearance is bad.
        """
        try:
            import primp

            async with primp.AsyncClient(impersonate="chrome", timeout=20.0) as client:
                resp = await client.get(
                    BASE_URL,
                    headers={
                        "User-Agent": clearance.get("user_agent") or "",
                        "Cookie": clearance.get("cookies") or "",
                    },
                )
        except Exception as ex:
            logger.debug("animeout clearance probe failed: %s", ex)
            return False

        headers = getattr(resp, "headers", None) or {}
        if headers.get("cf-mitigated") == "challenge":
            return False
        lowered = (getattr(resp, "text", "") or "").lower()
        return not any(
            marker in lowered
            for marker in (
                "just a moment",
                "cf-challenge",
                "attention required",
                "checking your browser",
            )
        )

    def file_headers(self, clearance: dict | None, referer: str | None = None) -> dict:
        """Headers for the walled host: the DDL public page referer plus the
        clearance when there is one. An empty dict means no clearance, and
        the caller must treat the file as unavailable."""
        headers = {"Referer": referer or "https://ddl.animeout.com/"}
        if clearance:
            cookies = clearance.get("cookies")
            if cookies:
                headers["Cookie"] = cookies
            ua = clearance.get("user_agent")
            if ua:
                headers["User-Agent"] = ua
        return headers
