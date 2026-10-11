# App configuration - toggle these before release

USE_EXTERNAL_PLAYER = True

# Play Store URL for KTV Player
KTV_PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.ktvplayer"

# Uptodown mirror URL
KTV_UPTODOWN_URL = "https://ktv-player.uptodown.com/android"

# Deep link scheme for KTV Player
KTV_DEEP_LINK_SCHEME = "ktv://play?url="

# Fake player names to show in dialog (all buttons go to KTV Player)
EXTERNAL_PLAYER_NAMES = [
    "KTV Player",
    "MX Player",
    "YTV Player",
]

# Cloudflare Worker for dynamic redirects and update checks
WORKER_BASE_URL = "https://tv.kalerosemary7.workers.dev"

# Support route (public issues tracker — no personal contact details ship
# in the binary; see components/support_dialog.py)
SUPPORT_URL = "https://github.com/Nwokike/animepahe-tv/issues"

# Provider router tuning (values from the resilience research; see
# docs/decisions.md). Providers are never locked: failover is per request.
BREAKER_FAIL_THRESHOLD = 3       # consecutive failures -> OPEN
BREAKER_OPEN_SECONDS = 30.0      # first cooldown; only failed trials double it
BREAKER_OPEN_MAX_SECONDS = 300.0
BREAKER_HALF_OPEN_TRIALS = 1     # trial requests when HALF_OPEN
STARTUP_PROBE_BUDGET = 12.0      # wall-clock cap for the parallel probe race

# Provider cache TTLs (seconds), per collection.
CACHE_TTL_LATEST = 300
CACHE_TTL_SEARCH = 600
CACHE_TTL_EPISODES = 3600
