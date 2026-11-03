import os

# Play Store URL for KTV Player
KTV_PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.ktvplayer"

# Uptodown mirror URL
KTV_UPTODOWN_URL = "https://ktv-player.uptodown.com/android"

# Deep link scheme for KTV Player
KTV_DEEP_LINK_SCHEME = "ktv://play?url="

# Support route (public issues tracker — no personal contact details ship
# in the binary; see components/support_dialog.py)
SUPPORT_URL = "https://github.com/Nwokike/animepahe-tv/issues"

# Provider router tuning (values from the resilience research; see
# docs/decisions.md). Providers are never locked: failover is per request.
BREAKER_FAIL_THRESHOLD = 3  # consecutive failures -> OPEN
BREAKER_OPEN_SECONDS = 30.0  # first cooldown; only failed trials double it
BREAKER_OPEN_MAX_SECONDS = 300.0
STARTUP_PROBE_BUDGET = 12.0  # wall-clock cap for the parallel probe race

# Provider cache TTLs (seconds), per collection.
CACHE_TTL_LATEST = 300
CACHE_TTL_SEARCH = 600
CACHE_TTL_EPISODES = 3600

# The home-feed paint-first snapshot (cache tier). Longer than any provider
# TTL on purpose: it is not truth, it is the catalog the user saw last —
# shown instantly at launch while the live fetch revalidates behind it.
HOME_FEED_SNAPSHOT_TTL = 21600  # 6 h

# Provider endpoints (the complete bench; see docs/decisions.md).
ANIMEOUT_API = "https://animeout.xyz/wp-json/wp/v2"

# Kayoanime (WordPress + Google Drive). The Drive "web key" is Google's
# own public client key (shipped inside drive.google.com's own app) with
# its HTTP-referrer restriction — the documented keyless listing route.
KAYOANIME_API = "https://kayoanime.com/wp-json/wp/v2"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_WEB_KEY = os.getenv("DRIVE_WEB_KEY", "AIzaSyC1qbk75NzWBvSaDh6KnsjjA9pIrP4lYIE")
DRIVE_REFERER = "https://drive.google.com/"
