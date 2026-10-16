"""Desktop Cloudflare solver — the pywebview subprocess.

Runs a visible WebView2 window against the challenge URL; watches cookies
and the page title; prints one JSON line ({"cookies", "user_agent"}) and
exits 0 on success, or {"error": reason} plus a non-zero exit so the parent
can tell failure apart from success. The parent passes the stored UA as
argv[2] when one exists — cf_clearance is bound to the UA that solved it,
so the solve must present the same string the later API calls will.
"""

import contextlib
import json
import os
import sys
import time

import webview

# The UA clearance is bound to; the parent process falls back to this same
# string, so the two can never disagree.
FALLBACK_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"

captured_ua = FALLBACK_UA
page_loaded_once = False
window = None
_done = False
# The proof navigation itself fires `loaded` again; this guard keeps the
# re-entrant judge from recursing into another proof.
_verifying = False

# A page whose title matches these is plainly a web server's own page
# (the owner saw pywebview sit on an nginx page for the full wait) — not
# a Cloudflare challenge, and polling it for cf_clearance is pointless.
_NOT_A_CHALLENGE_MARKERS = (
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


def on_loaded():
    global captured_ua, page_loaded_once
    page_loaded_once = True
    try:
        ua = window.evaluate_js("navigator.userAgent")
        if ua:
            captured_ua = ua
    except Exception:
        pass
    # Event-driven fast path: a challenge that already finished is judged
    # the moment the page loads; the 1 s poll stays the backstop.
    _check_now(window)


def served_a_plain_page(window) -> str | None:
    """The page title when it is a web-server page rather than a challenge.

    Only called after the first navigation completed: evaluate_js waits on
    the bridge-injection gate, which is only set post-load.
    """
    try:
        title = str(window.evaluate_js("document.title") or "").strip()
    except Exception:
        return None
    lowered = title.lower()
    if any(marker in lowered for marker in _NOT_A_CHALLENGE_MARKERS):
        return title
    return None


# Cookies Cloudflare's post-challenge redirect sets on the target site.
# Their presence is a POSITIVE completion signal (the old 1.0.9 solver's
# rule, restored): cf_clearance alone appears while the interstitial is
# still running, and a title read that races a navigation comes back ""
# rather than a challenge word — the old negative-only check therefore
# declared success on UNFINISHED challenges and shipped a cf_clearance
# primp could never use (owner's run, 2026-10-16).
_TARGET_COOKIE_MARKERS = ("animepahe_session", "serverid", "xsrf-token", "latest")

_CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "cloudflare",
)


def is_challenge_complete(window, cookie_keys: set[str]) -> bool:
    """Did the challenge actually finish?

    Rules, in order (the 1.0.9 discipline, kept two-host honest):
    - cf_clearance must exist at all;
    - a challenge URL/title is never complete;
    - an EMPTY title is never complete — that read races a navigation and
      is what shipped an unusable clearance for animepahe (owner's run,
      2026-10-16): the solver "succeeded" while the interstitial was still
      looping, and primp could never use the cookie;
    - the site's own cookies, a title naming the site, or a plainly
      non-Cloudflare page (public.animeout.xyz lands on an nginx 403 with
      only cf_clearance in the jar) are POSITIVE completion signals.
    """
    if "cf_clearance" not in cookie_keys:
        return False

    # The site's own cookies are the strongest signal — the challenge
    # redirected and the app's session began.
    if any(
        any(marker in key.lower() for marker in _TARGET_COOKIE_MARKERS)
        for key in cookie_keys
    ):
        return True

    # Check URL for challenge tokens
    try:
        curr_url = (window.get_current_url() or "").lower()
        if "__cf_chl" in curr_url:
            return False
    except Exception:
        pass

    try:
        title = str(window.evaluate_js("document.title") or "").strip()
    except Exception:
        return False
    title_lower = title.lower()
    if not title_lower:
        # A title read that raced a navigation — never judge it complete.
        return False
    if any(marker in title_lower for marker in _CHALLENGE_TITLE_MARKERS):
        return False
    if "animepahe" in title_lower or "anime" in title_lower:
        return True
    # A plain web-server page (the DDL host's nginx 403) means the
    # challenge cleared and the origin answered.
    return any(marker in title_lower for marker in _NOT_A_CHALLENGE_MARKERS)


