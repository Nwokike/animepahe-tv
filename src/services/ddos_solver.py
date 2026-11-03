import asyncio
import logging
from urllib.parse import urlparse

import primp

from core.state import state
from services.store import get_store
from services.webview_solver import WebViewSolver

logger = logging.getLogger(__name__)

BASE = "https://animepahe.com"

# Cloudflare challenge / interstitial markers. Cloudflare's current Turnstile /
# Managed-Challenge most often returns HTTP 200 with a JS "Just a moment…" page
# (NOT a 403), so we must match on body content as well as status codes.
_CF_BODY_MARKERS = (
    "just a moment",
    "cf-mitigated",
    "challenges.cloudflare.com",
    "cf-challenge",
    "attention required",
    "enable javascript",
    "checking your browser",
    "ray id",  # footer signature on CF error/challenge pages
)

# Status codes Cloudflare uses to block or rate-limit.
_CF_BLOCK_STATUSES = (403, 429, 503)


def _looks_like_cf_challenge(text: str, status_code: int) -> bool:
    """Detect a Cloudflare challenge/block in any of its forms.

    Cloudflare frequently returns HTTP 200 with a JS interstitial instead of a
    clean 403, so a plain status check is not enough. This also catches the
    "valid 200 but actually a challenge HTML page" case that previously produced
    empty results ("zero items") because the body failed to parse as JSON.
    """
    if status_code in _CF_BLOCK_STATUSES:
        return True
    if not text:
        return False
    lowered = text.lower()
    # An HTML page from the API is always suspicious — the API returns JSON.
    # Combined with a marker it is almost certainly a challenge page.
    if "<html" in lowered and any(marker in lowered for marker in _CF_BODY_MARKERS):
        return True
    # Direct marker hit anywhere (covers title-only challenge pages too).
    return any(marker in lowered for marker in _CF_BODY_MARKERS)


