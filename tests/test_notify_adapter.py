"""The notifications adapter against the INSTALLED flet-notifications 0.1.3.

This adapter was written against APIs that do not exist in the installed
package (create_channel, a details= kwarg, BigPictureStyle(image_file_path=...)),
so the whole engine was dead weight. These tests pin the real shapes so it
cannot drift again: a fake service records the exact calls.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-notify-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

import pytest  # noqa: E402

import core.notifications as notifications  # noqa: E402


class _Event:
    def __init__(self, payload):
        self.payload = payload


class _FakeService:
    """Records every call the adapter makes; nothing raises."""

    def __init__(self, permissions: bool = True, raises: Exception | None = None):
        self.permissions = permissions
        self.raises = raises
        self.channels: list = []
        self.shown: list[dict] = []
        self.on_tap = None

    async def request_permissions(self) -> bool:
        if self.raises:
            raise self.raises
        return self.permissions

    async def create_notification_channel(self, channel) -> None:
        if self.raises:
            raise self.raises
        self.channels.append(channel)

    async def show(self, **kwargs) -> None:
        self.shown.append(kwargs)


@pytest.fixture(autouse=True)
def _clean_session(monkeypatch):
    """The dev-mode detection is session state: reset it per test so a test
    that fails on purpose can't poison the ones after it."""
    monkeypatch.setattr(notifications, "_unavailable", False)
    yield
    monkeypatch.setattr(notifications, "_unavailable", False)


@pytest.fixture
def fake(monkeypatch):
    service = _FakeService()
    monkeypatch.setattr(notifications, "_available", True)
    monkeypatch.setattr(notifications, "_service", service)
    return service


def _off_platform(monkeypatch):
    monkeypatch.setattr(notifications, "_available", False)
    monkeypatch.setattr(notifications, "_service", None)


# ---------------------------------------------------------------------------
# The channel (the call that never existed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_channel_creates_the_new_episodes_channel_at_high(fake):
    from flet_notifications.channels import NotificationChannel
    from flet_notifications.types import Importance

    assert await notifications.ensure_channel() is True

    (channel,) = fake.channels
    assert isinstance(channel, NotificationChannel)
    assert channel.id == notifications.CHANNEL_NEW_EPISODES
    assert channel.importance is Importance.HIGH
    assert channel.name and channel.description


@pytest.mark.asyncio
async def test_ensure_channel_is_quiet_when_the_service_refuses(fake):
    fake.raises = RuntimeError("no platform")
    assert await notifications.ensure_channel() is False


# ---------------------------------------------------------------------------
# The show shape (BigPicture is a required AndroidIcon, not a path string)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_show_new_episode_carries_the_payload_channel_and_big_picture(
    fake, tmp_path
):
    poster = tmp_path / "poster.img"
    poster.write_bytes(b"img")

    assert (
        await notifications.show_new_episode(
            anime_session="anikato:naruto",
            title="Naruto",
            episode=221,
            poster_path=str(poster),
        )
        is True
    )

    (call,) = fake.shown
    assert call["id"] == notifications.stable_id("anikato:naruto")
    assert call["payload"] == "animepahe://anime/anikato:naruto"
    assert call["channel_id"] == notifications.CHANNEL_NEW_EPISODES
    assert call["title"] == "Naruto — Episode 221"
    assert "details" not in call  # the kwarg the old code invented

    from flet_notifications.styles import AndroidIcon, BigPictureStyle

    style = call["style"]
    assert isinstance(style, BigPictureStyle)
    assert isinstance(style.image, AndroidIcon)
    assert style.image.file_path == str(poster)


@pytest.mark.asyncio
async def test_show_new_episode_without_a_poster_omits_the_style(fake):
    """AndroidIcon requires exactly one source, so a missing poster must
    mean NO style rather than a broken one."""
    await notifications.show_new_episode(
        anime_session="s1", title="T", episode=1, poster_path=None
    )
    assert fake.shown[0]["style"] is None


@pytest.mark.asyncio
async def test_show_progress_is_one_notification_advanced_by_id(fake):
    await notifications.show_progress(
        notification_id=42,
        title="Downloading",
        body="Episode 3",
        payload="animepahe://anime/s1",
        progress=30,
        max_progress=100,
    )
    call = fake.shown[0]
    assert call["id"] == 42
    assert call["show_progress"] is True
    assert (call["progress"], call["max_progress"]) == (30, 100)

    # The same id again advances the same row.
    await notifications.show_progress(
        notification_id=42,
        title="Downloading",
        body="Episode 3",
        progress=90,
        max_progress=100,
    )
    assert [c["progress"] for c in fake.shown] == [30, 90]