def _split_cookies(cookies) -> tuple[set[str], list[str]]:
    """SimpleCookie list -> (keys, "k=v" pairs), with the debug trace."""
    cookie_strs: list[str] = []
    cookie_keys: set[str] = set()
    for c in cookies:
        # Each c is a SimpleCookie from http.cookies
        for key, morsel in c.items():
            print(
                f"[DEBUG] Found cookie: {key}={morsel.value[:50] if len(morsel.value) > 50 else morsel.value}",
                file=sys.stderr,
            )
            cookie_strs.append(f"{key}={morsel.value}")
            cookie_keys.add(key)
    return cookie_keys, cookie_strs


# The API path the parent's own fetches use (the pahe provider's helper).
# The clearance is proven by a JSON answer from THIS path, never by the
# cookie's mere presence: a stale cf_clearance in the persistent profile
# passes every local check and still 403s, and shipping it looped the app
# (live probe, 2026-10-16 — 'solve succeeded' in seconds, then the same
# 403).
_PROOF_PATH = "/api?m=airing&page=1"

# Cloudflare's hard block (as opposed to a solvable challenge): retrying
# only deepens the flag. The owner hit exactly this — repeated automated
# attempts from one address earn 'Sorry, you have been blocked'.
_BLOCKED_TITLE_MARKERS = ("attention required", "sorry, you have been blocked")


def clearance_works(base_url: str, cookie_header: str, ua: str) -> bool:
    """Ask the API with the captured clearance: a JSON body is the proof.

    Uses the WebView's own network stack (a top-level navigation inside
    the window), so the judgement runs under the same fingerprint that
    solved the challenge. Returns False on any non-JSON answer — the
    challenge loop keeps running and the stale profile gets discarded by
    the caller's next attempt instead of being persisted.
    """
    url = f"{base_url.rstrip('/')}{_PROOF_PATH}"
    try:
        window.load_url(url)
        time.sleep(4.0)
        body = str(window.evaluate_js("document.body ? document.body.innerText : ''") or "")
    except Exception as ex:
        print(f"[DEBUG] Proof request failed: {ex}", file=sys.stderr)
        return False
    body = body.strip()
    ok = body.lstrip()[:1] == "{"
    print(
        f"[DEBUG] Proof request -> {'JSON' if ok else 'NOT JSON'}: {body[:80]!r}",
        file=sys.stderr,
    )
    return ok


def _emit_success(cookie_strs: list[str], window) -> None:
    """Print the clearance JSON once and close the window."""
    global _done, captured_ua
    if _done:
        return
    _done = True
    try:
        ua = window.evaluate_js("navigator.userAgent")
        if ua:
            captured_ua = ua
    except Exception:
        pass
    cookie_header = "; ".join(cookie_strs)
    print(
        f"[DEBUG] Returning verified cf_clearance cookie, header length: {len(cookie_header)}",
        file=sys.stderr,
    )
    print(json.dumps({"cookies": cookie_header, "user_agent": captured_ua}))
    with contextlib.suppress(Exception):
        window.destroy()


def _check_now(window) -> None:
    """Judge the just-loaded page, once: success short-circuits the poll."""
    if _done:
        return
    try:
        cookies = window.get_cookies()
    except Exception:
        return
    keys, pairs = _split_cookies(cookies)
    if is_challenge_complete(window, keys):
        _emit_success(pairs, window)


def _hard_blocked(window) -> bool:
    """Is this Cloudflare's hard block (not a solvable challenge)?"""
    try:
        title = str(window.evaluate_js("document.title") or "").lower()
    except Exception:
        return False
    return any(marker in title for marker in _BLOCKED_TITLE_MARKERS)


