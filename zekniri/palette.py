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

from zekniri.config import CONF_NAME, default_preset_palette, get_config, reload_config, user_conf_path
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


def apply_palette(wallpaper: Optional[str] = None, wait: float = 0.0, force: bool = False) -> bool:
    """Apply the palette mapped to ``wallpaper`` (or noctalia's current one).

    An unmapped wallpaper falls back to a bare ``preset_palette`` default when
    one is configured; otherwise the current palette is left untouched (there is
    no implicit "first mapping" fallback).

    Only applies while waybar is in preset mode (the stable
    ``colors-active.css`` entry does not import noctalia's auto-generated
    colours), keeping preset and Noctalia-auto modes independent; pass
    ``force`` to override.

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
        palette = cfg.default_palettes[0] if cfg.default_palettes else default_preset_palette()
        print(msg("palette_default_used", target.name, palette.stem), flush=True)

    palette = ensure_palette_installed(palette)
    name = palette.stem
    proc = timed_run(["noctalia", "msg", "color-scheme-set", "custom", name], timeout=10)
    if proc is None or proc.returncode != 0:
        print(msg("palette_apply_failed", name), flush=True)
        return False

    print(msg("palette_applied", target.name, name), flush=True)
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


def _preset_mode_active() -> bool:
    """False when waybar currently imports noctalia's auto-generated colours.

    Reads the stable ``colors-active.css`` entry (``style.css`` imports it), so
    the check survives a ``style.css`` redeploy.
    """
    active = get_env().config_dir / "waybar" / "colors-active.css"
    try:
        return "colors-noctalia.css" not in active.read_text(encoding="utf-8")
    except OSError:
        return True


_WATCH_LOCK = None

_FONT_SIZE_MARKER = "ZEKniri: base font size"


def _reload_waybar() -> None:
    script = get_env().config_dir / "waybar" / "scripts" / "reload-waybar.sh"
    if script.is_file():
        subprocess.run(
            ["bash", str(script)], check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["pkill", "-SIGUSR2", "waybar"], check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def apply_font_size(size: str) -> bool:
    """Rewrite the marked base ``font-size`` in Waybar's live style.css."""
    style = get_env().config_dir / "waybar" / "style.css"
    try:
        content = style.read_text(encoding="utf-8")
    except OSError:
        return False

    pattern = re.compile(
        r"(?m)^(\s*font-size:\s*)[^;]+(;.*" + re.escape(_FONT_SIZE_MARKER) + r".*)$"
    )
    updated, count = pattern.subn(rf"\g<1>{size}\g<2>", content, count=1)
    if count == 0:
        # Older live styles have the base rule without our marker.
        pattern = re.compile(r"(?m)^(\s*font-size:\s*)[^;]+(;.*)$")
        updated, count = pattern.subn(
            rf"\g<1>{size}; /* {_FONT_SIZE_MARKER} */", content, count=1
        )
    if count == 0 or updated == content:
        return False

    tmp = style.with_name(style.name + ".tmp")
    try:
        tmp.write_text(updated, encoding="utf-8")
        tmp.replace(style)
    except OSError:
        return False
    log_msg("INFO", f"Waybar base font size -> {size}")
    _reload_waybar()
    return True


def _config_mtime() -> float:
    env = get_env()
    mtimes = []
    for path in (env.repo_dir / CONF_NAME, user_conf_path()):
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def watch(interval: float = 1.0) -> int:
    """Follow noctalia's wallpaper and hot-reload the Waybar font size.

    Polls ``[wallpaper.last].path``; on a new wallpaper that has a mapping, the
    palette is applied once. Also polls ``ZEK-niri.conf`` and rewrites the
    marked base Waybar ``font-size`` when it changes. Runs in the foreground
    until interrupted. Only one watcher may run at a time (non-blocking lock);
    it does not take the CLI's single-instance lock.
    """
    global _WATCH_LOCK
    lock_path = get_env().state_dir / "watch.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        print(msg("watch_already_running"), flush=True)
        return 0
    _WATCH_LOCK = lock

    print(msg("watch_started", interval), flush=True)
    last = None
    reload_config()
    last_conf_mtime = _config_mtime()
    last_font_size = get_config().font_size
    apply_font_size(last_font_size)  # reconcile a style deployed by an older engine
    try:
        while True:
            conf_mtime = _config_mtime()
            if conf_mtime != last_conf_mtime:
                last_conf_mtime = conf_mtime
                reload_config()
                font_size = get_config().font_size
                if font_size != last_font_size:
                    last_font_size = font_size
                    apply_font_size(font_size)
            path = current_wallpaper()
            if path is not None and path != last:
                last = path
                if _preset_mode_active():
                    apply_palette(str(path))
            time.sleep(interval)
    except KeyboardInterrupt:
        print(msg("watch_stopped"), flush=True)
    finally:
        _WATCH_LOCK = None
        lock.close()
    return 0


_SERVICE = "zekniri-watch.service"


def _service_path() -> Path:
    return get_env().config_dir / "systemd" / "user" / _SERVICE


def install_watcher() -> bool:
    """Install + (re)start a systemd user service running ``ZEK-niri watch``."""
    if shutil.which("systemctl") is None:
        print(msg("watch_no_systemd"), flush=True)
        return False
    exe = get_env().home / ".local" / "bin" / CLI_CMD
    unit = (
        "[Unit]\n"
        "Description=ZEKniri wallpaper palette & Waybar font watcher\n"
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
    subprocess.run(["systemctl", "--user", "enable", _SERVICE], check=False)
    subprocess.run(["systemctl", "--user", "restart", _SERVICE], check=False)
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
