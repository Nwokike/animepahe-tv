import httpx

BASE = "https://animepahe.com"


class DDoSSolver:
    def __init__(self, timeout: int = 15):
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self._solved = False

    def solve(self) -> bool:
        if self._solved:
            return True
        try:
            self.client.get(
                f"{BASE}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            ddgid = self.client.cookies.get("__ddgid_")
            if ddgid:
                self.client.get(
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

    def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ) -> httpx.Response:
        if not self._solved:
            self.solve()
        merged = {"User-Agent": "Mozilla/5.0"}
        if headers:
            merged.update(headers)
        return self.client.get(url, headers=merged, params=params, **kwargs)

    def close(self):
        self.client.close()