def check_cookies(window):
    # The backend must be a real Chromium: on MSHTML (or with no runtime
    # installed) get_cookies() is not implemented and the old code sat the
    # full two minutes for it (dep-pywebview.md, §C).
    renderer = getattr(webview, "renderer", None)
    if renderer not in ("edgechromium", "cef"):
        print(f"[DEBUG] Unsupported renderer: {renderer!r}", file=sys.stderr)
        with contextlib.suppress(Exception):
            window.destroy()
        _fail(f"unsupported-renderer ({renderer or 'none'}) — install the WebView2 Runtime")
    # The user closing the window must END the wait: without this the
    # 120x1s poll kept calling get_cookies() on a dead window and the
    # parent's communicate() hung the app for two full minutes.
    closed = getattr(window.events, "closed", None)
    # Loop and check for completed challenge
    for _ in range(120):  # 2 minutes timeout
        if _done:
            return  # the loaded-event fast path already emitted
        if closed is not None and closed.is_set():
            print("[DEBUG] Window closed by the user", file=sys.stderr)
            _fail("closed")
        time.sleep(1.0)
        try:
            cookies = window.get_cookies()
            if cookies is None:  # window destroyed mid-poll
                if _done:
                    return
                continue
            print(f"[DEBUG] Cookie jar has {len(cookies)} entries", file=sys.stderr)
            cookie_keys, cookie_strs = _split_cookies(cookies)
            if is_challenge_complete(window, cookie_keys):
                _emit_success(cookie_strs, window)
                return
        except Exception as e:
            print(f"[DEBUG] Error reading cookies: {e}", file=sys.stderr)

        if page_loaded_once:
            plain = served_a_plain_page(window)
            if plain:
                print(
                    f"[DEBUG] Loaded page is not a challenge: {plain!r}",
                    file=sys.stderr,
                )
                with contextlib.suppress(Exception):
                    window.destroy()
                _fail(f"not-a-challenge ({plain[:60]})")

    # Timeout: an explicit error line and a NON-ZERO exit, so the parent
    # can tell "never finished" from "user closed it" from "solved".
    print("[DEBUG] Timed out waiting for the challenge", file=sys.stderr)
    with contextlib.suppress(Exception):
        window.destroy()
    _fail("timeout")


def _fail(reason: str) -> None:
    """Signal failure to the parent and exit the subprocess.

    os._exit (not sys.exit) because this runs on pywebview's background
    thread — a plain SystemExit there would only end the thread and leave
    the GUI pumping.
    """
    print(json.dumps({"error": reason}))
    sys.stdout.flush()
    os._exit(3)


def _profile_dir() -> str | None:
    """A durable WebView2 profile beside the app's own storage.

    The default ephemeral profile wipes cookies/history every run, so the
    challenge sees a brand-new client each time — the environment where the
    non-interactive check loops forever. A persistent profile accumulates
    the same kind of trust a user's own browser has.
    """
    base = os.environ.get("FLET_APP_STORAGE_DATA")
    if not base:
        return None
    path = os.path.join(base, "cf-profile")
    with contextlib.suppress(OSError):
        os.makedirs(path, exist_ok=True)
        return path
    return None


def run(url: str, requested_ua: str | None = None) -> None:
    """Create the solver window and pump the GUI. Split from __main__ so
    tests can drive it with a fake webview module."""
    global window, captured_ua
    if requested_ua:
        captured_ua = requested_ua
    window = webview.create_window("Cloudflare Turnstile Solver", url, width=800, height=600)
    window.events.loaded += on_loaded
    # user_agent= pins the solve to the UA the clearance is bound to;
    # None keeps the system default. The storage_path keeps the profile.
    profile = _profile_dir()
    webview.start(
        check_cookies,
        window,
        user_agent=requested_ua,
        private_mode=profile is None,
        storage_path=profile,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    requested = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    run(sys.argv[1], requested)