class DDoSSolver:
    def __init__(self, timeout: int = 15):
        self._client: primp.AsyncClient | None = None
        self._solved = False
        # A verification window is a deliberate, user-visible act: it opens
        # only when the user asked for animepahe's own content. Background
        # work (probes, the episode checker, prefetch) can never trigger it.
        self.solve_allowed = False
        self._timeout = timeout
        self._base_url = "https://animepahe.com"
        self._cookies_str = ""
        self._store = get_store()
        # Concurrent callers once shared the solve: two parallel get()s
        # could open TWO verification windows.
        self._solve_lock = asyncio.Lock()
        self._user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def _get_client(self) -> primp.AsyncClient:
        if self._client is None:
            logger.debug("DDoS creating new primp session")
            self._client = primp.AsyncClient(
                timeout=self._timeout,
                impersonate="chrome",
            )
        return self._client

    @staticmethod
    def _clear_webview_cookies() -> bool:
        """Clear the Android system WebView's cookie jar.

        This is the critical step that was missing: the stale ``cf_clearance``
        cookie lives in the WebView's own cookie jar (``webview.db``), which is
        owned by the system WebView and is NOT cleared by deleting the app's
        ``files/`` or ``databases/`` directories. Only this call (or the OS
        "Clear Data" action, which does the same thing before process start)
        actually removes it. On desktop (no jnius) this is a no-op.

        Returns True if the jar was cleared, False if unavailable (desktop).
        """
        try:
            from jnius import autoclass  # type: ignore[import-not-found]
        except ImportError:
            logger.debug("DDoS _clear_webview_cookies: jnius unavailable (desktop), skipping")
            return False
        try:
            CookieManager = autoclass("android.webkit.CookieManager")
            cm = CookieManager.getInstance()
            # removeAllCookies accepts a ValueCallback<Boolean>; passing None
            # schedules the removal synchronously enough for our purposes.
            cm.removeAllCookies(None)
            cm.flush()
            logger.info("DDoS cleared WebView cookie jar (cf_clearance removed)")
            return True
        except Exception as ex:
            logger.error("DDoS failed to clear WebView cookie jar: %s", ex)
            return False

    async def solve(self) -> bool:
        if self._solved:
            logger.debug("DDoS already solved")
            return True
        if not self.solve_allowed:
            # The wall is real, but no user action asked for this content —
            # the caller treats it as "not available right now" instead of
            # opening a verification window.
            logger.info("DDoS solve suppressed: no user action requested it")
            return False
        logger.info("DDoS attempting to solve challenge")

        # 1. Resolve redirect BASE domain
        client = self._get_client()
        try:
            resp = await client.get("https://animepahe.com", follow_redirects=True)
            parsed = urlparse(str(resp.url))
            self._base_url = f"{parsed.scheme}://{parsed.netloc}"
            logger.info("DDoS dynamically resolved base URL: %s", self._base_url)
        except Exception as ex:
            logger.error("DDoS failed to resolve base URL, using fallback: %s", ex)
            self._base_url = "https://animepahe.com"

        # 2. Try the persisted clearance BEFORE showing any webview. This is
        #    the slow-boot fix: a returning user skips Turnstile entirely
        #    unless Cloudflare has expired the cookie.
        stored = await self._store.get_clearance()
        if stored:
            stored_ua = stored.get("user_agent") or self._user_agent
            stored_cookies = stored.get("cookies") or ""
            if await self._probe_api(stored_ua, stored_cookies):
                self._user_agent = stored_ua
                self._cookies_str = stored_cookies
                self._solved = True
                logger.info("DDoS reused persisted clearance — no challenge shown")
                return True
            logger.info("DDoS persisted clearance expired, solving fresh")
            await self._store.clear_clearance()

        # 3. Trigger WebViewSolver
        page = getattr(state, "page", None)
        if page is None:
            logger.error("DDoS state.page is not set, cannot solve Cloudflare challenge")
            return False

        stored = await self._store.get_clearance() if self._store is not None else None
        prior_ua = (stored or {}).get("user_agent") or self._user_agent or None
        try:
            cookies, ua = await WebViewSolver.solve_challenge(
                page, self._base_url, user_agent=prior_ua
            )
            self._cookies_str = cookies
            self._user_agent = ua
            self._solved = True
            await self._store.save_clearance(cookies, ua)
            logger.info("DDoS solved successfully. Clearance persisted durably.")
            return True
        except Exception as ex:
            logger.error("DDoS solve challenge failed: %s", ex)
            return False

    async def _probe_api(self, user_agent: str, cookies: str) -> bool:
        """Is this clearance still good? One cheap API call decides."""
        try:
            client = self._get_client()
            headers = {"User-Agent": user_agent}
            if cookies:
                headers["Cookie"] = cookies
            resp = await client.get(
                f"{self._base_url}/api",
                params={"m": "airing", "page": "1"},
                headers=headers,
            )
            if resp.status_code != 200:
                return False
            if _looks_like_cf_challenge(resp.text, resp.status_code):
                return False
            body = resp.text or ""
            return body.lstrip()[:1] == "{"  # the API always answers JSON
        except Exception as ex:
            logger.debug("DDoS clearance probe failed: %s", ex)
            return False

    async def _request(
        self,
        method: str,
        client: primp.AsyncClient,
        url: str,
        headers: dict,
        params: dict | None,
        **kwargs,
    ) -> primp.AsyncResponse:
        if method == "GET":
            return await client.get(url, headers=headers, params=params, **kwargs)
        return await client.request(method, url, headers=headers, params=params, **kwargs)

    async def _ensure_solved(self) -> None:
        """One solve gate for every caller (the get() rewrite branch and
        the plain path used to EACH call solve(), so an unsolved state
        could open the verification window twice). The lock also makes
        concurrent callers share one solve instead of racing."""
        if self._solved:
            return
        async with self._solve_lock:
            if not self._solved:
                await self.solve()

    async def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> primp.AsyncResponse:
        logger.debug("DDoS GET %s", url)

        # Check if URL references hardcoded animepahe.com, rewrite to resolved base url
        if "animepahe.com" in url:
            # Solve first: the dynamic base URL (and the clearance) come
            # from it, and the old code called solve() here AND again in
            # the branch below — two solves, two windows when the first
            # failed.
            await self._ensure_solved()
            url = url.replace("https://animepahe.com", self._base_url)
        else:
            await self._ensure_solved()

        client = self._get_client()
        merged = {"User-Agent": self._user_agent}
        if self._cookies_str:
            merged["Cookie"] = self._cookies_str
        if headers:
            merged.update(headers)

        logger.debug(
            "Outbound request to %s (cookie=%s)",
            url,
            "redacted" if "Cookie" in merged else "none",
        )

        resp = await self._request("GET", client, url, merged, params, **kwargs)
        logger.debug("DDoS GET %s -> status=%s len=%s", url, resp.status_code, len(resp.text))

        # Detect a Cloudflare challenge in ANY of its forms (not just 403).
        # This covers the common "HTTP 200 + JS interstitial" case that used to
        # silently produce empty results ("zero items") because the dead
        # cf_clearance cookie was being reused indefinitely.
        if _looks_like_cf_challenge(resp.text, resp.status_code):
            logger.warning(
                "DDoS detected Cloudflare challenge (status=%s), clearing stale "
                "cookie and re-solving...",
                resp.status_code,
            )
            self._clear_webview_cookies()
            self._solved = False
            self._cookies_str = ""
            await self._store.clear_clearance()
            # The REUSED primp client's cookie_store still holds the dead
            # cf_clearance and would resend it on the re-solve — rebuild
            # the client (its pool) so the fresh solve starts clean.
            await self.close()
            await self._ensure_solved()

            # Re-build headers and retry once with the fresh clearance
            merged["User-Agent"] = self._user_agent
            if self._cookies_str:
                merged["Cookie"] = self._cookies_str
            else:
                merged.pop("Cookie", None)
            resp = await self._request("GET", client, url, merged, params, **kwargs)
            logger.debug(
                "DDoS RETRIED GET %s -> status=%s len=%s",
                url,
                resp.status_code,
                len(resp.text),
            )

        return resp

    async def reset(self):
        """Reset in-memory clearance state AND the WebView cookie jar.

        Clearing the cookie jar here is essential: ``reset()`` is called by the
        in-app "Verify" button (via ``_safe_clear_cf``) and by the self-healing
        re-solve path. Without it the stale ``cf_clearance`` would remain in the
        jar and be reused on the next solve attempt — which is the original
        "still using the old thing" bug.
        """
        logger.info("DDoS resetting solver state + clearing WebView cookies")
        self._solved = False
        self._cookies_str = ""
        await self._store.clear_clearance()
        self._clear_webview_cookies()
        await self.close()
        self._client = None

    async def close(self):
        if self._client:
            logger.debug("DDoS closing session")
            # primp's AsyncClient has no public close() method; use __aexit__
            # to release the underlying connection pool.
            await self._client.__aexit__(None, None, None)
            self._client = None
