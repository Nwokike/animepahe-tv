"""The CF completion judge must be ONE rule for BOTH transports.

Owner's report (2026-10-20): "I just opened my phone, the same anime that
works here. Select an anime in animeout, solve the captcha, 403 page,
waiting for verification. It did not capture the clearance... But that of
animepahe works, so I want you to investigate because since we implemented
solver for animeout, I've never tested it on my phone."

The cause was not animeout's wall — it was that the phone's solver and
the desktop solver each carried their OWN copy of "is the challenge
done?", and the phone's copy named animepahe in three places:

* the completion markers were animepahe's session cookies only
* "is this the target site" required the literal title/URL string
  ``animepahe``
* the navigation handler read cookies only on
  ``"animepahe" in current_url``

AnimePahe is the only source whose phone solve the owner had ever
exercised, so the drift went unnoticed: every other source's phone
solve sat on "Waiting for verification..." over a challenge that had
already cleared, and timed out with nothing captured. On desktop the
same animeout solve succeeded because the pywebview child's judge fell
through to "a plain web-server page means the origin answered".

These tests pin the shared rule (services/cf_judge.py) against every
host in the fixed order, so a change that makes one transport host-blind
again fails here instead of on the owner's phone.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft
import pytest

from services.cf_judge import challenge_complete, is_hard_blocked, target_host_of

# Every source in the fixed order, with the URL the app actually hands the
# solver for it. AniKato and Kayoanime answer with no challenge at all
# (the order is built on that), so the solveable hosts are the two the
# owner flags.
_PAHE_URL = "https://animepahe.pw/"
_OUT_URL = "https://public.animeout.xyz/"


# ---------------------------------------------------------------------------
# target_host_of — the label a site would put in its own title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://animepahe.pw/", "animepahe"),
        ("https://animepahe.pw/anime/x", "animepahe"),
        ("https://www.animepahe.com/", "animepahe"),
        ("https://public.animeout.xyz/nimbus.animeout.com/series/x.mkv", "animeout"),
        ("https://animeout.xyz/", "animeout"),
        ("http://ddl.animeout.com/index.php?url=x", "animeout"),
        ("", ""),
        ("not a url", ""),
    ],
)
def test_target_host_reads_the_label_the_site_puts_in_its_title(url, expected):
    """The registrable label, not the subdomain: a page titled
    "AnimeOut - ..." never contains the string "public.animeout.xyz"."""
    assert target_host_of(url) == expected


# ---------------------------------------------------------------------------
# The rule itself, per host
# ---------------------------------------------------------------------------


def test_animepahe_still_completes_on_its_own_cookie():
    """The host that always worked must keep working: its session cookie
    is enough, even when the title read raced the navigation."""
    assert challenge_complete(
        cookie_keys={"cf_clearance", "animepahe_session"},
        url=_PAHE_URL,
        title="",
        target_host=target_host_of(_PAHE_URL),
    )


def test_animeout_completes_with_only_a_clearance_and_its_own_host():
    """THE REGRESSION. public.animeout.xyz sets no session cookies of its
    own — after the challenge clears it answers an nginx 403, and the jar
    holds cf_clearance and nothing else. The only signal available is
    "we are on the host we were asked to clear", which the phone solver
    never looked for."""
    assert challenge_complete(
        cookie_keys={"cf_clearance"},
        url=_OUT_URL,
        title="403 Forbidden",
        target_host=target_host_of(_OUT_URL),
    )


def test_animeout_completes_on_a_site_title_too():
    """The same clearance, reached when the host serves a real page: the
    title naming the site is a positive signal for a host with no
    cookies."""
    assert challenge_complete(
        cookie_keys={"cf_clearance"},
        url="https://public.animeout.xyz/series/Ongoing/Naruto/",
        title="AnimeOut — Direct Download Free Encoded Animes",
        target_host=target_host_of(_OUT_URL),
    )


def test_animeout_completes_on_a_plain_nginx_landing():
    """The documented landing (backend-animeout.md §3.1): the origin
    answers a plain web-server page with only cf_clearance in the jar."""
    assert challenge_complete(
        cookie_keys={"cf_clearance"},
        url=_OUT_URL,
        title="Welcome to nginx",
        target_host=target_host_of(_OUT_URL),
    )


def test_an_unrelated_host_never_completes():
    """A clearance plus a page that names neither the target host nor a
    web server is not evidence — the poll must keep waiting."""
    assert not challenge_complete(
        cookie_keys={"cf_clearance"},
        url="https://example.invalid/",
        title="Some unrelated page",
        target_host="animeout",
    )


# ---------------------------------------------------------------------------
# The negatives — a challenge in progress is never done
# ---------------------------------------------------------------------------


def test_a_running_challenge_is_never_complete():
    assert not challenge_complete(
        cookie_keys={"cf_clearance"},
        url="https://public.animeout.xyz/?__cf_chl_opt_tries=1",
        title="AnimeOut",
        target_host="animeout",
    )


def test_an_empty_title_is_never_complete():
    """The regression that shipped an unusable pahe clearance: a title
    read racing a navigation comes back "" rather than a challenge word."""
    assert not challenge_complete(
        cookie_keys={"cf_clearance"}, url=_OUT_URL, title="", target_host="animeout"
    )


def test_no_clearance_is_never_complete():
    """Even on the right host with the right title: no cookie, nothing to
    ship."""
    assert not challenge_complete(
        cookie_keys=set(), url=_OUT_URL, title="AnimeOut", target_host="animeout"
    )


def test_a_hard_block_is_a_failure_not_a_wait():
    assert is_hard_blocked("Sorry, you have been blocked")
    assert not challenge_complete(
        cookie_keys={"cf_clearance", "animepahe_session"},
        url=_PAHE_URL,
        title="Attention Required! | Cloudflare",
        target_host="animepahe",
    )


# ---------------------------------------------------------------------------
# The DESKTOP solver must read the same rule (the drift this pins)
# ---------------------------------------------------------------------------


class _JudgeWindow:
    """A pywebview-shaped window: URL, title, cookies, on any host."""

    def __init__(self, url, title, cookies):
        self._url = url
        self._title = title
        self._cookies = cookies
        self.original_url = url

    def get_current_url(self):
        return self._url

    def evaluate_js(self, script):
        if "document.title" in script:
            return self._title
        return ""

    def get_cookies(self):
        return [SimpleCookie(k, v) for k, v in self._cookies]


class SimpleCookie:
    """The morsel shape the desktop child iterates."""

    def __init__(self, name, value):
        self._name = name
        self._value = value

    def items(self):
        return ((self._name, _Morsel(self._value)),)


class _Morsel:
    def __init__(self, value):
        self.value = value


@pytest.mark.parametrize("host_url", [_PAHE_URL, _OUT_URL])
def test_the_desktop_judge_delegates_to_the_shared_rule(host_url):
    """Both transports must answer alike for the same facts. The desktop
    child's own copy used to differ from the phone's — that drift is the
    bug, so this is the pin that they cannot drift again."""
    from services.desktop_cf_solver import is_challenge_complete

    win = _JudgeWindow(host_url, "403 Forbidden", [("cf_clearance", "abc")])
    assert is_challenge_complete(win, {"cf_clearance"}) is True


# ---------------------------------------------------------------------------
# The MOBILE solver must read the same rule
# ---------------------------------------------------------------------------


class _FakeWebViewModule:
    class _WebView:
        def __init__(self, **kwargs):
            self.page = None
            self._title = "403 Forbidden"
            for k, v in kwargs.items():
                setattr(self, k, v)

        async def get_current_url(self):
            return _OUT_URL

        async def get_title(self):
            return self._title

        async def get_user_agent(self):
            return "Mozilla/5.0 (Android) TestWebView"

    WebView = _WebView
    WebViewConsoleMessageEvent = dict
    JavaScriptMode = type("JavaScriptMode", (), {"UNRESTRICTED": "unrestricted"})


class _AndroidPage:
    """A page that reports ANDROID: the platform the phone solve uses."""

    platform = ft.PagePlatform.ANDROID
    on_keyboard_event = None

    def show_dialog(self, dialog):
        pass

    def update(self):
        pass

    def pop_dialog(self):
        pass


def _run_mobile_solve(monkeypatch, webview_module, url):
    """Drive the phone path once with a cookie jar and read what it
    captured. Returns (cookies, ua), or raises when it never captures."""
    import services.webview_solver as wvs

    monkeypatch.setitem(sys.modules, "flet_webview", webview_module)
    monkeypatch.setitem(sys.modules, "jnius", _FakeJnius())

    # The real budget is 300 s; a test must not sit out a timeout to
    # prove nothing was captured.
    monkeypatch.setattr(wvs, "MOBILE_SOLVER_TIMEOUT", 0.25)

    # Speed the 1.5 s poll up — but STILL yield: a fake sleep that
    # returns without awaiting makes the poll loop unable to observe the
    # cancellation its own `finally` issues, and the test would hang
    # forever instead of finishing.
    async def _fast_sleep(_seconds):
        await asyncio.sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    async def _drive():
        return await wvs.WebViewSolver._solve_mobile(_AndroidPage(), url)

    return asyncio.run(_drive())


class _FakeJnius:
    """Stands in for pyjnius: the solver asks for the CookieManager
    singleton and then reads a cookie string for the current URL."""

    @staticmethod
    def getCookie(url):
        return "cf_clearance=abc; other=1"

    @staticmethod
    def autoclass(name):
        class _CookieManager:
            # The solver's shape: `CookieManager.getInstance().getCookie(url)`.
            getInstance = staticmethod(lambda: _FakeJnius)

        return _CookieManager


def test_the_phone_solver_captures_a_non_animepahe_host(monkeypatch):
    """THE OWNER'S BUG, end to end on the phone path: solve animeout and
    the clearance is captured, not timed out.

    Before the shared judge this raised VerificationError (the mobile
    path's own completion test demanded 'animepahe' in the title/URL), so
    the app reported "Waiting for verification..." forever and shipped
    nothing."""
    cookies, ua = _run_mobile_solve(monkeypatch, _FakeWebViewModule, _OUT_URL)
    assert "cf_clearance" in cookies
    assert ua


def test_the_phone_solver_still_captures_animepahe(monkeypatch):
    """The host that always worked must keep working on the phone too."""
    cookies, _ua = _run_mobile_solve(monkeypatch, _FakeWebViewModule, _PAHE_URL)
    assert "cf_clearance" in cookies


def test_the_phone_solver_does_not_capture_while_the_challenge_runs(monkeypatch):
    """A challenge page is never completion evidence, on any host."""

    class _StillChallenging(_FakeWebViewModule._WebView):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._title = "Just a moment..."
            self._challenge_url = "https://public.animeout.xyz/?__cf_chl_tk=abc"

        async def get_current_url(self):
            return self._challenge_url

        async def get_title(self):
            return self._title

    class _Module(_FakeWebViewModule):
        WebView = _StillChallenging

    # The wait times out — nothing was captured, which is the point.
    with pytest.raises(TimeoutError):
        _run_mobile_solve(monkeypatch, _Module, _OUT_URL)


# ---------------------------------------------------------------------------
# The desktop child is a STANDALONE subprocess
# ---------------------------------------------------------------------------


def test_the_desktop_subprocess_can_import_the_shared_judge():
    """The desktop solver runs as `python desktop_cf_solver.py <url>` —
    a fresh interpreter whose sys.path does NOT include ``src/``.

    The first shared judge broke that: ``from services.cf_judge import
    ...`` raised ModuleNotFoundError inside the child's own cookie poll,
    so the desktop solve that had WORKED for months stopped capturing
    (the owner's run, 2026-10-20 — every poll printed "Error reading
    cookies: No module named 'services'" and the window was closed with
    nothing saved).

    The child therefore bootstraps ``src/`` onto its own sys.path at
    import time. This test loads the module the way the subprocess does
    and asserts the shared judge is reachable from it.
    """
    import importlib.util
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent / "src"
    script = src / "services" / "desktop_cf_solver.py"
    assert script.exists(), script
    assert (src / "services" / "cf_judge.py").exists()

    sys.path.insert(0, str(src))
    try:
        spec = importlib.util.spec_from_file_location("desktop_cf_solver", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(src))

    # The judge is importable in that process, which is what the child's
    # own poll needs — prove it through the path the child actually uses.
    resolved = pathlib.Path(module._PROJECT_SRC)
    assert resolved == src, (
        f"the child resolved the wrong project root: {resolved}"
    )
    from services.cf_judge import challenge_complete

    assert callable(challenge_complete)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
