"""Per-wallpaper palette switching for noctalia.

The ``wallpaper_palette`` mapping in ``ZEK-niri.conf`` pairs each wallpaper with
a palette JSON. This module reads noctalia's current wallpaper, resolves the
mapped palette, and applies it with ``noctalia msg color-scheme-set custom NAME``.

Noctalia has no wallpaper-change hook, so the switch is driven by the
``ZEK-niri palette`` command (manual or bound in a keybind / waybar module).
"""

import shutil
import tomllib
from pathlib import Path
from typing import Optional

from zekniri.config import get_config
from zekniri.constants import Colors
from zekniri.core import get_env, log_msg, timed_run
from zekniri.i18n import msg


def _noctalia_settings() -> list[Path]:
    env = get_env()
    return [
        env.state_home / "noctalia" / "settings.toml",
        env.config_dir / "noctalia" / "settings.toml",
    ]


def current_wallpaper() -> Optional[Path]:
    """Noctalia's current wallpaper, from ``[wallpaper.last|default|monitors.*]``."""
    for path in _noctalia_settings():
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        section = data.get("wallpaper")
        if not isinstance(section, dict):
            continue
        for key in ("last", "default"):
            entry = section.get(key)
            if isinstance(entry, dict) and entry.get("path"):
                return Path(entry["path"])
        monitors = section.get("monitors")
        if isinstance(monitors, dict):
            for entry in monitors.values():
                if isinstance(entry, dict) and entry.get("path"):
                    return Path(entry["path"])
    return None


def ensure_palette_installed(palette: Path) -> Path:
    """Copy a mapped palette into noctalia's palettes dir if it lives elsewhere."""
    env = get_env()
    dest_dir = env.config_dir / "noctalia" / "palettes"
    if palette.parent == dest_dir or not palette.is_file():
        return palette
    dest = dest_dir / palette.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(palette, dest)
        log_msg("INFO", f"Installed palette {dest}")
    return dest


def apply_palette(wallpaper: Optional[str] = None) -> bool:
    """Apply the palette mapped to ``wallpaper`` (or noctalia's current one)."""
    if shutil.which("noctalia") is None:
        print(msg("palette_no_noctalia"))
        return False

    target = Path(wallpaper) if wallpaper else current_wallpaper()
    if target is None:
        print(msg("palette_no_wallpaper"))
        return False

    palette = get_config().palette_for(target)
    if palette is None:
        print(msg("palette_unmapped", target.name))
        return False

    palette = ensure_palette_installed(palette)
    name = palette.stem
    proc = timed_run(["noctalia", "msg", "color-scheme-set", "custom", name], timeout=10)
    if proc is None or proc.returncode != 0:
        print(msg("palette_apply_failed", name))
        return False

    print(msg("palette_applied", target.name, name))
    log_msg("INFO", f"Applied palette {name} for {target}")
    return True


def list_mappings() -> None:
    """Print the configured wallpaper → palette mapping."""
    pairs = get_config().wallpaper_palettes
    print(f"{Colors.BOLD_WHITE}{msg('palette_list_title')}{Colors.RESET}\n")
    if not pairs:
        print(msg("palette_list_empty"))
        return
    for wallpaper, palette in pairs:
        mark = Colors.GREEN + "✓" + Colors.RESET if wallpaper.is_file() else Colors.YELLOW + "?" + Colors.RESET
        print(f"  [{mark}] {wallpaper}  ->  {palette.stem}")
