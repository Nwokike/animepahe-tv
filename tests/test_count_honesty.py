"""Count honesty — Phase 3 Step 2.

The rule: show what the provider gives you, hide what it doesn't — never
print "0". AnimeOut's only count lives in `excerpt.rendered`
(`Episodes: N`); a live probe on 2026-10-15 found it clean on regular and
ongoing posts (220 / 24 / 4 / 1) and empty-or-absent on the mega-posts,
which is why the parse is digits-only and absent stays hidden. The other
guards pinned here: the series-download dialog never says "0 episodes",
a release card with no episode says "New release", the Continue-Watching
shelf drops "of 0", and the detail metadata row keeps its zero guard.
"""

import ast
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from core.state import Episode, LatestRelease
from screens.anime_detail_screen import _build_series_download_dialog
from screens.home_screen import _continue_watching_row, _release_card
from services.providers.animeout import (
    AnimeOutProvider,
    _episodes_from_excerpt,
)


def _texts(control, found=None):
    """Every ft.Text value in a control tree (dialogs included)."""
    found = [] if found is None else found
    if control is None:
        return found
    if isinstance(control, ft.Text):
        found.append(str(control.value))
    for attr in ("content", "controls", "actions", "title"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                _texts(item, found)
        elif isinstance(child, ft.Control):
            _texts(child, found)
    return found


def _ep(episode: int) -> Episode:
    return Episode(
        id=episode,
        anime_id=1,
        episode=episode,
        title=f"Episode {episode}",
        snapshot="",
        disc="",
        audio="jpn",
        duration="",
        session=f"s{episode}",
        filler=False,
    )


# ---------------------------------------------------------------------------
# AnimeOut's excerpt count
# ---------------------------------------------------------------------------


def test_excerpt_parse_uses_the_probed_real_shapes():
    real = {
        "220": "<p>Synonyms: Naruto Type: TV Series Episodes: 220 Aired: 2002</p>",
        "24": "<p>Type: TV Series Episodes: 24 Aired: 2012-03-23 Ended: 2012-09-22</p>",
        "4": "<p>Episodes: 4 Status: Ongoing</p>",
        "1": ("<p>Episodes: 1</p>"),
        "": "<p>Type: TV Series Episodes: Aired: 2020</p>",  # mega-posts
    }
    for expected, html in real.items():
        post = {"excerpt": {"rendered": html}}
        got = _episodes_from_excerpt(post)
        assert got == (int(expected) if expected else 0), html
    # Absent field and non-numeric values stay 0 (hidden, never printed).
    assert _episodes_from_excerpt({}) == 0
    assert _episodes_from_excerpt({"excerpt": {"rendered": "Episodes: ongoing"}}) == 0


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Serves the single post fetch `anime()` makes (no featured_media →
    no media call)."""

    def __init__(self, post):
        self.post = post
        self.urls = []

    async def get(self, url, **kwargs):
        self.urls.append(url)
        return _Resp(self.post)


def test_animeout_anime_carries_the_count():
    post = {
        "id": 1029418,
        "title": {"rendered": "Accel World (2012)(Complete BD)"},
        "excerpt": {"rendered": "<p>Type: TV Series Episodes: 24 Aired: 2012-03-23</p>"},
    }
    provider = AnimeOutProvider(client=_FakeClient(post))
    anime = asyncio.run(provider.anime("animeout:1029418"))
    assert anime is not None
    assert anime.episodes == 24
    assert anime.session == "animeout:1029418"


def test_animeout_anime_hides_an_absent_count():
    post = {
        "id": 160691,
        "title": {"rendered": "One Piece Movies (Mega Post)"},
        "excerpt": {"rendered": "<p>Movies 1-15</p>"},
    }
    provider = AnimeOutProvider(client=_FakeClient(post))
    anime = asyncio.run(provider.anime("animeout:160691"))
    assert anime is not None and anime.episodes == 0


# ---------------------------------------------------------------------------
# The dialog, the card, the shelf, the metadata row
# ---------------------------------------------------------------------------


def test_series_download_dialog_never_says_zero():
    empty = _build_series_download_dialog([], object(), "s", {}, None)
    texts = _texts(empty)
    assert "No episodes in this range" in texts
    assert not any(t.startswith("0 episodes") for t in texts)

    with_eps = _build_series_download_dialog([_ep(1), _ep(2)], object(), "s", {}, None)
    assert "2 episodes" in _texts(with_eps)


def test_release_card_never_says_episode_zero():
    release = LatestRelease(
        anime_id=1,
        anime_title="Black Clover",
        anime_session="s",
        episode=0,
        snapshot="",
        session="",
        created_at="",
    )
    texts = _texts(_release_card(release, lambda *_: None, False))
    assert "New release" in texts
    assert not any("Episode 0" in t for t in texts)

    release.episode = 5
    texts = _texts(_release_card(release, lambda *_: None, False))
    assert any("Episode 5" in t for t in texts)


def test_continue_watching_never_says_of_zero():
    row = _continue_watching_row(
        {
            "s": {
                "anime_session": "s",
                "title": "T",
                "poster": "",
                "total_episodes": 0,
                "episode_num": 3,
            }
        },
        lambda *_: None,
    )
    texts = _texts(row)
    assert "Ep 3" in texts
    assert not any("of 0" in t for t in texts)

    row = _continue_watching_row(
        {
            "s": {
                "anime_session": "s",
                "title": "T",
                "poster": "",
                "total_episodes": 12,
                "episode_num": 3,
            }
        },
        lambda *_: None,
    )
    assert "Ep 3 · of 12" in _texts(row)


def test_metadata_row_keeps_its_zero_guard():
    """`_metadata_row` is nested inside the screen component, so this pins
    the structure: the "N Episodes" append must sit behind an
    `anime.get("episodes")` guard (the row renders nothing at 0)."""
    path = os.path.join(os.path.dirname(__file__), "..", "src", "screens", "anime_detail_screen.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_metadata_row"
    )
    guarded = any(
        isinstance(node, ast.If) and "episodes" in ast.unparse(node.test) for node in ast.walk(fn)
    )
    assert guarded


def test_plain_summary_strips_tags_and_caps_at_a_sentence():
    """The WP pair publishes its description inside the post body — the
    helper that turns that HTML into prose (tags stripped, whitespace
    collapsed, capped at a sentence end, never mid-word)."""
    from core.html_extract import plain_summary

    html = (
        "<h4>Title</h4><p><strong>Type: TV Series</strong><br />Episodes: 24</p>"
        "<p>First sentence of the description. Second sentence follows here "
        "and continues past the limit so the cap has to cut it cleanly.</p>"
        "<a href='x'>link</a>"
    )
    text = plain_summary(html, limit=80)
    assert "<" not in text and ">" not in text
    assert "Type: TV Series" in text
    assert text.endswith("."), text
    assert len(text) <= 81

    # Short bodies come back whole.
    assert plain_summary("<p>Short.</p>") == "Short."
    assert plain_summary("") == ""
