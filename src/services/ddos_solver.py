import httpx


BASE = "https://animepahe.com"


class DDoSSolver:
    def __init__(self, timeout: int = 15):
        self._client: httpx.AsyncClient | None = None
        self._solved = False
        self._timeout = timeout

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            )
        return self._client

    async def solve(self) -> bool:
        if self._solved:
            return True
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
            ddgid = resp.cookies.get("__ddgid_")
            if ddgid:
                await client.get(
                    f"{BASE}/.well-known/ddos-guard/id/{ddgid}",
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": f"{BASE}/",
                        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    },
                )
                self._solved = True
                return True
        except httpx.RequestError:
            pass
        return False

    async def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> httpx.Response:
        if not self._solved:
            await self.solve()
        client = self._get_client()
        merged = {"User-Agent": "Mozilla/5.0"}
        if headers:
            merged.update(headers)
        return await client.get(url, headers=merged, params=params, **kwargs)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
