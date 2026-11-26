"""Wallpaper pack deployment.

The repo ships ``assets/wallpapers/``. It is synced (no-clobber) into
``<Pictures>/wallpaper`` — e.g. ``~/图片/wallpaper`` — so the wallpapers live
where desktop tools expect them, not under a dot directory. A file already
present is left alone, so the user's own wallpapers survive updates.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from zekniri.config import get_config
from zekniri.core import get_env, get_pics_dir, log_msg

_WALLPAPER_SRC = "wallpapers"
_WALLPAPER_DIR = "wallpaper"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}


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


def _toml_string(value: str) -> str:
    """Render a TOML basic string; JSON escaping is compatible with TOML."""
    return json.dumps(str(value), ensure_ascii=False)


def _line_value(line: str) -> str:
    raw = line.partition("=")[2].strip()
    if raw.startswith('"'):
        end = raw.find('"', 1)
        if end > 0:
            return raw[1:end]
    if raw.startswith("'"):
        end = raw.find("'", 1)
        if end > 0:
            return raw[1:end]
    return raw.split("#", 1)[0].strip()


def _first_wallpaper(directory: Path) -> Optional[Path]:
    """Pick a deterministic image from the deployed pack."""
    try:
        files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )
    except OSError:
        return None
    for path in files:
        if path.suffix.lower() in _IMAGE_SUFFIXES:
            return path
    return None


def _is_wallpaper_path_section(section: str) -> bool:
    return section in ("[wallpaper.default]", "[wallpaper.last]") or section.startswith(
        "[wallpaper.monitors."
    )


def _should_replace_directory(current: str, destination: Path) -> bool:
    """Whether ``[wallpaper] directory`` should be pointed at the deployed pack.

    Preserve an existing custom folder. Repair the common stale cases:
      * empty value
      * Pictures root (``~/Pictures`` / localised ``~/图片``)
      * a path from another machine (outside this HOME and missing)
    """
    if not current:
        return True
    env = get_env()
    try:
        current_path = Path(current).expanduser()
    except (OSError, RuntimeError):
        return True
    if current_path == destination:
        return False
    if current_path == get_pics_dir() or current_path == env.home / "Pictures":
        return True
    if not current_path.is_relative_to(env.home) and not current_path.exists():
        return True
    return False


def _can_contact_noctalia() -> bool:
    """Avoid touching the real session from tests/sandbox/custom trees."""
    if os.environ.get("ZEKNIRI_SANDBOX"):
        return False
    env = get_env()
    return env.run_mode == "system" or (env.repo_dir / "install.sh").is_file()


def _reload_noctalia() -> None:
    if not _can_contact_noctalia() or shutil.which("noctalia") is None:
        return
    try:
        subprocess.run(
            ["noctalia", "msg", "config-reload"],
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _apply_noctalia_wallpaper(path: Path) -> None:
    if not _can_contact_noctalia() or shutil.which("noctalia") is None:
        return
    try:
        subprocess.run(
            ["noctalia", "msg", "wallpaper-set", str(path)],
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def sync_noctalia_wallpaper_dir(destination: Path) -> Tuple[bool, Optional[Path]]:
    """Point Noctalia at the deployed pack and repair stale wallpaper paths.

    Returns ``(changed, selected_wallpaper)``. ``selected_wallpaper`` is set only
    when an empty/missing default or last path was replaced with a shipped image,
    so the caller can apply it to a running Noctalia without overriding a user's
    still-valid custom wallpaper. Monitor paths are repaired in the state file
    but do not by themselves change the current wallpaper.

    A seed state file from another machine used to carry absolute
    ``/home/<author>/...`` paths. Those are repaired here instead of being
    treated as a user-custom folder.
    """
    env = get_env()
    state_file = env.state_home / "noctalia" / "settings.toml"
    try:
        lines = state_file.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return False, None

    destination = Path(destination).expanduser()
    chosen = _first_wallpaper(destination)

    section = ""
    wallpaper_header = -1
    directory_line = -1
    path_lines: list[tuple[int, str]] = []
    section_headers: dict[str, int] = {}
    section_path_count: dict[str, int] = {}

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            if section == "[wallpaper]":
                wallpaper_header = index
            if _is_wallpaper_path_section(section):
                section_headers[section] = index
                section_path_count.setdefault(section, 0)
            continue
        if section == "[wallpaper]":
            key, sep, _value = line.partition("=")
            if sep and key.strip() == "directory":
                directory_line = index
        elif _is_wallpaper_path_section(section):
            key, sep, _value = line.partition("=")
            if sep and key.strip() == "path":
                path_lines.append((index, section))
                section_path_count[section] = section_path_count.get(section, 0) + 1

    # No [wallpaper] table at all: append a complete, portable one.
    if wallpaper_header < 0:
        selected: Optional[Path] = None
        block = [
            "[wallpaper]\n",
            f"directory = {_toml_string(str(destination))}\n",
            "transition_on_startup = true\n",
        ]
        if chosen is not None:
            block.extend(
                [
                    "\n    [wallpaper.default]\n",
                    f"    path = {_toml_string(str(chosen))}\n",
                    "\n    [wallpaper.last]\n",
                    f"    path = {_toml_string(str(chosen))}\n",
                ]
            )
            selected = chosen
        prefix = "" if not lines or lines[-1].endswith("\n") else "\n"
        try:
            state_file.write_text("".join(lines) + prefix + "".join(block), encoding="utf-8")
        except OSError as exc:
            log_msg("ERROR", f"Cannot update Noctalia wallpaper settings: {exc}")
            return False, None
        log_msg("INFO", f"Created Noctalia wallpaper settings -> {destination}")
        return True, selected

    updates: dict[int, str] = {}
    inserts: dict[int, list[str]] = {}
    append: list[str] = []
    changed = False
    selected: Optional[Path] = None

    # [wallpaper] directory
    if directory_line >= 0:
        current = _line_value(lines[directory_line])
        if _should_replace_directory(current, destination):
            indent = lines[directory_line][: len(lines[directory_line]) - len(lines[directory_line].lstrip())]
            updates[directory_line] = f"{indent}directory = {_toml_string(str(destination))}\n"
            changed = True
    else:
        inserts[wallpaper_header] = [f"directory = {_toml_string(str(destination))}\n"]
        changed = True

    # Existing default/last/monitor path lines: keep valid custom files, repair
    # empty or missing (including seed paths from another HOME).
    for index, section in path_lines:
        current = _line_value(lines[index])
        try:
            path = Path(current).expanduser() if current else None
        except (OSError, ValueError):
            path = None
        if path is None or not path.is_file():
            if chosen is not None:
                indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
                updates[index] = f"{indent}path = {_toml_string(str(chosen))}\n"
                if section in ("[wallpaper.default]", "[wallpaper.last]"):
                    selected = chosen
                changed = True

    # Ensure default/last exist and have a path.
    for table in ("[wallpaper.default]", "[wallpaper.last]"):
        if table not in section_headers:
            if chosen is not None:
                append.extend(
                    [
                        f"\n{table}\n",
                        f"    path = {_toml_string(str(chosen))}\n",
                    ]
                )
                selected = chosen
                changed = True
        elif section_path_count.get(table, 0) == 0 and chosen is not None:
            inserts.setdefault(section_headers[table], []).append(
                f"    path = {_toml_string(str(chosen))}\n"
            )
            selected = chosen
            changed = True

    if not changed:
        return False, None

    result: list[str] = []
    for index, line in enumerate(lines):
        result.append(updates.get(index, line))
        result.extend(inserts.get(index, []))
    result.extend(append)

    try:
        state_file.write_text("".join(result), encoding="utf-8")
    except OSError as exc:
        log_msg("ERROR", f"Cannot update Noctalia wallpaper settings: {exc}")
        return False, None

    log_msg("INFO", f"Updated Noctalia wallpaper settings -> {destination}")
    return True, selected


def deploy_assets() -> AssetDeployResult:
    """No-clobber sync of ``assets/wallpapers/`` into every configured dir."""
    src_root = wallpaper_source()
    dests = wallpaper_destinations()
    result = AssetDeployResult(destination=", ".join(str(d) for d in dests))
    if not assets_present():
        log_msg("INFO", "No wallpapers shipped; skipping")
        return result

    for dest_root in dests:
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log_msg("ERROR", f"Cannot create wallpaper directory {dest_root}: {exc}")
            continue
        for src in src_root.rglob("*"):
            if src.is_dir() or src.name.startswith("."):
                continue
            rel = src.relative_to(src_root)
            target = dest_root / rel
            if target.exists():
                result.skipped += 1
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            except OSError as exc:
                log_msg("ERROR", f"Cannot copy wallpaper {target}: {exc}")
                continue
            result.copied += 1

    changed, selected = sync_noctalia_wallpaper_dir(dests[0])
    if changed:
        _reload_noctalia()
    if selected is not None:
        _apply_noctalia_wallpaper(selected)

    log_msg("INFO", f"Wallpapers deployed: {result.copied} copied, {result.skipped} kept")
    return result
