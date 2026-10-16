"""Minimal HTML attribute extraction on the stdlib parser.

Replaces BeautifulSoup for this app's two narrow needs — both are pure
attribute scraping on known element shapes, no DOM traversal:

* ``.anime-card`` elements and their ``data-*`` attributes (search HTML
  fallback), plus the presence of a ``.pagination .next`` link
* ``[data-src]`` elements (kwik sources) with their resolution/audio metadata

Kept deliberately small: if the site changes shape, the scrapers fail
loudly and get fixed, exactly as with soup — there is no query language
here to mislead anyone.
"""

import re
from html import unescape
from html.parser import HTMLParser

__all__ = ["extract_anime_cards", "extract_data_src_elements", "plain_summary"]


def _classes(attrs: dict) -> set:
    return set((attrs.get("class") or "").split())


class _ElementParser(HTMLParser):
    """Collects start-tag attribute dicts for elements matching a predicate."""

    def __init__(self, match):
        super().__init__(convert_charrefs=True)
        self._match = match
        self.elements: list[dict] = []
        self._stack: list[tuple[str, set]] = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = _classes(attr_dict)
        self._stack.append((tag, classes))
        if self._match(tag, attr_dict, classes, self._stack):
            self.elements.append(attr_dict)

    def handle_endtag(self, tag):
        # Pop back to the nearest matching open tag; tolerate unclosed tags.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    @property
    def inside_pagination(self) -> bool:
        return any("pagination" in classes for _, classes in self._stack)


def extract_anime_cards(html: str) -> tuple[list[dict], bool]:
    """Return the ``.anime-card`` attribute dicts and whether a next page exists."""

    class _CardParser(_ElementParser):
        def __init__(self):
            super().__init__(lambda tag, attrs, classes, stack: "anime-card" in classes)
            self.has_next = False

        def handle_starttag(self, tag, attrs):
            attr_dict = dict(attrs)
            classes = _classes(attr_dict)
            self._stack.append((tag, classes))
            if "anime-card" in classes:
                self.elements.append(attr_dict)
            if self.inside_pagination and "next" in classes:
                self.has_next = True

    parser = _CardParser()
    parser.feed(html)
    parser.close()
    return parser.elements, parser.has_next


def extract_data_src_elements(html: str) -> list[dict]:
    """Return the attribute dicts of every element carrying ``data-src``."""
    parser = _ElementParser(lambda tag, attrs, classes, stack: bool(attrs.get("data-src")))
    parser.feed(html)
    parser.close()
    return parser.elements


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def plain_summary(html: str, *, limit: int = 600) -> str:
    """Human prose from a post body: tags stripped, whitespace collapsed,
    capped. The WordPress pair (AnimeOut, KayoAnime) publishes its
    description INSIDE the post body rather than an API field, so this is
    where their "blog entry" text comes from — the same HTML the episode
    parser already downloads, nothing extra fetched."""
    text = _TAG_RE.sub(" ", html or "")
    text = unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Trim to the last sentence end so the cap never splits a word.
    for mark in (". ", "! ", "? "):
        idx = cut.rfind(mark)
        if idx > limit // 2:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"
