
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

- **Browse & Search** — Submit-driven search with debounced recent-search suggestions, paginated results, and real empty/error states.
- **Continue Watching** — A shelf on Home that picks up exactly where you stopped; positions persist across launches.
- **In-app Player** — `flet-video` (mpv) with a quality selector when the master playlist offers variants, resume from your saved position, next/previous episode buttons, and a 10s-network-timeout watchdog so a dead stream fails into Retry instead of hanging.
- **Offline Downloads** — Save any episode (or a whole series) for offline: parallel segments, `Range`-resumable, cancel-safe, grouped by series with progress and sizes. Downloaded episodes play from the same player with resume intact.
- **All four ad formats** — inline + sticky banners, interstitial between episodes, rewarded early access, and app-open on cold start, on phone and Android TV.
- **Live Activity Terminal** — Settings → Open Terminal: the last 500 engine/network/UI log lines with telemetry, for diagnosing Cloudflare/kwik/download issues.
- **TV Remote Navigation** — Left navigation rail on TV and wide screens, bottom bar on phones, D-pad focus order with an autofocus back handler; no primary nav at the bottom on TV.
- **Adaptive Scraper Waterfall** — Multi-strategy resolution: JSON API → HTML parsing (stdlib) → regex extraction → Dean Edwards JS unpack, each layer with tested fallbacks.
- **Persistent Cloudflare session** — the clearance cookie is stored durably and reused, so returning boots skip the Turnstile webview.
- **System Theme Awareness** — Dark → Light → System cycling.
- **Adaptive Layout** — Rail on wide/TV, bottom bar on phones; glass cards with focus-ring reserves that never shift layout.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Flet 1.0.4 (Python → Flutter), `@ft.component` screens |
| Video Engine | `flet-video` 1.0.4 (mpv backend) |
| Network | `primp` (async, Chrome impersonation for Cloudflare, `Range`-capable streaming) |
| Cloudflare | `flet-webview-all` on Android/iOS/TV; pywebview subprocess for desktop dev |
| Durable state | JSON store in `FLET_APP_STORAGE_DATA` (history, continue watching, positions, clearance, downloads) |
| Stream Resolver | Dean Edwards JS unpack + regex + stdlib HTML parsing |
| Ads | `flet-yandex-ads` (banner, interstitial, rewarded, app open) |
| State Management | `@observable` AppState + context providers + a controller bridge |
| Navigation | Component-state branches (tabs / detail / player), rail/bar adaptive |
| Diagnostics | In-memory ring-buffer log handler → Activity Terminal |
| Storage | No Android permissions needed — app-private dirs only |

### Project Structure

```text
src/
├── main.py                    # AppController (services + data actions) + entry
├── app_shell.py               # Adaptive shell: rail/bottom nav, tab + detail + player branches
├── state/
│   ├── app_state.py           # AppStateCtx = ft.create_context(state)
│   └── controller_ctx.py      # ControllerMethods bridge
├── screens/
│   ├── home_screen.py         # Promo hero, continue watching, latest grid, banners
│   ├── search_screen.py       # Submit-driven search + suggestions + pager
│   ├── anime_detail_screen.py # Backdrop, poster, metadata, episode grid, download buttons
│   ├── downloads_screen.py    # Series-grouped offline episodes
│   └── settings_screen.py     # Activity terminal + about
├── components/
│   ├── banner_ad.py           # Canonical build_banner_ad()
│   ├── cross_promo.py         # Hero + 'more from us' cross-promo
│   └── player/
│       └── immersive_player.py # ImmersivePlayer: mpv props, overlay, watchdog, resume
├── hooks/
│   ├── use_debounce.py        # Debounced value hook
│   └── use_focus_scope.py     # Back/Escape with autofocus (TV remotes)
├── services/
│   ├── animepahe.py           # Scraper (API → HTML → regex → unpack)
│   ├── ddos_solver.py         # Cloudflare session + durable clearance
│   ├── webview_solver.py      # WebView solver (mobile: flet-webview-all; desktop: pywebview)
│   ├── desktop_cf_solver.py   # Desktop pywebview subprocess
│   ├── kwik_resolver.py       # kwik m3u8 resolution with referer + clearance
│   ├── cache.py               # TTL JSON cache (regenerable tier)
│   ├── store.py              # Durable JSON store (search/continue/positions/clearance/downloads)
│   ├── downloads.py           # DownloadManager: parallel, resumable, manifest-gated
│   ├── ads.py                 # Yandex ad service + interstitial/rewarded/app-open
│   └── update_service.py      # Worker-based update check
└── core/
    ├── state.py               # @observable AppState
    ├── theme.py               # Palette + glass helpers
    ├── constants.py           # Labels, app name/version
    ├── logger_handler.py      # Ring-buffer logging for the terminal
    └── tasks.py               # spawn() task helper
├── services/
│   ├── animepahe.py        # Multi-strategy scraper (API → HTML → regex)
│   ├── kwik_resolver.py    # Dean Edwards JS unpacker + m3u8 extractor
│   ├── ddos_solver.py      # Cloudflare challenge bypass
│   └── cache.py            # Async SQLite cache with TTL
└── components/
    └── player/


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
