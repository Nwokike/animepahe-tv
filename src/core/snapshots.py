"""Snapshot files — what the player's screenshot button actually writes.

The old code called `take_screenshot()` and dropped the bytes on the floor
(its comment even claimed a save). One pure naming rule, one atomic write,
and a small rotation so a screenshot binge cannot grow forever: the player
passes the device Downloads directory when the platform offers one
(gallery-visible), else the app's data tier.
"""

import os
from datetime import datetime

from core.storage import app_data_dir

# Keep at most this many snapshots per directory; oldest first.
KEEP_SNAPSHOTS = 50

PREFIX = "animepahe-"


def snapshot_filename(when: datetime | None = None) -> str:
    """`animepahe-YYYYMMDD-HHMMSS-mmm.png` — sortable = chronological."""
    when = when or datetime.now()
    return f"{PREFIX}{when:%Y%m%d-%H%M%S}-{when.microsecond // 1000:03d}.png"


def save_snapshot(
    data: bytes,
    directory: str | None = None,
    *,
    when: datetime | None = None,
    keep: int = KEEP_SNAPSHOTS,
) -> str:
    """Write the PNG (atomically) and return its full path.

    `directory` defaults to the data tier's `screenshots/`. Rotation runs on
    the same directory and never fails the save.
    """
    target_dir = directory or app_data_dir("screenshots")
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, snapshot_filename(when))
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    _prune(target_dir, keep)
    return path


def _prune(directory: str, keep: int) -> None:
    """Keep the newest `keep` snapshot files; a file that resists deletion
    is skipped, never raised."""
    if keep <= 0:
        return
    try:
        names = sorted(
            n
            for n in os.listdir(directory)
            if n.startswith(PREFIX) and n.endswith(".png")
        )
    except OSError:
        return
    for name in names[:-keep]:
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            continue
