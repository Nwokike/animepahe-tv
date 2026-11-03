"""Reproduce the app's EXACT download pipeline per backend, locally.

Discovery -> episodes -> sources -> DownloadManager -> bytes on disk.
Only the app's own modules are used (router, providers, downloads, store);
nothing here re-implements a step. The store is redirected to a scratch
dir so the owner's real state is untouched.

Usage: uv run python tools/download_matrix.py [backend ...] [--query "..."]
"""

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".flet" / "storage" / "temp" / "dlmatrix"
for tier in ("data", "cache", "temp"):
    (SCRATCH / tier).mkdir(parents=True, exist_ok=True)
os.environ["FLET_APP_STORAGE_DATA"] = str(SCRATCH / "data")
os.environ["FLET_APP_STORAGE_CACHE"] = str(SCRATCH / "cache")
os.environ["FLET_APP_STORAGE_TEMP"] = str(SCRATCH / "temp")
sys.path.insert(0, str(ROOT / "src"))

from services.downloads import DownloadManager
from services.router import ProviderRouter
from services.store import get_store

QUERIES = {
    "anikato": "black clover",
    "animeout": "black clover",
    "animepahe": "black clover",
    "kayoanime": "black clover",
}

HEADER_NAMES = {
    b"\x1a\x45\xdf\xa3": "EBML/Matroska (mkv/webm)",
    b"\x47": "MPEG-TS",
    b"\x89PNG": "PNG",
}


def sniff(path: Path) -> str:
    head = path.open("rb").read(12)
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "EBML/Matroska (mkv/webm)"
    if head[:1] == b"\x47":
        return "MPEG-TS"
    if head[4:8] == b"ftyp":
        return "MP4"
    if head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    return f"unknown head={head[:8].hex()}"


def job_stats(job_dir: Path) -> tuple[int, int, list[str]]:
    """(segments, bytes, kinds) for either job shape: an HLS job keeps its
    media under `segs/`, a direct-file job keeps ONE file beside the
    manifest."""
    segs = job_dir / "segs"
    if segs.is_dir():
        files = sorted(p for p in segs.iterdir() if p.is_file())
    else:
        files = sorted(
            p
            for p in job_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".mkv", ".mp4", ".ts", ".webm", ".avi")
        )
    total = sum(p.stat().st_size for p in files)
    kinds = sorted({sniff(p) for p in files[:4]}) if files else []
    return len(files), total, kinds


async def run_backend(name: str, query: str) -> None:
    print(f"\n{'=' * 72}\n[{name}] discovering '{query}'")
    from services.providers.anikato import AniKatoProvider
    from services.providers.animeout import AnimeOutProvider
    from services.providers.animepahe_provider import AnimePaheProvider
    from services.providers.kayoanime import KayoanimeProvider

    if name == "animepahe":
        from services.animepahe import AnimePaheScraper

        scraper = AnimePaheScraper()
        provider = AnimePaheProvider(scraper)
    elif name == "anikato":
        provider = AniKatoProvider()
    elif name == "animeout":
        provider = AnimeOutProvider()
    else:
        provider = KayoanimeProvider()

    router = ProviderRouter([provider])
    router.set_pin(name)
    store = get_store()
    manager = DownloadManager(store=store)

    try:
        results, _ = await router.search(query, 1)
    except Exception as ex:
        print(f"[{name}] search FAILED: {type(ex).__name__}: {ex}")
        return
    if not results:
        print(f"[{name}] search returned nothing")
        return
    anime = results[0]
    print(f"[{name}] -> {anime.title!r} session={anime.session} episodes={anime.episodes}")

    try:
        episodes, has_more = await router.episodes(anime.session, 1)
    except Exception as ex:
        print(f"[{name}] episodes FAILED: {type(ex).__name__}: {ex}")
        return
    if not episodes:
        print(f"[{name}] no episodes")
        return
    ep = episodes[0]
    print(f"[{name}] episode 1 session={ep.session[:28]}… more={has_more}")

    try:
        sources = await router.sources(anime.session, ep.session)
    except Exception as ex:
        print(f"[{name}] sources FAILED: {type(ex).__name__}: {ex}")
        return
    if not sources:
        print(f"[{name}] no sources")
        return

    # Try each source until one downloads real bytes (the preset logic's
    # intent: the best that actually works).
    for i, src in enumerate(sources[:3]):
        url = src.download_url or src.url
        headers = dict(getattr(src, "headers", None) or {})
        t0 = time.time()
        print(f"[{name}] src[{i}] q={src.resolution}p url={url[:90]}")
        try:
            kind, server_name = await manager.detect_kind(url, headers)
        except Exception as ex:
            print(f"[{name}]   detect_kind FAILED: {type(ex).__name__}: {ex}")
            continue
        print(f"[{name}]   kind={kind} server_name={server_name!r}")
        episode_key = f"{name}:matrix:{ep.session[:24]}"
        meta = {
            "anime_session": anime.session,
            "title": anime.title,
            "episode_num": ep.episode,
            "filename": server_name or "",
        }
        try:
            if kind == "file":
                await manager.start_direct(episode_key, url, headers, meta)
            else:
                await manager.start(episode_key, url, headers, meta)
        except Exception as ex:
            print(f"[{name}]   start FAILED: {type(ex).__name__}: {ex}")
            continue
        # Wait for the job to finish (or 8 minutes).
        while episode_key in manager._tasks and time.time() - t0 < 480:
            await asyncio.sleep(2.0)
        job_dir = manager._job_dir(anime.session, episode_key)
        job_path = Path(job_dir)
        row = (await store.get_downloads()).get(episode_key) or {}
        state = row.get("state")
        nsegs, nbytes, kinds = job_stats(job_path)
        manifest = manager._read_manifest(str(job_path / "manifest.json"))
        print(
            f"[{name}]   RESULT state={state} segments={nsegs} "
            f"bytes={nbytes} ({nbytes / 1_000_000:.1f} MB) takes={time.time() - t0:.0f}s"
        )
        files = (
            [p.name for p in sorted((job_path / "segs").iterdir())][:2]
            if (job_path / "segs").is_dir()
            else [p.name for p in sorted(job_path.iterdir()) if p.is_file()]
        )
        print(f"[{name}]   file(s)={files}")
        print(
            f"[{name}]   kinds={kinds or [manifest.get('state')]} error={row.get('error', '')[:120]}"
        )
        if state == "complete" and nbytes > 20_000_000:
            print(f"[{name}]   VERDICT: REAL download ({nbytes / 1_000_000:.1f} MB)")
            return
        if state == "complete":
            print(f"[{name}]   VERDICT: completed but suspiciously small — retrying next source")
            continue
        print(f"[{name}]   VERDICT: failed ({row.get('error', '')[:100]}) — trying next source")


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    backends = args or ["anikato", "kayoanime", "animepahe", "animeout"]
    query = "black clover"
    if "--query" in sys.argv:
        query = sys.argv[sys.argv.index("--query") + 1]
    for name in backends:
        await run_backend(name, QUERIES.get(name, query))


if __name__ == "__main__":
    asyncio.run(main())
