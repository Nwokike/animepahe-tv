"""Kayoanime provider — the map's evidence replayed. Drive API is injected
(fake transport); WP response shapes come from the map's captured probes.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# --- pure functions ----------------------------------------------------

def test_episode_number_three_shapes_plus_movie():
    from services.providers.kayoanime import _episode_number

    assert _episode_number("[Kayoanime] Boruto - Naruto Next Generations - 107.mkv") == 107
    assert _episode_number("[Kayoanime] Boruto - 274.mkv") == 274
    assert _episode_number("[Kayoanime] Dandadan - S02E05.mkv") == 5
    assert _episode_number("Sousou no Frieren - 01.mkv") == 1
    assert _episode_number("[Kayoanime] Naruto Shippuden - Movie 08 - Boruto.mkv") is None
    assert _episode_number("random-notes.txt") is None


def test_folder_pairs_and_maintenance_rule():
    from services.providers.kayoanime import _folder_pairs

    html = (
        '<a href="https://drive.google.com/drive/folders/1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs">BOX 2</a>'
        '<a href="https://drive.google.com/drive/folders/1KY6nyLVpwB_l0VS_QyUfEJ7iWv_GsHMT">BOX 3</a>'
        '<a href="#">FIXING LINKS</a>'
    )
    pairs = _folder_pairs(html)
    assert pairs == [
        ("1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs", "BOX 2"),
        ("1KY6nyLVpwB_l0VS_QyUfEJ7iWv_GsHMT", "BOX 3"),
    ]
    assert _folder_pairs('<a href="#">FIXING LINKS</a>') == []  # maintenance


def test_title_ranking_is_ranking_not_filtering():
    from services.providers.kayoanime import _title_relevance

    assert _title_relevance("one piece", "One Piece (All Season + Movies)") == 100
    assert _title_relevance("one piece", "Barakamon (Season 1) 1080p") == 0
    assert _title_relevance("frieren", "Sousou no Frieren Season 2 BD") == 100


def test_extract_resolution_never_invents():
    from services.providers.kayoanime import _extract_resolution

    assert _extract_resolution("Boruto 1080p Dual Audio HEVC") == 1080
    assert _extract_resolution("Sousou no Frieren Season 2") == 0  # unknown stays 0


# --- provider with an injected fake transport -------------------------

class _PrimpLikeClient:
    """Minimal surface the provider uses: get(url, params, headers)."""

    def __init__(self, routes):
        self._routes = routes
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        # route needles may match the URL or any param value
        hay = url + " " + " ".join(
            f"{k}={v}" for k, v in (params or {}).items()
        )
        for needle, status, payload in self._routes:
            if needle in hay:
                return _PrimpLikeClient._Resp(status, payload)
        return _PrimpLikeClient._Resp(404, {})


    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload


def _posts_response(posts):
    return _PrimpLikeClient._Resp(200, posts)


def test_search_ranks_posts_by_title_coverage():
    import asyncio

    from services.providers.kayoanime import KayoanimeProvider

    posts = [
        {"id": 10, "title": {"rendered": "Barakamon (Season 1) 1080p | Kayoanime"},
         "featured_media": 1, "yoast_head_json": {"og_image": [{"url": "https://x/b.jpg"}]}},
        {"id": 162, "title": {"rendered": "One Piece (All Season + Movies) | Kayoanime"},
         "featured_media": 2, "yoast_head_json": {"og_image": [{"url": "https://x/op.jpg"}]}},
    ]
    client = _PrimpLikeClient([("/wp-json/wp/v2/posts", 200, posts)])
    provider = KayoanimeProvider(client=client)
    results, _ = asyncio.run(provider.search("one piece", 1))
    assert [a.id for a in results] == [162, 10]  # real match first, noise second
    assert results[0].poster == "https://x/op.jpg"
    assert results[0].session == "kayoanime:162"


def test_episodes_walk_folders_dedupe_and_use_file_ids():
    import asyncio

    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 961,
        "title": {"rendered": "Boruto 1080p Dual Audio | Kayoanime"},
        "content": {"rendered": (
            '<a href="https://drive.google.com/drive/folders/1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs">BOX 6</a>'
            '<a href="https://drive.google.com/drive/folders/1UKWccvPLOD1MycpDFYMpB6EKK7kJFIJV">BOX 8</a>'
            '<a href="https://drive.google.com/drive/folders/1F_w6VDJn824XUBF3v3gSdy843Mj_4yWQ">1080p [Private Drive]</a>'
        )},
    }
    def listing(files):
        return _PrimpLikeClient._Resp(200, {"files": files})

    routes = [
        ("/wp-json/wp/v2/posts/961", 200, post),
        ("q='1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs' in parents", 200, {
            "files": [
                {"id": "f136", "name": "[Kayoanime] Boruto - 136.mkv", "size": "100000000"},
                {"id": "f137", "name": "[Kayoanime] Boruto - 137.mkv", "size": "101000000"},
            ]
        }),
        ("q='1UKWccvPLOD1MycpDFYMpB6EKK7kJFIJV' in parents", 200, {
            "files": [
                # overlaps 136 with a LARGER file, plus its own range
                {"id": "f136big", "name": "Boruto - 136.mkv", "size": "200000000"},
                {"id": "f274", "name": "Boruto - 274.mkv", "size": "90000000"},
            ]
        }),
        ("q='1F_w6VDJn824XUBF3v3gSdy843Mj_4yWQ' in parents", 200, {"files": []}),
        ("/drive/v3/files/1F_w6VDJn824XUBF3v3gSdy843Mj_4yWQ", 404, {"error": {"code": 404}}),
    ]
    client = _PrimpLikeClient(routes)
    provider = KayoanimeProvider(client=client)
    episodes, has_more = asyncio.run(provider.episodes("kayoanime:961", 1))
    nums = [e.episode for e in episodes]
    assert nums == [136, 137, 274]  # deduped by number, sorted
    # the larger overlapping copy wins and its file id is the session
    winner = next(e for e in episodes if e.episode == 136)
    assert winner.session == "f136big"
    assert has_more is False
    # quality carried from the post title, not invented
    sources = asyncio.run(provider.sources("kayoanime:961", "f274"))
    assert len(sources) == 2  # keyed + keyless routes
    assert all(s.resolution == 1080 for s in sources)
    assert sources[0].url.startswith("https://www.googleapis.com/drive/v3/files/f274?alt=media")
    assert "confirm=t" in sources[1].url
    # The gated folder is named (not just logged) and the real filename survives.
    assert provider.gated_folders("kayoanime:961") == ["1080p [Private Drive]"]
    assert provider.file_name("kayoanime:961", "f274") == "Boruto - 274.mkv"
    assert provider.file_name("kayoanime:961", "nope") is None


def test_kayoanime_box_labels_are_batches_not_seasons():
    """BOX labels name the FOLDER (a batch volume), which is why the walk
    stays flat: splitting the episode list by them would invent a season
    structure the post does not have."""
    from services.providers.kayoanime import _folder_pairs

    html = (
        '<a href="https://drive.google.com/drive/folders/1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs">BOX 6</a>'
        '<a href="https://drive.google.com/drive/folders/1UKWccvPLOD1MycpDFYMpB6EKK7kJFIJV">Season 2</a>'
    )
    pairs = _folder_pairs(html)
    assert pairs == [
        ("1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs", "BOX 6"),
        ("1UKWccvPLOD1MycpDFYMpB6EKK7kJFIJV", "Season 2"),
    ]
    # the label is kept for the gated report, and never splits the list
    assert [label for _fid, label in pairs] == ["BOX 6", "Season 2"]


def test_maintenance_post_surfaces_no_episodes():
    import asyncio

    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 162,
        "title": {"rendered": "One Piece | Kayoanime"},
        "content": {"rendered": '<a href="#">FIXING LINKS</a>'},
    }
    client = _PrimpLikeClient([("/wp-json/wp/v2/posts/162", 200, post)])
    provider = KayoanimeProvider(client=client)
    episodes, _ = asyncio.run(provider.episodes("kayoanime:162", 1))
    assert episodes == []
