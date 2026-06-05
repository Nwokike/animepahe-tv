import httpx
import logging

logger = logging.getLogger(__name__)

CURRENT_BUILD_NUMBER = 4
CONFIG_URL = "https://tv.kalerosemary7.workers.dev/config"
APP_KEY = "animepahe"


class UpdateService:
    def __init__(self):
        self.config_url = CONFIG_URL

    async def check_for_update(self) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                resp = await client.get(self.config_url)
                if resp.status_code == 200:
                    data = resp.json()
                    app_config = data.get(APP_KEY)
                    if not app_config:
                        return None
                    server_build = app_config.get("build_number", 0)
                    if server_build > CURRENT_BUILD_NUMBER:
                        return {
                            "version": app_config.get("version", "1.0.3"),
                            "release_notes": app_config.get("release_notes", ""),
                            "apk_url": app_config.get("update_url", ""),
                            "mandatory": app_config.get("mandatory", False),
                        }
        except Exception as ex:
            logger.error("Update check failed: %s", ex)
        return None
