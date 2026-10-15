import logging
import primp

logger = logging.getLogger(__name__)

CURRENT_BUILD_NUMBER = 10
CONFIG_URL = "https://tv.kalerosemary7.workers.dev/config"
APP_KEY = "animepahe"


def _safe_https_url(value) -> str:
    """Only https URLs pass, with a bounded length. The update URL is
    handed to the OS launcher verbatim — a compromised or malformed
    worker config could otherwise drive an arbitrary scheme (intent
    abuse). https-only also matches the config host itself."""
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if not url.startswith("https://") or len(url) > 2048:
        return ""
    return url


class UpdateService:
    def __init__(self):
        self.config_url = CONFIG_URL

    async def check_for_update(self) -> dict | None:
        try:
            async with primp.AsyncClient(timeout=3.0) as client:
                resp = await client.get(self.config_url)
                if resp.status_code == 200:
                    data = resp.json()
                    # A non-dict payload (a CDN error page answering 200
                    # with HTML) used to raise AttributeError below.
                    if not isinstance(data, dict):
                        return None
                    app_config = data.get(APP_KEY)
                    if not isinstance(app_config, dict) or not app_config:
                        return None
                    # A string build number used to raise TypeError on
                    # the compare — coerce, and fail closed (no update).
                    try:
                        server_build = int(app_config.get("build_number", 0))
                    except (TypeError, ValueError):
                        logger.info("update config: bad build_number, ignoring")
                        return None
                    if server_build > CURRENT_BUILD_NUMBER:
                        return {
                            "version": str(app_config.get("version", "1.0.9")),
                            "release_notes": str(app_config.get("release_notes", "")),
                            "apk_url": _safe_https_url(app_config.get("update_url")),
                            "mandatory": bool(app_config.get("mandatory", False)),
                        }
        except Exception as ex:
            logger.error("Update check failed: %s", ex)
        return None
