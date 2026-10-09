import sys
import json
import time
import webview

captured_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"


def on_loaded():
    global captured_ua
    try:
        ua = window.evaluate_js("navigator.userAgent")
        if ua:
            captured_ua = ua
    except Exception:
        pass


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
    # Loop and check for completed challenge
    for _ in range(120):  # 2 minutes timeout
        time.sleep(1.0)
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

    # If timeout or closed
    window.destroy()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    url = sys.argv[1]
    window = webview.create_window(
        "Cloudflare Turnstile Solver", url, width=800, height=600
    )
    window.events.loaded += on_loaded
    webview.start(check_cookies, window)
