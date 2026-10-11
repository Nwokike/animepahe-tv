"""AniKato fixture tests — recorded payloads replayed with zero network.

The fixtures were captured live from anikototv.to during the Phase 0
probes (search page, watch page, VRF episode list, server list, a real
getSources enc token). These pin the MAPPING and the two fixed
transforms (the site's RC4 VRF and MegaPlay's AES-CBC enc), which are
the parts that break silently when a site changes.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------

def test_parse_items_maps_catalog_entries():
    from services.providers.anikato import _parse_items

    items = _parse_items(_read("anikato_search.html"))
    assert items, "search fixture must yield items"
    naruto = next(a for a in items if a.title == "Naruto")
    assert naruto.session == "anikato:naruto-eybxz"
    assert naruto.id == 958
    assert naruto.type == "TV"
    assert naruto.episodes == 220
    assert naruto.poster.startswith("https://cdn.anipixcdn.co/")
    assert naruto.year == 0  # not in the item markup — never invented


def test_parse_items_needs_no_bs4_and_survives_missing_fields():
    from services.providers.anikato import _parse_items

    junk = '<div class="item"><div class="inner">no links here</div></div>'
    assert _parse_items(junk) == []
    assert _parse_items("") == []


def test_parse_watch_maps_anime_id_and_metadata():
    from services.providers.anikato import _parse_watch

    watch = _parse_watch(_read("anikato_watch.html"))
    assert watch["anime_id"] == 958
    assert watch["poster"].startswith("https://cdn.anipixcdn.co/")


def test_parse_episode_list_maps_220_entries():
    from services.providers.anikato import _parse_episode_list

    entries = _parse_episode_list(_read("anikato_episode_list.html"))
    assert len(entries) == 220
    nums = [n for n, _ in entries]
    assert nums[0] == 1 and 220 in nums
    # every entry carries the server-list token
    assert all(ids for _, ids in entries)


def test_parse_servers_maps_sub_and_dub_groups():
    from services.providers.anikato import _parse_servers

    servers = _parse_servers(_read("anikato_servers.html"))
    kinds = {k for k, _ in servers}
    assert kinds == {"sub", "dub"}
    assert len(servers) >= 2  # at least one of each — nothing dropped


def test_megaplay_params_extracts_realid_type_and_s():
    from services.providers.anikato import _megaplay_params

    assert _megaplay_params("https://megaplay.buzz/stream/s-2/12352/sub?s=tcdn") == ("12352", "sub", "tcdn")
    assert _megaplay_params("https://megaplay.buzz/videojs/stream/s-2/999/dub") == ("999", "dub", "")
    assert _megaplay_params("https://megaplay.buzz/other") is None


# ---------------------------------------------------------------------
# The two fixed transforms
# ---------------------------------------------------------------------

def test_vrf_matches_the_site_scheme():
    from services.providers.anikato import _vrf

    # Recorded live in Phase 0: the site accepted exactly this token for
    # anime id 958.
    assert _vrf(958) == "LtGg"


def test_aes_decrypt_opens_the_live_enc_token():
    from services.aes import aes_cbc_decrypt
    from services.providers.anikato import _AES_IV, _AES_KEY, _decrypt_manifest

    enc = json.loads(_read("anikato_getsources.json"))["enc"]
    manifest = _decrypt_manifest(enc)
    assert manifest.startswith("https://")
    assert manifest.endswith("master.m3u8")
    # And the primitive agrees on the raw ciphertext round trip.
    import base64

    raw = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4))
    plain = aes_cbc_decrypt(_AES_KEY, _AES_IV, raw)
    assert b"master.m3u8" in plain
