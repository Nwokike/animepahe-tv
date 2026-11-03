"""The Cloudflare completion judge — ONE rule, two transports.

The app solves challenges through two very different windows: an
in-app ``flet_webview`` WebView on Android/Android TV (the phone path)
and a pywebview/WebView2 subprocess on desktop. Both need the same
answer to "did this challenge actually finish?" — and until now they
each carried their own copy of that rule, and the copies had drifted.

The drift is what the owner reported: the desktop path captured an
AnimeOut clearance (its judge fell through to "a plain web-server page
means the origin answered"), while the phone path's judge demanded the
literal string ``animepahe`` in the title or the URL. So on the phone
AnimePahe solved and AnimeOut never did — the WebView sat on
"Waiting for verification..." over a challenge that had already
cleared, and the loop timed out with nothing captured. AnimePahe is
the FIRST source in the fixed order and the only one whose catalogue
the owner had exercised on a phone; AnimeOut's phone solve had never
been tested.

So the test lives here, as one pure function with no window, no page
and no platform in it, and each solver feeds it the facts it can read
(which cookies the jar has, what URL the window is on, what title the
page reports, which host it was asked for). A transport bug can no
longer change the answer.

The rules, in order — the 1.0.9 discipline that the desktop solver
restored after the empty-title bug (owner's run, 2026-10-16), and whose
ordering the existing tests pin:

1. **cf_clearance must exist at all.** No clearance, nothing to ship.
2. **The hard block is a stop, not a wait.** Retrying only deepens the
   flag, so it fails rather than continuing to poll.
3. **The site's own cookies are the strongest positive signal** — and
   they outrank the negatives below: a site that set its own session
   cookie has finished the redirect, even when the title read raced the
   navigation that set it.
4. **A challenge is never complete.** ``__cf_chl`` in the URL, or a
   challenge word in the title, means the interstitial is still running
   — the cookie may already be in the jar while the page loops.
5. **An empty title is never complete.** That read races a navigation;
   judging it as success is exactly what shipped an unusable clearance.
6. **The host we were asked to clear is a positive signal** — for a
   host with no session cookies of its own (AnimeOut's file wall), this
   is the only signal there is.
7. **A plain web-server page means the origin answered.** The AnimeOut
   file host lands on an nginx 403 with only cf_clearance in the jar.
"""

from __future__ import annotations

# Cookies a site sets once the challenge redirects and its own session
# begins. These are per-site strings; they are the strongest signal
# wherever they appear, and their absence must NOT block a host that
# has none of them (rule 5 covers those).
TARGET_COOKIE_MARKERS = ("animepahe_session", "serverid", "xsrf-token", "latest")

# A title containing one of these is the challenge itself.
CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "checking your browser before accessing",
    "cloudflare",
)

# Cloudflare's hard block (not a solvable challenge). Reported as a
# failure so the caller stops; retrying only deepens the flag.
BLOCK_TITLE_MARKERS = (
    "sorry, you have been blocked",
    "you have been blocked",
    "attention required",
    "access denied",
)

# A title that is plainly a web server's own page — not a challenge and
# not the site. The owner watched pywebview sit on one of these for the
# full wait once; polling it for cf_clearance is pointless.
PLAIN_PAGE_TITLE_MARKERS = (
    "welcome to nginx",
    "index of /",
    "apache2",
    "it works!",
    "401 unauthorized",
    "403 forbidden",
    "404 not found",
    "502 bad gateway",
    "503 service",
    "504 gateway",
)


def target_host_of(url: str) -> str:
    """The host the caller asked to clear, as a bare label.

    ``https://public.animeout.xyz/nimbus.../x.mkv`` -> ``animeout``
    (the registrable part, minus any ``public.``/``www.`` prefix), so a
    page title naming the site counts as "we are on the target".
    Returns "" for anything unparseable — which makes the host rule go
    quiet and leaves the other rules to decide.
    """
    raw = (url or "").strip().lower()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    raw = raw.split("?", 1)[0]
    raw = raw.split("@", 1)[-1]  # drop any userinfo
    # Keep the label a site would put in its own title: the last two
    # labels ("animeout.xyz"), because "public.animeout.xyz" would never
    # appear in that site's title.
    parts = [p for p in raw.split(".") if p]
    if len(parts) < 2:
        return ""
    return parts[-2]


def challenge_complete(
    *,
    cookie_keys,
    url: str = "",
    title: str = "",
    target_host: str = "",
) -> bool:
    """Did the challenge actually finish? The one rule, both transports.

    Args:
        cookie_keys: the cookie NAMES in the window's jar (case is not
            assumed — every comparison lowercases).
        url: the URL the window is on right now.
        title: the page title the window reports ("" when the read
            failed or raced a navigation).
        target_host: the host that was asked to clear, as a bare label
            from :func:`target_host_of`; "" disables rule 5.

    Returns:
        True only when the evidence says the challenge is over and the
        clearance is usable.
    """
    keys = {str(k).lower() for k in (cookie_keys or ())}

    # 1. No clearance, nothing to ship.
    if "cf_clearance" not in keys:
        return False

    # 2. The hard block first — it is a stop, not a wait.
    lowered_title = (title or "").lower()
    if any(marker in lowered_title for marker in BLOCK_TITLE_MARKERS):
        return False

    # 3. The site's own cookies are the strongest positive signal, and
    #    they outrank every negative below: a site that sets its own
    #    session cookie has finished the redirect, even if the title read
    #    raced the navigation that set it.
    if any(any(marker in key for marker in TARGET_COOKIE_MARKERS) for key in keys):
        return True

    lowered_url = (url or "").lower()

    # 4. A running challenge is never complete.
    if "__cf_chl" in lowered_url:
        return False
    if any(marker in lowered_title for marker in CHALLENGE_TITLE_MARKERS):
        return False

    # 5. An empty title is a racing read — never judge it complete.
    if not lowered_title.strip():
        return False

    # 6. We are on the host we were asked to clear, past the challenge.
    if target_host and target_host in lowered_title:
        return True
    if target_host and target_host in lowered_url:
        return True

    # 7. A plain web-server page means the origin answered (AnimeOut's
    # file host lands on an nginx 403 with only cf_clearance in the jar).
    return any(marker in lowered_title for marker in PLAIN_PAGE_TITLE_MARKERS)


def is_hard_blocked(title: str) -> bool:
    """Cloudflare's hard block, detected from the title alone."""
    lowered = (title or "").lower()
    return any(marker in lowered for marker in BLOCK_TITLE_MARKERS)


__all__ = [
    "BLOCK_TITLE_MARKERS",
    "CHALLENGE_TITLE_MARKERS",
    "PLAIN_PAGE_TITLE_MARKERS",
    "TARGET_COOKIE_MARKERS",
    "challenge_complete",
    "is_hard_blocked",
    "target_host_of",
]
