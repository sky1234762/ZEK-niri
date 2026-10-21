"""Configuration parsing for the standalone ZEKniri menu."""

from __future__ import annotations

import os
from pathlib import Path


def menu_config_path(home: Path | None = None, xdg_config_home: str | None = None) -> Path:
    home = home or Path.home()
    base = Path(xdg_config_home) if xdg_config_home else home / ".config"
    return base / "ZEKniri" / "ZEKniri-menu.conf"


def expand_config_path(raw: str, home: Path | None = None) -> Path:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if home is not None and value == "~":
        value = str(home)
    elif home is not None and value.startswith("~/"):
        value = str(home / value[2:])
    return Path(os.path.expandvars(os.path.expanduser(value)))


def read_menu_entries(path: Path, home: Path | None = None) -> tuple[list[tuple[int, str, Path]], Path | None]:
    """Return indexed appimage entries and the optional memo path."""
    apps: list[tuple[int, str, Path]] = []
    memo: Path | None = None
    app_index = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = (part.strip() for part in stripped.split("=", 1))
        if key == "appimage_path":
            app_index += 1
            if not value:
                continue
            app = expand_config_path(value, home)
            apps.append((app_index, app.name or str(app), app))
        elif key == "memo_path" and value and memo is None:
            memo = expand_config_path(value, home)
    return apps, memo
