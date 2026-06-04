import logging

import httpx

logger = logging.getLogger(__name__)

BASE = "https://animepahe.com"


class DDoSSolver:
    def __init__(self, timeout: int = 15):
        self._client: httpx.AsyncClient | None = None
        self._solved = False
        self._timeout = timeout

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
        try:
            client = self._get_client()
            resp = await client.get(
                f"{BASE}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            logger.info(
                "DDoS homepage status=%s len=%s", resp.status_code, len(resp.text)
            )
            logger.debug("DDoS cookies: %s", dict(resp.cookies))

            ddgid = resp.cookies.get("__ddgid_")
            if ddgid:
                logger.info("DDoS found __ddgid_ cookie: %s...", ddgid[:20])
                verify_resp = await client.get(
                    f"{BASE}/.well-known/ddos-guard/id/{ddgid}",
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": f"{BASE}/",
                        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    },
                )
                logger.info("DDoS verify status=%s", verify_resp.status_code)
                self._solved = True
                logger.info("DDoS solved successfully")
                return True
            else:
                logger.warning(
                    "DDoS no __ddgid_ cookie found — site may be using different protection. "
                    "Response start: %s",
                    resp.text[:200],
                )
        except httpx.RequestError as ex:
            logger.error("DDoS solve request failed: %s", ex)
        return False

    async def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> httpx.Response:
        logger.debug("DDoS GET %s", url)
        if not self._solved:
            logger.debug("DDoS not solved yet, attempting solve")
            await self.solve()
        client = self._get_client()
        merged = {"User-Agent": "Mozilla/5.0"}
        if headers:
            merged.update(headers)
        resp = await client.get(url, headers=merged, params=params, **kwargs)
        logger.debug(
            "DDoS GET %s -> status=%s len=%s", url, resp.status_code, len(resp.text)
        )
        return resp

    async def close(self):
        if self._client and not self._client.is_closed:
            logger.debug("DDoS closing client")
            await self._client.aclose()
