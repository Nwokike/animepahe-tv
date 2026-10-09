import os
import sys
import json
import asyncio
import logging
import platform
import flet as ft

logger = logging.getLogger(__name__)


def _get_python_executable() -> str:
    cwd = os.getcwd()
    if platform.system() == "Windows":
        venv_python = os.path.join(cwd, ".venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(cwd, ".venv", "bin", "python")

    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


class WebViewSolver:
    @staticmethod
    async def solve_challenge(page: ft.Page, url: str) -> tuple[str, str]:
        # Check platform - Android, Android TV, iOS, or macOS can run Flet native webview
        is_mobile = page.platform in [
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.ANDROID_TV,
            ft.PagePlatform.IOS,
            ft.PagePlatform.MACOS,
        ]

        if is_mobile:
            logger.info("WebViewSolver using Flet WebView (Mobile/TV/macOS)")
            return await WebViewSolver._solve_mobile(page, url)
        else:
            logger.info("WebViewSolver using pywebview subprocess (Desktop)")
            return await WebViewSolver._solve_desktop(page, url)

    @staticmethod
    async def _solve_desktop(page: ft.Page, url: str) -> tuple[str, str]:
        # Path to the desktop solver script
        dir_path = os.path.dirname(os.path.abspath(__file__))
        solver_script = os.path.join(dir_path, "desktop_cf_solver.py")

        # Show loading indicator in Flet app while solver runs
        loading_dlg = ft.AlertDialog(
            title=ft.Text("Cloudflare Security Challenge", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text(
                        "Opening verification window... Please complete the challenge in the popup window.",
                        size=13,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.ProgressRing(color=ft.Colors.PRIMARY),
                            ft.Text("Waiting for verification...", size=14),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
            ),
            modal=True,
        )
        page.dialog_open = True
        page.show_dialog(loading_dlg)
        page.update()

        try:
            proc = await asyncio.create_subprocess_exec(
                _get_python_executable(),
                solver_script,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_data, stderr_data = await proc.communicate()

            stderr_out = stderr_data.decode().strip()
            if stderr_out:
                logger.info("Subprocess stderr logs:\n%s", stderr_out)

            if proc.returncode != 0:
                logger.error(
                    "Desktop solver failed with code %d: %s",
                    proc.returncode,
                    stderr_out,
                )
                raise Exception(f"Desktop solver failed: {stderr_out}")

            out = stdout_data.decode().strip()

            # Find the JSON line in the stdout
            json_str = None
            for line in out.splitlines():
                if line.startswith("{") and line.endswith("}"):
                    json_str = line
                    break

            if not json_str:
                raise Exception("Verification was closed or failed.")

            data = json.loads(json_str)
            cookies = data.get("cookies") or ""
            ua = (
                data.get("user_agent")
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            return cookies, ua
        finally:
            page.dialog_open = False
            try:
                page.pop_dialog()
            except Exception:
                pass
            page.update()

    @staticmethod
    async def _solve_mobile(page: ft.Page, url: str) -> tuple[str, str]:
        from flet_webview import WebView, JavaScriptMode, WebViewConsoleMessageEvent

        # Force platform to ANDROID on Android TV so flet_webview methods work.
        # flet_webview's _check_mobile_or_mac_platform() only allows ANDROID,
        # IOS, and MACOS — ANDROID_TV is not recognized, causing all WebView
        # method calls (set_javascript_mode, reload, run_javascript, etc.) to
        # raise FletUnsupportedPlatformException.
        original_platform = page.platform
        if page.platform == ft.PagePlatform.ANDROID_TV:
            logger.info(
                "Mobile solver: overriding ANDROID_TV -> ANDROID for flet_webview compatibility"
            )
            page.platform = ft.PagePlatform.ANDROID

        # Try to initialize pyjnius CookieManager for reading HttpOnly cookies
        _cookie_manager = None
        try:
            from jnius import autoclass  # type: ignore[import-not-found]

            CookieManager = autoclass("android.webkit.CookieManager")
            _cookie_manager = CookieManager.getInstance()
            logger.info("Mobile solver: pyjnius CookieManager initialized")
        except Exception as ex:
            logger.warning(
                "Mobile solver: pyjnius not available, fallback to document.cookie: %s",
                ex,
            )

        loop = asyncio.get_running_loop()
        result_future = loop.create_future()

        async def _android_cookies(current_url: str) -> str:
            if _cookie_manager is None:
                return ""
            try:
                return _cookie_manager.getCookie(current_url) or ""
            except Exception as ex:
                logger.error("CookieManager.getCookie error: %s", ex)
                return ""

        async def _try_resolve(cookie_str: str, current_url: str = ""):
            if "cf_clearance" not in cookie_str:
                return

            lower_cookies = cookie_str.lower()
            target_markers = ("animepahe_session", "serverid", "xsrf-token", "latest")
            has_target_cookie = any(
                marker in lower_cookies for marker in target_markers
            )

            # Check title and current URL to avoid premature completion on challenge interstitial
            title = ""
            try:
                title = (await webview.get_title()) or ""
            except Exception:
                pass

            title_lower = title.lower()
            is_challenge_page = (
                any(
                    m in title_lower
                    for m in [
                        "just a moment",
                        "attention required",
                        "checking your browser",
                        "cloudflare",
                    ]
                )
                or "__cf_chl" in (current_url or "").lower()
            )

            if is_challenge_page and not has_target_cookie:
                logger.debug(
                    "Mobile solver: challenge still in progress (title=%s, url=%s)",
                    title,
                    current_url,
                )
                return

            # Complete if target site cookies are set OR if title reached Animepahe
            is_target_site = (
                has_target_cookie
                or "animepahe" in title_lower
                or (
                    current_url
                    and "animepahe" in current_url.lower()
                    and not is_challenge_page
                )
            )

            if not is_target_site:
                return

            logger.info("Mobile solver verified challenge completion! Title: %s", title)
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            try:
                ua = (await webview.get_user_agent()) or ua
            except Exception as ex:
                logger.error("Failed to get UA: %s", ex)
            if not result_future.done():
                result_future.set_result((cookie_str, ua))

        async def on_console(e: WebViewConsoleMessageEvent):
            msg = e.message
            if msg.startswith("COOKIE:"):
                current_url = ""
                try:
                    current_url = (await webview.get_current_url()) or ""
                except Exception:
                    pass
                await _try_resolve(msg[7:].strip(), current_url=current_url)

        async def on_url_change(e):
            logger.info("WebView URL changed to: %s", e.data)
            # When we land on animepahe, try native cookie reader if challenge token is not present
            if _cookie_manager and "animepahe" in e.data and "__cf_chl" not in e.data:
                cookies = await _android_cookies(e.data)
                if cookies:
                    await _try_resolve(cookies, current_url=e.data)

        is_tv = original_platform == ft.PagePlatform.ANDROID_TV

        async def on_page_ended(e):
            logger.info("WebView page load ended: %s", e.data)
            # NOTE: we intentionally do NOT inject viewport/scale CSS or mutate
            # document.title here. Cloudflare's Turnstile challenge is a JS app
            # that watches the DOM; mutating it (body transform, viewport meta,
            # title) trips its integrity checks and causes the page to reload
            # itself — the reload loop seen on Android TV. We only disable zoom
            # via the official API, which does not disturb the page.
            try:
                await webview.disable_zoom()
                logger.info("WebView zoom disabled")
            except Exception as ex:
                logger.error("Error disabling zoom: %s", ex)

        webview = WebView(
            url=url,
            expand=True,
            on_console_message=on_console,
            on_url_change=on_url_change,
            on_page_ended=on_page_ended,
        )

        async def poll_cookies():
            try:
                await webview.set_javascript_mode(JavaScriptMode.UNRESTRICTED)
                logger.info("WebView JS mode set to UNRESTRICTED")
            except Exception as ex:
                logger.error("Error setting JS mode: %s", ex)

            while not result_future.done():
                current_url = ""
                try:
                    current_url = (await webview.get_current_url()) or ""
                except Exception:
                    pass

                # Primary (and on Android, the ONLY path that works for
                # cf_clearance): read native cookies via pyjnius. cf_clearance is
                # an HttpOnly cookie, so document.cookie can NEVER see it — the
                # native CookieManager is the real capture path on every device.
                if current_url and _cookie_manager:
                    cookies = await _android_cookies(current_url)
                    if cookies:
                        await _try_resolve(cookies, current_url=current_url)
                        if result_future.done():
                            break

                # Last-resort fallback ONLY when pyjnius is unavailable
                # (should not happen on Android, but kept defensively). Uses a
                # single READ-ONLY console.log — we deliberately avoid mutating
                # document.title, which previously disturbed the Cloudflare
                # challenge and caused the reload loop on Android TV.
                if _cookie_manager is None:
                    try:
                        await webview.run_javascript(
                            "console.log('COOKIE:' + (document.cookie || ''))"
                        )
                    except Exception:
                        pass

                # Poll every 1.5s instead of 0.5s. Native cookie reads are cheap
                # and non-intrusive, so the longer interval does not slow down
                # detection meaningfully — but it stops starving the Cloudflare
                # challenge JS of CPU on low-power TV hardware (the slowness).
                await asyncio.sleep(1.5)

        polling_task = asyncio.create_task(poll_cookies())

        loading_ring = ft.ProgressRing(color=ft.Colors.PRIMARY, stroke_width=4)

        dialog_width = 600 if is_tv else 360
        dialog_height = 450 if is_tv else 280

        wv_container = ft.Container(
            content=webview,
            width=dialog_width,
            height=dialog_height,
            border_radius=8,
            clip_behavior="antiAlias",
        )

        dialog_content = ft.Column(
            [
                ft.Text(
                    "Scroll down and verify you are human to continue.",
                    size=14,
                    weight=ft.FontWeight.W_500,
                ),
                ft.Container(height=4),
                ft.Row(
                    [loading_ring, ft.Text("Waiting for verification...", size=13)],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Container(height=8),
                wv_container,
            ],
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        def on_cancel(e):
            if not result_future.done():
                result_future.set_exception(
                    Exception("Verification cancelled by user.")
                )

        dlg = ft.AlertDialog(
            title=ft.Text("Security Verification", weight=ft.FontWeight.BOLD),
            content=dialog_content,
            actions=[ft.Button(content=ft.Text("Cancel"), on_click=on_cancel)],
            modal=True,
        )

        page.dialog_open = True
        page.show_dialog(dlg)
        page.update()

        original_on_keyboard = page.on_keyboard_event
        if is_tv:

            async def handle_tv_keys(e: ft.KeyboardEvent):
                key_map = {
                    "ArrowUp": (0, -120),
                    "ArrowDown": (0, 120),
                    "ArrowLeft": (-120, 0),
                    "ArrowRight": (120, 0),
                }
                if e.key in key_map:
                    dx, dy = key_map[e.key]
                    try:
                        await webview.scroll_by(dx, dy)
                    except Exception as ex:
                        logger.error("TV scroll error: %s", ex)
                    return
                if original_on_keyboard:
                    await original_on_keyboard(e)

            page.on_keyboard_event = handle_tv_keys
            page.update()

        try:
            cookies, ua = await result_future
            return cookies, ua
        finally:
            polling_task.cancel()
            page.dialog_open = False
            if is_tv and original_on_keyboard is not None:
                page.on_keyboard_event = original_on_keyboard
            elif is_tv:
                page.on_keyboard_event = None
            try:
                page.pop_dialog()
            except Exception:
                pass
            # Restore the original platform if it was overridden
            page.platform = original_platform
            page.update()
