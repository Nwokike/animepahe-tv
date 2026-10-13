"""The downloads row: state word, inline bar, and the actions each state
allows (the YouTube shape).

The bar lives INSIDE the name row while a job runs, an unknown length is
indeterminate rather than a lie at 0%, and each state offers exactly the
actions that make sense for it.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-dlrow-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft  # noqa: E402

from screens.downloads_screen import _episode_row  # noqa: E402


class _Controller:
    """Records the actions the row's buttons would fire."""

    def __init__(self):
        self.fired: list[str] = []

    def pause_download(self, session):
        self.fired.append("pause")

    def resume_download(self, session):
        self.fired.append("resume")

    def retry_download(self, session):
        self.fired.append("retry")

    def cancel_download(self, session):
        self.fired.append("cancel")

    def delete_download(self, session):
        self.fired.append("delete")

    def play_downloaded(self, session):
        self.fired.append("play")


def _buttons(control) -> list:
    """Every IconButton in the tree (the row's actions)."""
    found: list = []
    stack = [control]
    while stack:
        current = stack.pop()
        if isinstance(current, ft.IconButton):
            found.append(current)
        for attr in ("controls", "content"):
            value = getattr(current, attr, None)
            if isinstance(value, list):
                stack.extend(value)
            elif value is not None:
                stack.append(value)
    return found


def _bar(control):
    """The inline ProgressBar, when the row renders one."""
    stack = [control]
    while stack:
        current = stack.pop()
        if isinstance(current, ft.ProgressBar):
            return current
        for attr in ("controls", "content"):
            value = getattr(current, attr, None)
            if isinstance(value, list):
                stack.extend(value)
            elif value is not None:
                stack.append(value)
    return None


def _texts(control) -> list[str]:
    """Every text in the tree — the state word lives here."""
    found: list[str] = []
    stack = [control]
    while stack:
        current = stack.pop()
        if isinstance(current, ft.Text):
            found.append(str(current.value))
        for attr in ("controls", "content"):
            value = getattr(current, attr, None)
            if isinstance(value, list):
                stack.extend(value)
            elif value is not None:
                stack.append(value)
    return found


def _row(progress=None, state="partial", **row):
    controller = _Controller()
    base = {"episode_num": 3, "state": state, "size_bytes": 5000}
    base.update(row)
    return controller, _episode_row(base, "ep3", controller, progress)


def test_a_running_job_shows_the_bar_inside_the_row_and_offers_pause():
    controller, row = _row({"state": "downloading", "done": 5, "total": 20, "percent": 25})
    bar = _bar(row)
    assert bar is not None
    assert bar.value == 0.25
    assert any("25%" in text for text in _texts(row))
    # pause + cancel, and nothing else
    tools = sorted(b.tooltip for b in _buttons(row))
    assert tools == ["Cancel", "Pause"]


def test_an_unknown_length_is_indeterminate_not_zero():
    controller, row = _row({"state": "downloading", "done": 3, "total": 0, "percent": None})
    bar = _bar(row)
    assert bar is not None
    assert bar.value is None  # indeterminate
    assert any("Downloading" in text for text in _texts(row))


def test_a_queued_job_waits_and_can_still_be_cancelled():
    controller, row = _row({"state": "queued", "done": 0, "total": 0})
    assert any("Waiting" in text for text in _texts(row))
    assert sorted(b.tooltip for b in _buttons(row)) == ["Cancel", "Pause"]


def test_a_paused_job_offers_resume_and_delete_never_pause():
    controller, row = _row({"state": "stopped", "bytes": 2048})
    assert any("Paused" in text for text in _texts(row))
    assert sorted(b.tooltip for b in _buttons(row)) == ["Delete", "Resume"]
    # the partial size is shown, not a percentage
    assert any("2.0KB" in text for text in _texts(row))


def test_a_failed_job_offers_retry_and_delete():
    controller, row = _row({"state": "failed"})
    assert any("Failed" in text for text in _texts(row))
    assert sorted(b.tooltip for b in _buttons(row)) == ["Delete", "Retry"]


def test_a_complete_job_offers_play_and_delete_and_no_bar():
    controller, row = _row(None, state="complete", size_bytes=293000000)
    assert _bar(row) is None
    assert sorted(b.tooltip for b in _buttons(row)) == ["Delete", "Play"]
    assert any("279" in text for text in _texts(row))  # 293000000 bytes


def test_the_buttons_fire_the_right_actions():
    controller, row = _row({"state": "stopped", "bytes": 10})
    for button in _buttons(row):
        button.on_click(None)
    assert controller.fired == ["delete", "resume"] or sorted(controller.fired) == [
        "delete",
        "resume",
    ]
