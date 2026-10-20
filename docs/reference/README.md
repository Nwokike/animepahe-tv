# `docs/reference/` — index and version stamps

Three families of reference, all compiled from live probes or the installed venv:

- **`backend-*.md`** — one map per source host (endpoint inventory, live evidence,
  capabilities, provider coverage vs gaps). These age with the SITES; reconfirm
  against live responses before trusting a selector.
- **`app-*.md`** — house-app studies (ktv-player, Sherlock, DDGS): what to port,
  what we already do better, ranked with file references.
- **`dep-*.md`** — dependency API references compiled from the installed venv.
  These age with the PACKAGES.

**Rule: the installed package is the only source of truth.** Where a dep doc
disagrees with `importlib.metadata` + live introspection, the doc is wrong, and
the failure mode is real — the swarm audit traced ~8 criticals to following
`dep-primp.md`'s primp-1.3.1 surface (docs/swarm-audit-2026-10-13.md §1.1).

## Version stamps (verified 2026-10-15, Python 3.14.7)

| Doc | Compiled against | Installed now | Banner |
|---|---|---|---|
| dep-flet.md | flet 0.85.3 | **flet 1.0.4** | ⚠ stale |
| dep-flet-video.md | flet-video 0.85.3 | **flet-video 1.0.4** | ⚠ stale |
| dep-flet-webview.md | flet-webview 0.85.3 | **flet-webview 1.0.4** | ⚠ stale |
| dep-flet-notifications.md | flet-notifications 0.1.3 | **0.1.4** | ⚠ stale |
| dep-flet-yandex-ads.md | flet-yandex-ads 0.1.0 | 0.1.0 (flet ref stale) | ⚠ |
| dep-primp.md | primp 1.3.1 | **primp 2.0.1** | ⚠ stale — API removals |
| dep-anyio.md | anyio 4.14.1 | **anyio 4.15.1** | ⚠ stale |
| dep-msgpack.md | msgpack 1.2.1 | **msgpack 1.2.3** | ⚠ minor |
| dep-oauthlib.md | oauthlib 3.3.1 | **oauthlib 4.0.0** | ⚠ major, unused by app |
| dep-small-transitives.md | certifi 2026.6.17 / idna 3.18 | **certifi 2026.7.22 / idna 3.20** | ⚠ minor |
| dep-pytest-microdeps.md | pluggy 1.6.0 | **pluggy 1.7.0** | ⚠ minor |
| dep-test-stack.md | ruff 0.15.20, 112 tests | **ruff 0.17.0, 618 tests** | ⚠ stale; §5 applied |
| dep-httpx.md | httpx 0.28.1 | 0.28.1 | current |
| dep-httpcore.md | httpcore 1.0.9 | 1.0.9 | current |
| dep-h11.md | h11 0.16.0 | 0.16.0 | current |
| dep-pywebview.md | pywebview 6.2.1 | 6.2.1 | current |
| dep-pythonnet-stack.md | pythonnet 3.2.1 stack | same | current |
| dep-pyqt6-stack.md | PyQt6 6.11.0 stack | same | current |
| dep-bottle-proxytools.md | bottle 0.13.4 / proxy-tools 0.1.0 | same | current |

Stale docs carry a "Version note" at the top pointing here. A full re-verification
of every stale dep doc is the hybrid era's Phase 5 (dependency close-out), together
with pinning the `[tool.ruff.lint] select` set.
