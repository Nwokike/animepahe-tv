import logging
from urllib.parse import urlparse
import httpx
from core.state import state
from services.webview_solver import WebViewSolver

logger = logging.getLogger(__name__)

BASE = "https://animepahe.com"

class DDoSSolver:
    def __init__(self, timeout: int = 15):
        self._client: httpx.AsyncClient | None = None
        self._solved = False
        self._timeout = timeout
        self._base_url = "https://animepahe.com"
        self._cookies_str = ""
        self._user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            logger.debug("DDoS creating new httpx client")
            self._client = httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            )
        return self._client

    async def solve(self) -> bool:
        if self._solved:
            logger.debug("DDoS already solved")
            return True
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

        # 2. Trigger WebViewSolver
        page = getattr(state, "page", None)
        if page is None:
            logger.error("DDoS state.page is not set, cannot solve Cloudflare challenge")
            return False

        try:
            cookies, ua = await WebViewSolver.solve_challenge(page, self._base_url)
            self._cookies_str = cookies
            self._user_agent = ua
            self._solved = True
            logger.info("DDoS solved successfully. User-Agent set, Cookies captured.")
            return True
        except Exception as ex:
            logger.error("DDoS solve challenge failed: %s", ex)
            return False

    async def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> httpx.Response:
        logger.debug("DDoS GET %s", url)
        
        # Check if URL references hardcoded animepahe.com, rewrite to resolved base url
        if "animepahe.com" in url:
            if not self._solved:
                # Solve once to get active base URL redirect
                await self.solve()
            url = url.replace("https://animepahe.com", self._base_url)

        if not self._solved:
            logger.debug("DDoS not solved yet, attempting solve")
            await self.solve()

        client = self._get_client()
        merged = {"User-Agent": self._user_agent}
        if self._cookies_str:
            merged["Cookie"] = self._cookies_str
        if headers:
            merged.update(headers)
            
        logger.info("Outbound request to %s with headers: %s", url, merged)

        resp = await client.get(url, headers=merged, params=params, **kwargs)
        logger.debug(
            "DDoS GET %s -> status=%s len=%s", url, resp.status_code, len(resp.text)
        )
        
        # Detect expired cf_clearance cookie or if we hit Cloudflare challenge screen
        if resp.status_code == 403 and ("challenges.cloudflare.com" in resp.text or "cf-challenge" in resp.text):
            logger.warning("DDoS detected Cloudflare challenge (403), re-solving...")
            self._solved = False
            await self.solve()
            
            # Re-build headers and retry once
            merged["User-Agent"] = self._user_agent
            if self._cookies_str:
                merged["Cookie"] = self._cookies_str
            resp = await client.get(url, headers=merged, params=params, **kwargs)
            logger.debug(
                "DDoS RETRIED GET %s -> status=%s len=%s", url, resp.status_code, len(resp.text)
            )

        return resp

    async def close(self):
        if self._client and not self._client.is_closed:
            logger.debug("DDoS closing client")
            await self._client.aclose()
