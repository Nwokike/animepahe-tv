# Anikato Download Quality Options Investigation

## Symptom
Download for Anikato only shows 1 option per language (eng or jpn) unlike Play which shows multiple qualities (1080p, 720p, 480p, etc.).

## Root Cause

### How PLAY builds quality options (src/main.py lines 1024-1054)
```python
# For master playlist sources (resolution=0), expand variants into
# separate quality choices so the user can pick 1080p/720p/480p etc.
expanded_choices = []
for choice in choices:
    src_url = choice["url"]
    src_headers = choice.get("headers", {})
    # Only expand master playlists (.m3u8 with resolution=0)
    if ".m3u8" in src_url and self.hls_proxy is not None:
        try:
            src_variants = await self.hls_proxy.fetch_variants(src_url, headers=src_headers)
        except Exception as ex:
            logger.warning("variant fetch for %s failed: %s", src_url, ex)
            src_variants = []
        if src_variants:
            # Create a choice for each variant
            for v in src_variants:
                v_label = v.get("label") or f"{v.get('height', '?')}p"
                expanded_choices.append(
                    {
                        "label": f"{v_label} - {choice['label']}",
                        "kind": "variant",
                        "url": src_url,
                        "headers": src_headers,
                        "subtitles": choice.get("subtitles"),
                        "skip": choice.get("skip"),
                        "variant_index": v.get("index"),
                        "parent_choice": choice,
                    }
                )
            continue
    expanded_choices.append(choice)
```

### How DOWNLOAD builds quality options (src/main.py lines 2057-2066)
```python
choices = _source_choices(
    sources,
    direct_download=bool(provider and provider.capabilities.get("direct_download_url")),
)
# NO variant expansion - uses choices directly
if len(choices) > 1:
    state.download_choices = choices
    state.download_choice_open = True
```

### AniKato Provider Returns Master Playlists Only
The AniKato provider's `sources()` method (src/services/providers/anikato.py line 950-961) returns `Source` objects with:
- `resolution=0` (master playlist — variants parsed at play)
- `audio="eng"` for dub, `"jpn"` for sub
- `url=manifest` (the m3u8 master playlist URL)

Since `_source_choices` (src/main.py line 85) collapses by `(resolution, audio, fansub, size, bd)` tuple and AniKato sources all have `resolution=0`, only ONE choice per audio language is produced:
- "SUB (JPN) (AniKato)" — for Japanese audio
- "DUB (ENG) (AniKato)" — for English dub

The PLAY path fetches variants from the master playlist and expands them into separate quality options (1080p, 720p, 480p, etc.), but the DOWNLOAD path skips this expansion entirely.

## Fix

Apply the same variant expansion logic from the play path to the download path in `src/main.py` in the `download_episode` method (around line 2060) and `download_series` method (around line 1995).

### Code Change Location
**File:** `/home/maikel/Desktop/kiri-apps/animepahe-tv/src/main.py`

**Method:** `download_episode` (around line 2060)
**Method:** `download_series` (around line 1995)

### Fix Implementation
After building `choices` via `_source_choices()`, add the variant expansion logic (same as lines 1028-1054 in `_play_episode_resolve`):

```python
# For master playlist sources (resolution=0), expand variants into
# separate quality choices so the user can pick 1080p/720p/480p etc.
expanded_choices = []
for choice in choices:
    src_url = choice["url"]
    src_headers = choice.get("headers", {})
    # Only expand master playlists (.m3u8 with resolution=0)
    if ".m3u8" in src_url and self.hls_proxy is not None:
        try:
            src_variants = await self.hls_proxy.fetch_variants(src_url, headers=src_headers)
        except Exception as ex:
            logger.warning("variant fetch for %s failed: %s", src_url, ex)
            src_variants = []
        if src_variants:
            # Create a choice for each variant
            for v in src_variants:
                v_label = v.get("label") or f"{v.get('height', '?')}p"
                expanded_choices.append(
                    {
                        "label": f"{v_label} - {choice['label']}",
                        "kind": "variant",
                        "url": src_url,
                        "headers": src_headers,
                        "subtitles": choice.get("subtitles"),
                        "skip": choice.get("skip"),
                        "variant_index": v.get("index"),
                        "parent_choice": choice,
                    }
                )
            continue
    expanded_choices.append(choice)

# Use expanded_choices instead of choices
choices = expanded_choices
```

Then update the condition to check `len(choices) > 1` and set `state.download_choices = choices`.

### Testing
Existing tests to verify fix:
- `tests/test_download_quality.py` — tests download quality selection flow
- `tests/test_source_choices.py` — tests choice collapsing and variant handling  
- `tests/test_variants.py` — tests HLS variant parsing

New test needed:
- Add test in `test_download_quality.py` verifying variant expansion works for master playlist sources (resolution=0)

### Severity
**High** — Users cannot choose video quality when downloading from Anikato, forced to accept whatever the first variant is (typically lowest quality). The PLAY path already works correctly.

## Summary
- **Symptom:** Anikato download shows only 1 option per language (eng/jpn)
- **Root Cause:** Download path in `main.py` doesn't expand HLS master playlist variants into quality choices, while Play path does
- **Fix:** Apply same variant expansion logic from `_play_episode_resolve` to `download_episode` and `download_series` methods
- **Tests:** Existing test_download_quality.py, test_source_choices.py, test_variants.py cover related logic; need new test for download variant expansion
- **Severity:** High