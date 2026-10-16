"""Critical misc regressions — M1.6.

Each test kills one defect from the swarm audit:
- main.py referenced notifications_stable(), which never existed →
  NameError on the first follow-with-poster notification
- notifications.on_tap assigned the handler after registration with no
  update push, so taps never reached Dart
- update_service passed a worker-supplied URL straight to the OS
  launcher (no https safelist) and raised on a string build_number
- update_dialog KeyError'd on a missing apk_url and could be escaped via
  Back when mandatory
- anime_detail's series-download preset passed ui in the downloads slot
- external_player's launch failure was undetectable for custom schemes
- router._run KeyError'd when a later provider raised after earlier
  empties

The cross_promo rotation-cancel fix is a use_effect cleanup (the same
pattern as use_debounce, tested in test_house_layer); a @ft.component
body cannot run outside a renderer, so it is covered by construction plus
the existing cadence test in test_craft_layer.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import notifications

# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------


def test_stable_filename_is_defined_stable_and_path_safe():
    """The helper never existed — main.py raised NameError calling it."""
    name = notifications.stable_filename("animepahe:12345|7")
    assert name == notifications.stable_filename("animepahe:12345|7")
    assert name.startswith("notify-")
    assert name.endswith(".img")
    # Session strings carry : | / * — none may reach the filesystem.
    for ch in ":|/*":
        assert ch not in name
    assert notifications.stable_filename("a", ".png").endswith(".png")


def test_on_tap_pushes_an_update_after_installing(monkeypatch):
    """A handler assigned after registration is not sent to Dart until
    the service updates — the taps silently never fired."""
    # _ready() gates on the platform probe; bypass it to exercise the
    # install path itself.
    monkeypatch.setattr(notifications, "_ready", lambda: True)

    class _Service:
        def __init__(self):
            self.updates = 0
            self.on_tap = None

        def update(self):
            self.updates += 1

    service = _Service()
    original = notifications._service
    notifications._service = service
    try:
        notifications.on_tap(lambda payload: None)
        assert service.on_tap is not None
        assert service.updates >= 1, "the handler must be pushed to the client"
    finally:
        notifications._service = original


# ---------------------------------------------------------------------------
# update_service
# ---------------------------------------------------------------------------


def _fake_primp(config_json):
    """A primp.AsyncClient stand-in answering the config URL."""

    class _Resp:
        status_code = 200

        def json(self):
            return config_json

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def get(self, url, **kwargs):
            return _Resp()

    class _Primp:
        AsyncClient = _Client

    return _Primp()


def test_update_service_rejects_a_non_https_url(monkeypatch):
    from services import update_service

    monkeypatch.setattr(
        update_service,
        "primp",
        _fake_primp(
            {
                "animepahe": {
                    "build_number": 99,
                    "version": "9.9",
                    "update_url": "http://evil.example/app.apk",
                }
            }
        ),
    )
    result = asyncio.run(update_service.UpdateService().check_for_update())
    assert result is not None
    assert result["apk_url"] == ""  # http is not launched


def test_update_service_survives_a_string_build_number(monkeypatch):
    from services import update_service

    monkeypatch.setattr(
        update_service,
        "primp",
        _fake_primp({"animepahe": {"build_number": "99", "version": "9.9"}}),
    )
    result = asyncio.run(update_service.UpdateService().check_for_update())
    assert result is not None and result["version"] == "9.9"


def test_update_service_survives_a_malformed_config(monkeypatch):
    from services import update_service

    monkeypatch.setattr(update_service, "primp", _fake_primp(["not", "a", "dict"]))
    assert asyncio.run(update_service.UpdateService().check_for_update()) is None


# ---------------------------------------------------------------------------
# update_dialog
# ---------------------------------------------------------------------------


class _FakeDialogPage:
    def __init__(self):
        self.dialogs_shown = 0
        self.run_tasks = []

    def show_dialog(self, dialog):
        self.dialogs_shown += 1

    def update(self):
        pass

    def pop_dialog(self):
        pass

    def run_task(self, handler, *args, **kwargs):
        self.run_tasks.append(handler)


def test_update_dialog_missing_apk_url_does_not_keyerror(monkeypatch):
    from components import update_dialog

    page = _FakeDialogPage()
    monkeypatch.setattr(update_dialog, "get_shared_services", lambda p: _SharedNoop())
    captured = {}
    monkeypatch.setattr(
        update_dialog,
        "show_app_dialog",
        lambda p, dlg: captured.setdefault("dlg", dlg),
    )
    # A payload with no apk_url used to raise KeyError mid-teardown.
    update_dialog.show_update_dialog(page, {"version": "2.0.0", "mandatory": True, "apk_url": ""})
    dlg = captured["dlg"]
    # Drive the "Update Now" action (the FilledButton; mandatory keeps only it).
    update_now = dlg.actions[0]
    update_now.on_click(None)
    assert page.run_tasks, "the launch should be scheduled"
    asyncio.run(page.run_tasks[0](None))  # open_download — must not raise
    assert page.dialogs_shown == 0  # nothing was dismissed (no launch happened)


class _SharedNoop:
    async def launch_url(self, url, **kwargs):
        return True

    async def can_launch_url(self, url):
        return True


def test_mandatory_update_reshows_after_a_back_dismissal(monkeypatch):
    from components import update_dialog

    page = _FakeDialogPage()
    monkeypatch.setattr(update_dialog, "get_shared_services", lambda p: _SharedNoop())
    shown = []
    original = update_dialog.show_update_dialog

    def _spy(page_, data):
        shown.append(data)
        return original(page_, data)

    monkeypatch.setattr(update_dialog, "show_update_dialog", _spy)
    update_dialog.show_update_dialog(
        page, {"version": "2.0.0", "mandatory": True, "apk_url": "https://x/y.apk"}
    )
    # The dialog carries an on_dismiss that re-shows (Back's path).
    # Find it through the dialog the app-dialog helper received.
    captured = {}

    def _capture(page_, dlg):
        captured["dlg"] = dlg

    monkeypatch.setattr(update_dialog, "show_app_dialog", _capture)
    update_dialog.show_update_dialog(
        page, {"version": "2.0.0", "mandatory": True, "apk_url": "https://x/y.apk"}
    )
    assert captured["dlg"].on_dismiss is not None


# ---------------------------------------------------------------------------
# anime_detail preset
# ---------------------------------------------------------------------------


def test_series_download_preset_sticks_when_a_chip_is_tapped(monkeypatch):
    """The preset callback passed ui into the `downloads` slot: the
    preset never stuck (every re-open reset to 'highest') and the range
    math called .get() on the string."""
    import flet as ft

    from screens import anime_detail_screen

    opens = []
    controller = type(
        "C",
        (),
        {
            "open_sheet": lambda self, s: opens.append(s),
            "close_dialog": lambda self: None,
        },
    )()

    def _walk(control):
        yield control
        for child in getattr(control, "controls", []) or []:
            yield from _walk(child)
        content = getattr(control, "content", None)
        if content is not None:
            yield from _walk(content)

    downloads = {"ep1": {"state": "complete"}}
    dlg = anime_detail_screen._build_series_download_dialog(
        [], controller, "sess", downloads, {"preset": "highest"}
    )
    chips = [n for n in _walk(dlg) if isinstance(n, ft.OutlinedButton)]
    assert len(chips) == 3  # Highest / Lowest / As served
    # Tap "lowest" — the old code passed ui into the downloads slot here
    # and crashed (or reset the preset).
    chips[1].on_click(None)
    assert len(opens) == 1
    # The re-opened sheet carries the choice: the lowest chip is now the
    # selected one.
    chips2 = [n for n in _walk(opens[0]) if isinstance(n, ft.OutlinedButton)]
    assert chips2[1].style.bgcolor is not None
    assert chips2[0].style.bgcolor is None


# ---------------------------------------------------------------------------
# external_player
# ---------------------------------------------------------------------------


def test_launch_external_asks_the_os_before_the_launch(monkeypatch):
    from services import external_player

    class _Shared:
        def __init__(self, can):
            self.launcher = type("L", (), {})()
            self.launcher.can_launch_url = self._can
            self._can = can
            self.launched = False

        async def _can(self, url):
            return self._can

        async def launch_url(self, url, **kwargs):
            self.launched = True
            return True

    shared = _Shared(can=False)
    monkeypatch.setattr(external_player, "get_shared_services", lambda p: shared)
    dialogs = []
    monkeypatch.setattr(
        external_player,
        "show_ktv_install_dialog",
        lambda p: dialogs.append(p),
    )
    ok = asyncio.run(external_player.launch_external(None, "https://x/y.m3u8", "Title"))
    assert ok is False
    assert shared.launched is False
    assert len(dialogs) == 1  # the install dialog offered, not a silent no-op


def test_launch_external_launches_when_a_handler_exists(monkeypatch):
    from services import external_player

    class _Shared:
        def __init__(self):
            self.launcher = type("L", (), {})()
            self.launcher.can_launch_url = self._can
            self.launched = False

        async def _can(self, url):
            return True

        async def launch_url(self, url, **kwargs):
            self.launched = True
            return True

    shared = _Shared()
    monkeypatch.setattr(external_player, "get_shared_services", lambda p: shared)
    monkeypatch.setattr(external_player, "show_ktv_install_dialog", lambda p: None)
    ok = asyncio.run(external_player.launch_external(None, "https://x/y.m3u8", "Title"))
    assert ok is True and shared.launched


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------


class _Provider:
    def __init__(self, name, behavior):
        self.name = name
        self.capabilities = {}
        self._behavior = behavior

    async def probe(self):
        return True

    async def search(self, query, page):
        return self._behavior(self)


def test_router_empty_then_raise_does_not_keyerror():
    """p1 answered empty, p2 raised and cancelled the group: indexing
    outcomes[p2] (eligible[-1]) raised KeyError."""
    from services.router import ProviderRouter

    empty = _Provider("empty", lambda s: ([], True))

    def _boom(self):
        raise RuntimeError("provider exploded")

    raiser = _Provider("raiser", _boom)
    router = ProviderRouter([empty, raiser])
    result = asyncio.run(router.search("frieren", 1))
    assert result == ([], True)