# ---------------------------------------------------------------------------
# Permissions + the tap deep-link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_permissions_returns_the_service_answer(fake):
    assert await notifications.request_permissions() is True
    fake.permissions = False
    assert await notifications.request_permissions() is False


@pytest.mark.asyncio
async def test_request_permissions_never_raises(monkeypatch):
    service = _FakeService(raises=RuntimeError("denied"))
    monkeypatch.setattr(notifications, "_available", True)
    monkeypatch.setattr(notifications, "_service", service)
    assert await notifications.request_permissions() is False


def test_on_tap_dispatches_the_payload_and_ignores_foreign_ones(monkeypatch):
    service = _FakeService()
    monkeypatch.setattr(notifications, "_available", True)
    monkeypatch.setattr(notifications, "_service", service)
    seen: list[str] = []
    notifications.on_tap(seen.append)

    assert service.on_tap is not None
    service.on_tap(_Event("animepahe://anime/anikato:naruto"))
    service.on_tap(_Event("https://example.com/other-app"))
    assert seen == ["animepahe://anime/anikato:naruto"]


def test_handle_payload_decodes_ours_and_rejects_everything_else():
    assert (
        notifications.handle_payload("animepahe://anime/kayoanime:12") == "kayoanime:12"
    )
    for junk in (
        None,
        "",
        "animepahe://anime/",
        "other://anime/x",
        "animepahe://episode/1",
    ):
        assert notifications.handle_payload(junk) is None


def test_stable_id_is_stable_and_in_range():
    first = notifications.stable_id("anikato:naruto")
    assert first == notifications.stable_id("anikato:naruto")
    assert notifications.stable_id("anikato:sasuke") != first
    assert 0 <= first < 2_000_000_000


# ---------------------------------------------------------------------------
# Off-platform: every entry point is a quiet no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_everything_is_a_noop_off_platform(monkeypatch):
    _off_platform(monkeypatch)
    assert await notifications.ensure_channel() is False
    assert (
        await notifications.show_new_episode(
            anime_session="s", title="T", episode=1, poster_path=None
        )
        is False
    )
    assert await notifications.show_progress(notification_id=1, title="t") is False
    assert await notifications.request_permissions() is False
    notifications.on_tap(lambda payload: None)  # must not raise


# ---------------------------------------------------------------------------
# Download rows: their own id band, their own completion wording
# ---------------------------------------------------------------------------


def test_download_notification_id_band():
    import core.notifications as n

    ep_id = n.download_id("anikato:naruto-eybxz|1")
    alert_id = n.stable_id("anikato:naruto-eybxz")
    assert ep_id != alert_id
    assert ep_id >= 1_000_000_000 > alert_id
    assert n.download_id("a|1") != n.download_id("b|2")
    assert n.download_id("x") == n.download_id("x")


@pytest.mark.asyncio
async def test_a_finished_download_reuses_the_same_row_as_its_progress(fake):
    """The progress row and the completion row share an id, so the tray
    never holds two rows for one episode — the package updates in place."""
    await notifications.show_progress(
        notification_id=notifications.download_id("ep1"),
        title="Frieren",
        body="40%",
        progress=40,
        max_progress=100,
    )
    await notifications.show_new_episode(
        anime_session="anikato:frieren",
        title="Frieren",
        episode=1,
        download_complete=True,
        episode_session="ep1",
    )
    ids = [call["id"] for call in fake.shown]
    assert len(ids) == 2
    assert ids[0] == ids[1]  # one row, advanced
    (progress_call, done_call) = fake.shown
    assert progress_call["show_progress"] is True
    # the completion row carries no progress bar at all
    assert "show_progress" not in done_call
    assert "Download complete" in done_call["body"]
    assert done_call["payload"] == "animepahe://anime/anikato:frieren"


@pytest.mark.asyncio
async def test_a_series_alert_and_a_download_never_share_a_row(fake):
    await notifications.show_new_episode(
        anime_session="anikato:frieren", title="Frieren", episode=2
    )
    await notifications.show_new_episode(
        anime_session="anikato:frieren",
        title="Frieren",
        episode=1,
        download_complete=True,
        episode_session="ep1",
    )
    ids = [call["id"] for call in fake.shown]
    assert ids[0] != ids[1]
    assert "Tap to watch" in fake.shown[0]["body"]
