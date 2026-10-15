"""Solver crash/hang regressions — M1.5.

Each test kills one defect from the swarm audit:
- desktop_cf_solver: the user closing the window left the 2-minute poll
  running (parent hung); timeouts exited 0, indistinguishable from success
- webview_solver: ANDROID_TV (a real PagePlatform) fails every WebView
  method (gated to Android/iOS/macOS) and the solver spun forever; the
  unbounded waits could pin the app open
- kwik_resolver: the verification HEAD request derived its Referer from
  the CDN URL instead of the kwik page; unguarded fetches raised
- ddos_solver: get() could call solve() twice; concurrent gets shared one
  verification window; the re-solve reused the stale-cookie client pool
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft  # noqa: E402
import pytest  # noqa: E402

from services.kwik_resolver import KwikResolver  # noqa: E402


# ---------------------------------------------------------------------------
# desktop_cf_solver
# ---------------------------------------------------------------------------


class _ClosedEvent:
    def is_set(self):
        return True


class _NotClosedEvent:
    def is_set(self):
        return False


class _Events:
    def __init__(self, closed):
        self.closed = closed


class _SolverExited(Exception):
    """Mirrors os._exit: the real _fail never returns."""


def test_desktop_solver_exits_when_the_user_closes_the_window():
    """The hang: the 120×1s poll kept calling get_cookies() on a dead
    window and the parent's communicate() never returned."""
    import services.desktop_cf_solver as dcs

    class _Window:
        def __init__(self):
            self.events = _Events(_ClosedEvent())

        def get_cookies(self):
            raise AssertionError("must not poll a closed window")

    calls = []

    def _fail(reason):
        calls.append(reason)
        raise _SolverExited(reason)

    dcs._fail = _fail  # type: ignore[assignment]
    with pytest.raises(_SolverExited):
        dcs.check_cookies(_Window())
    assert calls == ["closed"]


def test_desktop_solver_timeout_reports_an_error(monkeypatch):
    import services.desktop_cf_solver as dcs

    class _Window:
        def __init__(self):
            self.events = _Events(_NotClosedEvent())

        def get_cookies(self):
            return []

        def destroy(self):
            pass

    monkeypatch.setattr(dcs.time, "sleep", lambda _s: None)  # instant loop
    calls = []

    def _fail(reason):
        calls.append(reason)
        raise _SolverExited(reason)

    monkeypatch.setattr(dcs, "_fail", _fail)
    with pytest.raises(_SolverExited):
        dcs.check_cookies(_Window())
    assert calls == ["timeout"]


def test_is_challenge_complete_matches_target_cookies_case_insensitively():
    from services.desktop_cf_solver import is_challenge_complete

    class _Window:
        def evaluate_js(self, script):
            return ""

        def get_current_url(self):
            return "https://animepahe.com/"

    # Real Set-Cookie headers arrive with original casing.
    assert is_challenge_complete(
        _Window(), {"cf_clearance", "XSRF-TOKEN", "animepahe_session"}
    )


# ---------------------------------------------------------------------------
# webview_solver — TV platform fallback
# ---------------------------------------------------------------------------


class _FakeWebViewModule:
    """Stands in for flet_webview: the TV shape raises the platform gate."""

    class _WebView:
        def __init__(self, **kwargs):
            self.page = None
            for k, v in kwargs.items():
                setattr(self, k, v)

        async def get_current_url(self):
            raise ft.FletUnsupportedPlatformException(
                "supported on Android, iOS and macOS only"
            )

        async def set_javascript_mode(self, mode):
            raise AssertionError("must not run on an unsupported platform")

        async def disable_zoom(self):
            raise AssertionError("must not run on an unsupported platform")

    WebView = _WebView
    WebViewConsoleMessageEvent = dict
    JavaScriptMode = type("JavaScriptMode", (), {"UNRESTRICTED": "unrestricted"})


class _TvPage:
    """A page that reports ANDROID_TV — the platform that gates WebView."""

    platform = ft.PagePlatform.ANDROID_TV

    def show_dialog(self, dialog):
        pass

    def update(self):
        pass

    def pop_dialog(self):
        pass

    on_keyboard_event = None


def test_tv_platform_falls_back_to_the_desktop_solver(monkeypatch):
    """flet_webview's allow-list excludes ANDROID_TV: every method raises
    FletUnsupportedPlatformException, so the mobile path must fail over
    to the desktop solver instead of spinning forever."""
    import services.webview_solver as wvs

    monkeypatch.setitem(sys.modules, "flet_webview", _FakeWebViewModule)
    fell_back = []
    monkeypatch.setattr(
        wvs.WebViewSolver,
        "_solve_desktop",
        staticmethod(lambda page, url: _recorder(fell_back, page, url)),
    )

    async def _recorder(fell_back, page, url):
        fell_back.append(url)
        return ("cookies", "ua")

    cookies, ua = asyncio.run(
        wvs.WebViewSolver.solve_challenge(_TvPage(), "https://animepahe.com/")
    )
    assert fell_back == ["https://animepahe.com/"]
    assert (cookies, ua) == ("cookies", "ua")


