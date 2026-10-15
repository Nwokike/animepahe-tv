import sys
import json
import os
import time
import webview

# The UA clearance is bound to; the parent process falls back to this same
# string, so the two can never disagree.
FALLBACK_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"

captured_ua = FALLBACK_UA
page_loaded_once = False

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


def check_cookies(window):
    global captured_ua
    # The user closing the window must END the wait: without this the
    # 120×1s poll kept calling get_cookies() on a dead window and the
    # parent's communicate() hung the app for two full minutes.
    closed = getattr(window.events, "closed", None)
    # Loop and check for completed challenge
    for _ in range(120):  # 2 minutes timeout
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
            cookie_strs = []
            cookie_keys = set()
            for c in cookies:
                # Each c is a SimpleCookie from http.cookies
                for key, morsel in c.items():
                    print(
                        f"[DEBUG] Found cookie: {key}={morsel.value[:50] if len(morsel.value) > 50 else morsel.value}",
                        file=sys.stderr,
                    )
                    cookie_strs.append(f"{key}={morsel.value}")
                    cookie_keys.add(key)

            if is_challenge_complete(window, cookie_keys):
                try:
                    ua = window.evaluate_js("navigator.userAgent")
                    if ua:
                        captured_ua = ua
                except Exception:
                    pass

                cookie_header = "; ".join(cookie_strs)
                result = {"cookies": cookie_header, "user_agent": captured_ua}
                print(
                    f"[DEBUG] Returning verified cf_clearance cookie, header length: {len(cookie_header)}",
                    file=sys.stderr,
                )
                print(json.dumps(result))
                window.destroy()
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    url = sys.argv[1]
    window = webview.create_window(
        "Cloudflare Turnstile Solver", url, width=800, height=600
    )
    window.events.loaded += on_loaded
    webview.start(check_cookies, window)
