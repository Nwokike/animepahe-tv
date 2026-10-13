import logging
import re
import primp

logger = logging.getLogger(__name__)

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
    def __init__(self, ddos_solver=None):
        self._client: primp.AsyncClient | None = None
        # Optional session owner: when the scraper passes its DDoSSolver in,
        # requests carry the Cloudflare clearance the CDN expects.
        self._ddos = ddos_solver

    def _get_client(self) -> primp.AsyncClient:
        if self._client is None:
            self._client = primp.AsyncClient(timeout=15, impersonate="chrome")
        return self._client

    def _headers(self, kwik_url: str) -> dict:
        # The Referer follows the issued URL's host — the kwik family
        # rotates (kwik.cx -> kwik.si -> kwik.pw documented) and a stale
        # host Referer is exactly what CDNs reject.
        import re as _re

        host_m = _re.search(r"https?://(kwik\.[a-z]+)/", kwik_url)
        referer = f"https://{host_m.group(1)}/" if host_m else "https://kwik.cx/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
        }
        ddos = self._ddos
        if ddos is not None and getattr(ddos, "_solved", False):
            cookies = getattr(ddos, "_cookies_str", "")
            if cookies:
                headers["Cookie"] = cookies
        return headers

    async def resolve(self, kwik_url: str) -> str | None:
        logger.info("resolve(%s)", kwik_url)
        m3u8 = await self._resolve_dean(kwik_url)
        if m3u8:
            logger.info("dean resolved: %s", m3u8)
            return m3u8
        logger.info("dean returned None, trying direct scan")
        m3u8 = await self._resolve_direct_scan(kwik_url)
        if m3u8:
            logger.info("direct scan resolved: %s", m3u8)
        else:
            logger.info("direct scan also returned None")
        return m3u8

    async def _resolve_dean(self, kwik_url: str) -> str | None:
        client = self._get_client()
        logger.info("fetching %s", kwik_url)
        resp = await client.get(kwik_url, headers=self._headers(kwik_url))
        logger.info("status=%s, len=%s", resp.status_code, len(resp.text))
        if resp.status_code != 200:
            return None
        urls = _dean_unpack(resp.text)
        logger.info("dean unpack found %d urls: %s", len(urls), urls)
        for url in urls:
            if await self._verify(url, kwik_url):
                logger.info("verify OK: %s", url)
                return url
            logger.info("verify FAILED: %s", url)
        return None

    async def _resolve_direct_scan(self, kwik_url: str) -> str | None:
        client = self._get_client()
        resp = await client.get(kwik_url, headers=self._headers(kwik_url))
        logger.info("direct_scan status=%s, len=%s", resp.status_code, len(resp.text))
        if resp.status_code != 200:
            return None
        urls = M3U8_PATTERN.findall(resp.text)
        logger.info("direct_scan found %d urls: %s", len(urls), urls)
        for url in urls:
            if await self._verify(url, kwik_url):
                logger.info("direct_scan verify OK: %s", url)
                return url
            logger.info("direct_scan verify FAILED: %s", url)
        return None

    async def _verify(self, url: str, referer: str) -> bool:
        try:
            client = self._get_client()
            resp = await client.head(url, headers=self._headers(url), timeout=5)
            ct = resp.headers.get("content-type", "")
            result = resp.status_code == 200 and "mpegurl" in ct
            logger.info(
                "verify HEAD %s -> %s ct=%s result=%s",
                url,
                resp.status_code,
                ct,
                result,
            )
            return result
        except Exception as ex:
            logger.info("verify HEAD %s -> RequestError: %s", url, ex)
            return False

    async def close(self):
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
