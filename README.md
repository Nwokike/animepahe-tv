
<p align="center">
  <img src="src/assets/icon.png" alt="AnimePahe TV" width="140" />
</p>

<h1 align="center">AnimePahe TV</h1>

<p align="center">
  A high-performance, client-side anime streaming application with TV-optimized navigation, multi-quality stream resolution, and a responsive glassmorphic UI. Built with Python and Flet.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows11&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/Android-3DDC84?style=flat-square&logo=android&logoColor=white" alt="Android" />
  <br>
  <img src="https://img.shields.io/badge/Built%20with-Flet%200.85-00B0FF?style=flat-square" alt="Built with Flet" />
</p>

---

## Download

Get the latest version of AnimePahe TV. If you aren't sure which Android version to pick, choose the **Universal** APK.

| Platform | Download | Size | Notes |
|:--------:|:--------:|:----:|:------|
| 🤖 **Android (ARM64)** | [**animepahe-tv-arm64-v8a.apk**](https://github.com/Nwokike/animepahe-tv/releases/latest/download/animepahe-tv-arm64-v8a.apk) | ~31 MB | For modern 64-bit Android TVs and smartphones |
| 🤖 **Android (ARM32)** | [**animepahe-tv-armeabi-v7a.apk**](https://github.com/Nwokike/animepahe-tv/releases/latest/download/animepahe-tv-armeabi-v7a.apk) | ~30 MB | For older 32-bit Android devices and older Firesticks |
| 🤖 **Android (x86_64)** | [**animepahe-tv-x86_64.apk**](https://github.com/Nwokike/animepahe-tv/releases/latest/download/animepahe-tv-x86_64.apk) | ~31 MB | For Android emulators / ChromeOS |
| 🤖 **Android (Universal)** | [**animepahe-tv.apk**](https://github.com/Nwokike/animepahe-tv/releases/latest/download/animepahe-tv.apk) | ~76 MB | Works on all devices (use if hardware type is unknown) |

---

## Screenshots

*Coming soon.*

---

## Features

- **Browse & Search** — Paginated anime discovery with real-time search and cover art previews.
- **Episode Grid** — Snapshot-based episode cards with pagination, duration display, and filler indicators.
- **Multi-Quality Stream Resolution** — Automatic best-quality selection from available resolutions (360p–1080p).
- **TV Remote Navigation** — Full D-pad support with sequential tab indexing, focus ring highlights, and hover effects. Optimized for Android TV, Fire Stick, and Leanback.
- **Adaptive Scraper Waterfall** — Multi-strategy content resolution: JSON API → HTML parsing → regex extraction → Dean Edwards JS unpack. Each layer has tested fallbacks.
- **System Theme Awareness** — Automatically follows device light/dark mode with manual override.
- **Responsive Layout** — SafeArea-wrapped, ListView-scrollable views that adapt from phone to TV screen sizes.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Flet 0.85 (Python → Flutter) |
| Video Engine | `flet-video` (libmpv backend) |
| Network | `httpx` (async, connection pooling, 15s timeout) |
| Cache | `aiosqlite` (WAL-mode SQLite with TTL expiration) |
| Stream Resolver | Dean Edwards JS unpack + regex + BeautifulSoup HTML parsing |
| DDoS Bypass | Cloudflare challenge solver with JA3 fingerprint rotation |
| State Management | Flet `@observable` reactive state with page-scoped view builders |
| Routing | Flet declarative routing with base64-encoded URL parameters |
| Navigation | Sequential `tab_index` D-pad focus chain across all interactive elements |

### Project Structure

```text
src/
├── main.py                 # App entry, routing, global back handler, theme init
├── core/
│   ├── config.py           # Feature flags (internal/external player toggle)
│   ├── state.py            # @observable reactive state (AppState)
│   ├── theme.py            # Light/dark color schemes, glass bg helpers
│   └── focus_manager.py    # Global keyboard/back event handler for TV remotes
├── views/
│   ├── splash.py           # Animated splash with auto-transition
│   ├── home.py             # Latest releases grid + pagination + D-pad focus
│   ├── search.py           # Search bar + results grid + D-pad focus
│   ├── anime_detail.py     # Anime info + episode grid + pagination + D-pad
│   └── player.py           # flet-video player with stream resolution overlay
├── services/
│   ├── animepahe.py        # Multi-strategy scraper (API → HTML → regex)
│   ├── kwik_resolver.py    # Dean Edwards JS unpacker + m3u8 extractor
│   ├── ddos_solver.py      # Cloudflare challenge bypass
│   └── cache.py            # Async SQLite cache with TTL
└── components/
    └── player/
        └── immersive_player.py  # Full-screen player wrapper (future)

```

### Stream Resolution Pipeline

```text
User clicks episode
    │
    ▼
scraper.sources() ─────────────────────────────────┐
    │                                               │
    ├── _sources_data_src()  ← parse data-src attrs │
    │                                               │
    └── _sources_regex()     ← regex kwik URLs     │
                                                    │
                                                    ▼
best = max(sources, key=resolution)                 │
    │                                               │
    ▼                                               │
kwik.resolve() ─────────────────────────────────────┤
    │                                               │
    ├── _resolve_dean()   ← unpack JS, find m3u8   │
    │                                               │
    └── _resolve_direct() ← regex scan HTML         │
                                                    │
                                                    ▼
video.playlist = [VideoMedia(m3u8, headers)] ───────┘

```

### D-Pad Navigation Model

Every interactive element is assigned a sequential `tab_index` so Android's `FocusFinder` can navigate with arrow keys:

```text
Home:    Search(1) → Theme(2) → Cards(3..N) → Prev(N+1) → Next(N+2)
Search:  Back(1) → Cards(2..N)
Detail:  Back(1) → Episodes(2..N) → Prev(N+1) → Next(N+2)
Player:  Back(1)

```

Focus highlights are applied via `on_focus`/`on_blur` callbacks that animate scale, shadow, and border color.

## Development

```bash
# Clone and set up
git clone [https://github.com/Nwokike/animepahe-tv.git](https://github.com/Nwokike/animepahe-tv.git)
cd animepahe-tv
uv sync

# Run in development
flet run

# Build for Android
flet build apk --release

# Build for Windows
flet build windows --release

```

## Legal Disclaimer

AnimePahe TV is a media player and network utility. It does not host, store, or distribute any copyrighted content. The app interfaces with publicly available APIs and web pages. Users are solely responsible for ensuring compliance with applicable laws and terms of service in their jurisdiction.
