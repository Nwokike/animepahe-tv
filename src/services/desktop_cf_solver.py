"""Desktop Cloudflare solver — the pywebview subprocess.

Runs a visible WebView2 window against the challenge URL; watches cookies
and the page title; prints one JSON line ({"cookies", "user_agent"}) and
exits 0 on success, or {"error": reason} plus a non-zero exit so the parent
can tell failure apart from success. The parent passes the stored UA as
argv[2] when one exists — cf_clearance is bound to the UA that solved it,
so the solve must present the same string the later API calls will.
"""

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


def is_challenge_complete(window, cookie_keys: set[str]) -> bool:
    if "cf_clearance" not in cookie_keys:
        return False

    # Target site cookies indicate that the challenge finished and redirected to Animepahe
    target_markers = {"animepahe_session", "serverid", "xsrf-token", "latest"}
    if any(k.lower() in target_markers for k in cookie_keys):
        return True

    # Check page title
    try:
        title = window.evaluate_js("document.title") or ""
        title_lower = title.lower()
        if any(
            marker in title_lower
            for marker in [
                "just a moment",
                "attention required",
                "checking your browser",
                "cloudflare",
            ]
        ):
            return False
        if "animepahe" in title_lower or "anime" in title_lower:
            return True
    except Exception:
        pass

    # Check URL for challenge tokens
    try:
        curr_url = (window.get_current_url() or "").lower()
        if "__cf_chl" in curr_url:
            return False
    except Exception:
        pass

    return False


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
    try:
        window.destroy()
    except Exception:
        pass


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


def check_cookies(window):
    # The backend must be a real Chromium: on MSHTML (or with no runtime
    # installed) get_cookies() is not implemented and the old code sat the
    # full two minutes for it (dep-pywebview.md, §C).
    renderer = getattr(webview, "renderer", None)
    if renderer not in ("edgechromium", "cef"):
        print(f"[DEBUG] Unsupported renderer: {renderer!r}", file=sys.stderr)
        try:
            window.destroy()
        except Exception:
            pass
        _fail(
            f"unsupported-renderer ({renderer or 'none'}) — install the WebView2 Runtime"
        )
    # The user closing the window must END the wait: without this the
    # 120×1s poll kept calling get_cookies() on a dead window and the
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
        if page_loaded_once:
            plain = served_a_plain_page(window)
            if plain:
                print(
                    f"[DEBUG] Loaded page is not a challenge: {plain!r}",
                    file=sys.stderr,
                )
                try:
                    window.destroy()
                except Exception:
                    pass
                _fail(f"not-a-challenge ({plain[:60]})")
        try:
            cookies = window.get_cookies()
            print(f"[DEBUG] Cookie jar has {len(cookies)} entries", file=sys.stderr)
            cookie_keys, cookie_strs = _split_cookies(cookies)
            if is_challenge_complete(window, cookie_keys):
                _emit_success(cookie_strs, window)
                return
        except Exception as e:
            print(f"[DEBUG] Error reading cookies: {e}", file=sys.stderr)

    # Timeout: an explicit error line and a NON-ZERO exit, so the parent
    # can tell "never finished" from "user closed it" from "solved".
    print("[DEBUG] Timed out waiting for the challenge", file=sys.stderr)
    try:
        window.destroy()
    except Exception:
        pass
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


def run(url: str, requested_ua: str | None = None) -> None:
    """Create the solver window and pump the GUI. Split from __main__ so
    tests can drive it with a fake webview module."""
    global window, captured_ua
    if requested_ua:
        captured_ua = requested_ua
    window = webview.create_window(
        "Cloudflare Turnstile Solver", url, width=800, height=600
    )
    window.events.loaded += on_loaded
    # user_agent= pins the solve to the UA the clearance is bound to;
    # None keeps the system default.
    webview.start(check_cookies, window, user_agent=requested_ua)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    requested = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    run(sys.argv[1], requested)
