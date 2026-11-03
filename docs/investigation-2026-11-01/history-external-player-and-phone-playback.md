# Git History: External Player (KTV) & Phone Playback Regression

**Date:** 2026-11-02 · Tags examined: v1.0.9-final (flet 0.85.3) vs HEAD (flet 1.0.4)

## 1. v1.0.9 external flow (worked on phone)

- `_play_episode_external` (v1.0.9 `src/main.py:724-760`): sources → sorted by resolution desc → choices → quality dialog when >1 → `_resolve_and_launch_external`.
- `_resolve_and_launch_external` (`:762-785`): `kwik.resolve(source.url)` → **raw m3u8** (NOT a proxy URL) → `launch_external(page, m3u8, episode_title(...))`.
- `build_deep_link` (`external_player.py:53-58`): `ktv://play?url=<base64 m3u8>&title=<url-encoded>`; `KTV_DEEP_LINK_SCHEME = "ktv://play?url="`.
- `launch_external` (v1.0.9 `:60-85`): NO `can_launch_url` — single `shared.launch_url` attempt; on False → **always** show the install dialog.
- Install dialog (`:14-65`): "Install Player" + "Not Now" / "Get it on Play Store" / "Download Uptodown" — unchanged to this day (`external_player.py:42-96`).
- v1.0.9 `shared_services.launch_url`: `asyncio.wait_for(..., timeout=1.0)`; TimeoutError = **success** (hand-off never returns); exceptions = False → dialog.

## 2. What changed since (regressions)

| Commit | Change | Effect |
|---|---|---|
| 463608d (10-10) | Restored deep link + install dialog | — |
| e5f302d (10-31) | Added `can_launch_url` guard with dead `page is None` branch | The no-handler path could never show the modal in a live app |
| 5976bdd (11-02) | flet 1.0.4 pin | UrlLauncher/video backend changed |

- **Headers are NOT in the ktv:// payload** (v1.0.9 or HEAD): KTV fetches with its own headers. v1.0.9 worked because kwik-resolved CDN URLs needed none.
- **HLS proxy binds 127.0.0.1** (`hls_proxy.py:214`); used by the in-app player only. No lifecycle handlers keep it alive when the app backgrounds.
- v1.0.9 had NO in-app player and NO proxy — external-only.

## 3. Phone-playback suspects (ranked)

1. **External mode handed the UNSELECTED master** (no variant expansion, no quality dialog for single-language sources) — owner confirmed: "external player was on … it could not play … I never saw select quality and audio". Fixed 2026-11-02: `_play_episode_external` now expands variants (`_expand_variant_choices`), stores `self._external_sources`, and `_launch_external_variant` resolves the master → picks the chosen variant's media playlist (`urljoin`) → hands THAT to KTV. `choose_quality` external branch handles variant choices.
2. **`launch_url` void return** — `if await shared.launch_url(...)` never True; modal logic broken. Fixed 2026-11-02: definitive-False semantics + reliable `can_launch_url` (the CI patch declares the ktv:// `<queries>`, so False = truly no handler) → immediate install dialog.
3. Proxy/primp on ARM64 (in-app): if primp's chrome impersonation misbehaves on ARM the proxy 403s; in-app falls back to raw m3u8 without headers. Needs device logs to confirm — re-test after the external fix.
4. Proxy lifecycle: Android may kill the backgrounded app during a KTV hand-off; proxy dies. Consider `on_connect` re-start (only if device logs show it).
5. flet 1.0.4 Media3 differences — mitigated by the planned hwdec auto-safe change (KTV pattern).

## 4. Restore plan (status)

- [x] Install modal on definitive no-handler (external_player.py, 2026-11-02)
- [x] Quality+audio dialog in external mode + variant-selected handoff (main.py, 2026-11-02)
- [ ] Device re-test: internal + external playback on phone (CI build)
- [ ] If in-app still fails on phone: capture `adb logcat` and check proxy startup/primp on ARM64
