# AnimePahe TV v2.0.0

The big multi-source rewrite. Instead of a single scraped site, the app now ships **four independent backends — AniKato, KayoAnime, AnimePahe and AnimeOut** — one chosen at startup (stored pin, or automatic health race), each with its own catalog, artwork, stream resolution and Cloudflare story. The app then *is* that source.

## Highlights since 1.0.9

- **Multi-platform sources** — AniKato (encrypted MegaPlay manifests), KayoAnime (Google Drive), AnimePahe (Kwik unpack behind Cloudflare), AnimeOut (DDL chain); a provider router with per-provider health shown in Settings.
- **Real in-app player** — `flet-video` (mpv) with quality selection from every HLS variant the source actually serves, audio (SUB/DUB) selection, subtitles (including offline sidecars saved with downloads), resume-from-position, next/previous episode, a watchdog that turns dead streams into Retry, SafeArea-aware controls, and one-press Back even from fullscreen. An optional external-player (KTV) handoff stays available in Settings, off by default, with a proper install dialog when no handler exists.
- **Offline downloads** — single episodes or whole series, parallel segments with 429-aware throttling, Range-resumable, cancel/pause-safe, grouped by series with live MB progress (verified totals for direct files, bytes-done for HLS), "Interrupted — tap Resume" after the app is killed, and downloaded episodes play straight from disk when you tap them.
- **Native notifications** — new episodes for followed anime, download progress/completion, and update alerts; taps route into the app. Wake lock keeps the screen on during playback and downloads.
- **TV-first navigation** — D-pad focus with per-state rings, one Back/Escape funnel, adaptive rail/bar layout, and layout that follows the artwork shape.
- **Continue watching & follows** — positions persist across launches; the follows checker alerts on new episodes.
- **Smaller APKs** — native libraries are stored compressed (`legacy_packaging`), keeping split APKs around 42–45 MB.
- **Flet 1.1.0-dev line** — the app is built on the current flet dev packages with the full API surface verified against the installed venv.

## APKs

Split per ABI: `animepahe-tv-arm64-v8a.apk` (~43 MB), `animepahe-tv-armeabi-v7a.apk`, `animepahe-tv-x86_64.apk`.

## Notes

- 670 automated tests pass; the whole ruff gate is clean.
- Built by GitHub Actions from tag `v2.0.0` (build number 11).
