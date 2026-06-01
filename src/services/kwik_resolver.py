import re
import httpx

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
KWIK_PATTERN = re.compile(
    r"\}\('(.*?)',\s*(\d+|\[.*?\])\s*,\s*(\d+)\s*,\s*'(.*?)'\.split\('\|'\)",
    re.DOTALL,
)
M3U8_PATTERN = re.compile(r"https?://[^\'\"\s<>]+\.m3u8[^\s\'\"\)<]*")


def _unbase(value: str, radix: int) -> int:
    result = 0
    for c in value:
        result = result * radix + ALPHABET.index(c)
    return result


def _dean_unpack(html_text: str) -> list[str]:
    urls = []
    for match in KWIK_PATTERN.finditer(html_text):
        payload = match.group(1)
        radix_str = match.group(2)
        symtab = match.group(4).split("|")
        radix = 62 if radix_str.startswith("[") else int(radix_str)
        payload = payload.replace("\\\\", "\\").replace("\\'", "'")

        def _replace(m: re.Match) -> str:
            word = m.group(0)
            try:
                idx = _unbase(word, radix)
                if 0 <= idx < len(symtab):
                    return symtab[idx] or word
            except (ValueError, IndexError):
                pass
            return word

        unpacked = re.sub(r"\b\w+\b", _replace, payload)
        urls.extend(M3U8_PATTERN.findall(unpacked))
    return urls


class KwikResolver:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15, follow_redirects=True)
        return self._client

    async def resolve(self, kwik_url: str) -> str | None:
        m3u8 = await self._resolve_dean(kwik_url)
        if m3u8:
            return m3u8
        return await self._resolve_direct_scan(kwik_url)

    async def _resolve_dean(self, kwik_url: str) -> str | None:
        client = self._get_client()
        resp = await client.get(
            kwik_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": kwik_url,
            },
        )
        if resp.status_code != 200:
            return None
        urls = _dean_unpack(resp.text)
        for url in urls:
            if await self._verify(url, kwik_url):
                return url
        return None

    async def _resolve_direct_scan(self, kwik_url: str) -> str | None:
        client = self._get_client()
        resp = await client.get(
            kwik_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": kwik_url,
            },
        )
        if resp.status_code != 200:
            return None
        urls = M3U8_PATTERN.findall(resp.text)
        for url in urls:
            if await self._verify(url, kwik_url):
                return url
        return None

    async def _verify(self, url: str, referer: str) -> bool:
        try:
            client = self._get_client()
            resp = await client.head(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": referer},
                timeout=5,
            )
            return resp.status_code == 200 and "mpegurl" in resp.headers.get(
                "content-type", ""
            )
        except httpx.RequestError:
            return False

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