# ---------------------------------------------------------------------------
# kwik_resolver
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _RecordingClient:
    """Records head()/get() calls; head answers like a CDN m3u8."""

    def __init__(self, get_error=None, head_status=200, head_ct="application/vnd.apple.mpegurl"):
        self.heads = []
        self.gets = []
        self._get_error = get_error
        self._head_status = head_status
        self._head_ct = head_ct

    async def head(self, url, headers=None, timeout=None):
        self.heads.append((url, headers or {}))
        return _FakeResp(self._head_status, headers={"content-type": self._head_ct})

    async def get(self, url, headers=None, **kwargs):
        self.gets.append((url, headers or {}))
        if self._get_error is not None:
            raise self._get_error
        return _FakeResp(200, text="#EXTM3U")


def test_verify_uses_the_kwik_page_as_referer():
    """The HEAD request derived its Referer from the CDN's own URL, which
    always fell back to the wrong host."""
    client = _RecordingClient()
    resolver = KwikResolver()
    resolver._client = client  # type: ignore[assignment]
    ok = asyncio.run(
        resolver._verify("https://cdn-six.example/stream.m3u8", "https://kwik.si/e/ABC")
    )
    assert ok is True
    url, headers = client.heads[0]
    assert headers["Referer"] == "https://kwik.si/"


def test_fetch_failures_return_none_not_an_exception():
    """The documented None contract used to leak transport errors."""
    client = _RecordingClient(get_error=ConnectionError("dns"))
    resolver = KwikResolver()
    resolver._client = client  # type: ignore[assignment]
    assert asyncio.run(resolver._resolve_dean("https://kwik.si/e/ABC")) is None
    assert asyncio.run(resolver._resolve_direct_scan("https://kwik.si/e/ABC")) is None


def test_verify_is_case_insensitive_about_the_content_type():
    client = _RecordingClient(head_ct="application/X-MpegURL")
    resolver = KwikResolver()
    resolver._client = client  # type: ignore[assignment]
    assert asyncio.run(resolver._verify("https://x/y.m3u8", "https://kwik.cx/")) is True


# ---------------------------------------------------------------------------
# ddos_solver — one solve gate
# ---------------------------------------------------------------------------


class _FakeStore:
    async def get_clearance(self):
        return {}

    async def clear_clearance(self):
        pass

    async def save_clearance(self, cookies, ua, host=None):
        pass


def test_get_solves_at_most_once_per_call(monkeypatch):
    """The rewrite branch and the plain branch each called solve() — an
    unsolved state opened the verification window twice."""
    from services.ddos_solver import DDoSSolver

    solver = DDoSSolver()
    solver.solve_allowed = False  # solve() stays a cheap no-op failure
    solver._store = _FakeStore()
    calls = []
    original = solver.solve

    async def counting_solve():
        calls.append(1)
        return await original()

    solver.solve = counting_solve

    class _Resp:
        status_code = 200
        text = "{}"

        @property
        def url(self):
            return "https://animepahe.com/api"

    class _Client:
        async def get(self, url, **kwargs):
            return _Resp()

        async def __aexit__(self, *exc):
            return None

    solver._client = _Client()
    asyncio.run(solver.get("https://animepahe.com/api"))
    assert len(calls) == 1


def test_re_solve_rebuilds_the_stale_cookie_client(monkeypatch):
    """The re-solve reused the same primp client whose cookie_store held
    the dead cf_clearance and resent it."""
    from services.ddos_solver import DDoSSolver

    solver = DDoSSolver()
    solver.solve_allowed = False
    solver._store = _FakeStore()
    solver._solved = True
    solver._cookies_str = "cf_clearance=dead"

    closed = []
    original_close = solver.close

    async def counting_close():
        closed.append(1)
        return await original_close()

    solver.close = counting_close

    class _ChallengeResp:
        status_code = 200
        text = "<html>Just a moment...</html>"

    class _Client:
        async def get(self, url, **kwargs):
            return _ChallengeResp()

        async def __aexit__(self, *exc):
            return None

    solver._client = _Client()
    asyncio.run(solver.get("https://animepahe.com/api"))
    assert closed, "the client must be rebuilt before the re-solve"


def test_desktop_solver_bails_on_plain_server_pages():
    """The owner saw pywebview sit on an nginx page for the full two-minute
    wait: a plainly non-challenge page must fail fast with a message the
    parent surfaces, not poll for cf_clearance that will never come."""
    from services.desktop_cf_solver import served_a_plain_page

    class _Win:
        def __init__(self, title):
            self._title = title

        def evaluate_js(self, _expr):
            return self._title

    assert served_a_plain_page(_Win("Welcome to nginx!")) == "Welcome to nginx!"
    assert served_a_plain_page(_Win("502 Bad Gateway")) == "502 Bad Gateway"
    assert served_a_plain_page(_Win("Index of /")) == "Index of /"
    assert served_a_plain_page(_Win("Just a moment...")) is None
    assert served_a_plain_page(_Win("AnimePahe")) is None
    assert served_a_plain_page(_Win("")) is None
