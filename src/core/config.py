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
