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
            logger.info("Mobile solver: overriding ANDROID_TV -> ANDROID for flet_webview compatibility")
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

        async def _try_resolve(cookie_str: str):
            if "cf_clearance" in cookie_str:
                logger.info("Mobile solver captured cf_clearance!")
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
                await _try_resolve(msg[7:].strip())

        async def on_url_change(e):
            logger.info("WebView URL changed to: %s", e.data)
            # When we land on animepahe.com, try native cookie reader immediately
            if _cookie_manager and "animepahe" in e.data:
                cookies = await _android_cookies(e.data)
                if cookies:
                    await _try_resolve(cookies)

        webview = WebView(
            url=url,
            expand=True,
            on_console_message=on_console,
            on_url_change=on_url_change,
        )

        async def poll_cookies():
            try:
                await webview.set_javascript_mode(JavaScriptMode.UNRESTRICTED)
                logger.info("WebView JS mode set to UNRESTRICTED")
            except Exception as ex:
                logger.error("Error setting JS mode: %s", ex)

            reloaded = False

            while not result_future.done():
                current_url = ""
                try:
                    current_url = (await webview.get_current_url()) or ""
                except Exception:
                    pass

                # Primary: read native cookies via pyjnius (captures HttpOnly)
                if current_url and _cookie_manager:
                    cookies = await _android_cookies(current_url)
                    if cookies:
                        await _try_resolve(cookies)
                        if result_future.done():
                            break

                # Fallback: document.cookie (won't read HttpOnly but keep for safety)
                try:
                    await webview.run_javascript(
                        "document.title = 'COOKIE:' + (document.cookie || '')"
                    )
                    title = (await webview.get_title()) or ""
                except Exception as ex:
                    logger.error("Title poll error: %s", ex)
                    await asyncio.sleep(1.0)
                    continue

                if not reloaded and "enable javascript" in title.lower():
                    logger.warning(
                        "Detected 'Enable JavaScript' error, reloading with JS enabled..."
                    )
                    try:
                        await webview.set_javascript_mode(JavaScriptMode.UNRESTRICTED)
                        await webview.reload()
                    except Exception as ex:
                        logger.error("Reload error: %s", ex)
                    reloaded = True
                    await asyncio.sleep(2.0)
                    continue

                if title.startswith("COOKIE:"):
                    await _try_resolve(title[7:])
                    if result_future.done():
                        break

                try:
                    await webview.run_javascript(
                        "console.log('COOKIE:' + (document.cookie || ''))"
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        polling_task = asyncio.create_task(poll_cookies())

        loading_ring = ft.ProgressRing(color=ft.Colors.PRIMARY, stroke_width=4)

        wv_container = ft.Container(
            content=webview,
            width=360,
            height=280,
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

        try:
            cookies, ua = await result_future
            return cookies, ua
        finally:
            polling_task.cancel()
            page.dialog_open = False
            try:
                page.pop_dialog()
            except Exception:
                pass
            # Restore the original platform if it was overridden
            page.platform = original_platform
            page.update()
