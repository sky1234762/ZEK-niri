"""Wallpaper pack deployment.

The repo ships ``assets/wallpapers/``. It is synced (no-clobber) into
``<Pictures>/wallpaper`` — e.g. ``~/图片/wallpaper`` — so the wallpapers live
where desktop tools expect them, not under a dot directory. A file already
present is left alone, so the user's own wallpapers survive updates.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from zekniri.config import get_config
from zekniri.core import get_env, get_pics_dir, log_msg

_WALLPAPER_SRC = "wallpapers"
_WALLPAPER_DIR = "wallpaper"


@dataclass
class AssetDeployResult:
    copied: int = 0
    skipped: int = 0
    destination: str = ""


def wallpaper_source() -> Path:
    return get_env().assets_src / _WALLPAPER_SRC


def wallpaper_destinations() -> tuple[Path, ...]:
    """Every configured wallpaper destination (auto ``<Pictures>/wallpaper`` if none)."""
    dirs = get_config().wallpaper_dirs
    if dirs:
        return dirs
    return (get_pics_dir() / _WALLPAPER_DIR,)


def wallpaper_destination() -> Path:
    """Primary wallpaper destination (first configured dir)."""
    return wallpaper_destinations()[0]


def assets_present() -> bool:
    """True when the repo ships wallpapers (hidden files ignored)."""
    src = wallpaper_source()
    return src.is_dir() and any(p for p in src.iterdir() if not p.name.startswith("."))


def deploy_assets() -> AssetDeployResult:
    """No-clobber sync of ``assets/wallpapers/`` into every configured dir."""
    src_root = wallpaper_source()
    dests = wallpaper_destinations()
    result = AssetDeployResult(destination=", ".join(str(d) for d in dests))
    if not assets_present():
        log_msg("INFO", "No wallpapers shipped; skipping")
        return result

    for dest_root in dests:
        dest_root.mkdir(parents=True, exist_ok=True)
        for src in src_root.rglob("*"):
            if src.is_dir() or src.name.startswith("."):
                continue
            rel = src.relative_to(src_root)
            target = dest_root / rel
            if target.exists():
                result.skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            result.copied += 1

    log_msg("INFO", f"Wallpapers deployed: {result.copied} copied, {result.skipped} kept")
    return result
