import httpx
import logging

logger = logging.getLogger(__name__)

CURRENT_BUILD_NUMBER = 1  # Standardized for current v1.0.0 release
UPDATE_JSON_URL = (
    "https://raw.githubusercontent.com/Nwokike/ktv-player/main/configs/config_a.json"
)
APK_DOWNLOAD_URL = "https://animepahetv.github.io/download/animepahe-tv.apk"


class UpdateService:
    def __init__(self):
        self.json_url = UPDATE_JSON_URL

    async def check_for_update(self) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(self.json_url)
                if resp.status_code == 200:
                    data = resp.json()
                    server_build = data.get("build_number", 0)
                    if server_build > CURRENT_BUILD_NUMBER:
                        return {
                            "version": data.get("version", "1.0.0"),
                            "release_notes": data.get("release_notes", ""),
                            "apk_url": APK_DOWNLOAD_URL,
                            "mandatory": data.get("mandatory", False),
                        }
        except Exception as ex:
            logger.error("Update check failed: %s", ex)
        return None
