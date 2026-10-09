"""Per-wallpaper palette switching for noctalia.

The ``wallpaper_palette`` mapping in ``ZEK-niri.conf`` pairs each wallpaper with
a palette JSON. This module reads noctalia's current wallpaper, resolves the
mapped palette, and applies it with ``noctalia msg color-scheme-set custom NAME``.

Noctalia has no wallpaper-change hook, so the switch is driven by the
``ZEK-niri palette`` command (manual or bound in a keybind / waybar module).
"""

import fcntl
import re
import shutil
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Optional

from zekniri.config import get_config, reload_config
from zekniri.constants import CLI_CMD, Colors
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


def _waybar_import_target(css: Path) -> str:
    """CSS path for waybar's ``@import``; external files are copied in."""
    waybar_dir = get_env().config_dir / "waybar"
    try:
        return css.relative_to(waybar_dir).as_posix()
    except ValueError:
        waybar_dir.mkdir(parents=True, exist_ok=True)
        dest = waybar_dir / "colors-wallpaper.css"
        shutil.copy2(css, dest)
        return dest.name


def _reload_waybar() -> None:
    script = get_env().config_dir / "waybar" / "scripts" / "reload-waybar.sh"
    if script.is_file():
        subprocess.run(
            ["bash", str(script)], check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(["pkill", "-SIGUSR2", "waybar"], check=False)


def apply_waybar_colors(wallpaper: Path) -> bool:
    """Point waybar's ``style.css`` at ``wallpaper``'s mapped CSS and reload.

    No-op when the wallpaper has no ``waybar_colors`` mapping or the file is
    missing, so the preset/auto mode chosen by ``toggle-colors.sh`` is preserved.
    """
    css = get_config().waybar_colors_for(wallpaper)
    style = get_env().config_dir / "waybar" / "style.css"
    if css is None or not css.is_file() or not style.is_file():
        return False
    target = _waybar_import_target(css)
    try:
        text = style.read_text(encoding="utf-8")
    except OSError:
        return False
    new = re.sub(r'@import\s+"[^"]*\.css";', f'@import "{target}";', text, count=1)
    if new == text:
        return False
    try:
        style.write_text(new, encoding="utf-8")
    except OSError:
        return False
    _reload_waybar()
    log_msg("INFO", f"Waybar colours -> {target} for {wallpaper}")
    return True


def apply_palette(wallpaper: Optional[str] = None, wait: float = 0.0, force: bool = False) -> bool:
    """Apply the palette mapped to ``wallpaper`` (or noctalia's current one).

    An unmapped wallpaper falls back to a bare ``preset_palette`` default when
    one is configured; otherwise the current palette is left untouched (there is
    no implicit "first mapping" fallback).

    Only applies while waybar is in preset mode (``style.css`` does not import
    noctalia's auto-generated colours), keeping preset and Noctalia-auto modes
    independent; pass ``force`` to override.

    When ``wallpaper`` is not given and ``wait > 0``, noctalia's ``wallpaper-*``
    IPC is asynchronous: poll briefly for ``[wallpaper.last].path`` to change
    before applying, so a waybar click applies the *new* wallpaper's palette.
    """
    if not force and not _preset_mode_active():
        print(msg("palette_auto_mode_skip"), flush=True)
        return False
    if shutil.which("noctalia") is None:
        print(msg("palette_no_noctalia"), flush=True)
        return False

    target = Path(wallpaper) if wallpaper else current_wallpaper()
    if wallpaper is None and wait > 0 and target is not None:
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(0.2)
            new = current_wallpaper()
            if new is not None and new != target:
                target = new
                break
    if target is None:
        print(msg("palette_no_wallpaper"), flush=True)
        return False

    cfg = get_config()
    palette = cfg.palette_for(target)
    if palette is None:
        if not cfg.default_palettes:
            print(msg("palette_unmapped", target.name), flush=True)
            return False
        palette = cfg.default_palettes[0]

    palette = ensure_palette_installed(palette)
    name = palette.stem
    proc = timed_run(["noctalia", "msg", "color-scheme-set", "custom", name], timeout=10)
    if proc is None or proc.returncode != 0:
        print(msg("palette_apply_failed", name), flush=True)
        return False

    print(msg("palette_applied", target.name, name), flush=True)
    log_msg("INFO", f"Applied palette {name} for {target}")
    apply_waybar_colors(target)
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


def _preset_mode_active() -> bool:
    """False when waybar currently imports noctalia's auto-generated colours.

    Guards the watcher so it does not fight the "Noctalia auto" mode: the mode is
    read from waybar's ``style.css`` ``@import`` line. Missing file means "don't
    block".
    """
    style = get_env().config_dir / "waybar" / "style.css"
    try:
        return "colors-noctalia.css" not in style.read_text(encoding="utf-8")
    except OSError:
        return True


_WATCH_LOCK = None


def watch(interval: float = 1.0) -> int:
    """Follow noctalia's current wallpaper and apply its palette on change.

    Polls ``[wallpaper.last].path``; on a new wallpaper that has a mapping, the
    palette is applied once. Runs in the foreground until interrupted. Only one
    watcher may run at a time (non-blocking lock); it does not take the CLI's
    single-instance lock.
    """
    global _WATCH_LOCK
    lock_path = get_env().state_dir / "watch.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _WATCH_LOCK = open(lock_path, "w")
    try:
        fcntl.flock(_WATCH_LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(msg("watch_already_running"), flush=True)
        return 0

    print(msg("watch_started", interval), flush=True)
    last = None
    try:
        while True:
            path = current_wallpaper()
            if path is not None and path != last:
                last = path
                if _preset_mode_active():
                    reload_config()  # pick up ZEK-niri.conf edits without a restart
                    apply_palette(str(path))
            time.sleep(interval)
    except KeyboardInterrupt:
        print(msg("watch_stopped"), flush=True)
    return 0


_SERVICE = "zekniri-watch.service"


def _service_path() -> Path:
    return get_env().config_dir / "systemd" / "user" / _SERVICE


def install_watcher() -> bool:
    """Install + start a systemd user service running ``ZEK-niri watch``."""
    if shutil.which("systemctl") is None:
        print(msg("watch_no_systemd"), flush=True)
        return False
    exe = get_env().home / ".local" / "bin" / CLI_CMD
    unit = (
        "[Unit]\n"
        "Description=ZEKniri wallpaper palette watcher\n"
        "After=graphical-session.target\n"
        "PartOf=graphical-session.target\n\n"
        "[Service]\n"
        f"ExecStart={exe} watch\n"
        "Restart=on-failure\n"
        "RestartSec=3\n\n"
        "[Install]\n"
        "WantedBy=graphical-session.target\n"
    )
    path = _service_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", _SERVICE], check=False)
    print(msg("watch_installed", str(path)), flush=True)
    return True


def remove_watcher() -> bool:
    """Stop + remove the systemd user watcher service (if present)."""
    if shutil.which("systemctl") is not None:
        subprocess.run(["systemctl", "--user", "disable", "--now", _SERVICE], check=False)
    path = _service_path()
    existed = path.exists()
    path.unlink(missing_ok=True)
    if shutil.which("systemctl") is not None:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(msg("watch_removed") if existed else msg("watch_not_installed"), flush=True)
    return existed
