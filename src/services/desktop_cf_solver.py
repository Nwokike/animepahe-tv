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


def check_cookies(window):
    # Loop and check for cf_clearance cookie
    for _ in range(120):  # 2 minutes timeout
        time.sleep(1.0)
        try:
            cookies = window.get_cookies()
            print(f"[DEBUG] Cookie jar has {len(cookies)} entries", file=sys.stderr)
            cookie_strs = []
            has_cf = False
            for c in cookies:
                # Each c is a SimpleCookie from http.cookies
                for key, morsel in c.items():
                    print(
                        f"[DEBUG] Found cookie: {key}={morsel.value[:50] if len(morsel.value) > 50 else morsel.value}",
                        file=sys.stderr,
                    )
                    cookie_strs.append(f"{key}={morsel.value}")
                    if key == "cf_clearance":
                        has_cf = True

            if has_cf:
                cookie_header = "; ".join(cookie_strs)
                result = {"cookies": cookie_header, "user_agent": captured_ua}
                print(
                    f"[DEBUG] Returning cf_clearance cookie, header length: {len(cookie_header)}",
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
