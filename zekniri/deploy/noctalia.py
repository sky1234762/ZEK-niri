"""Noctalia runtime-state defaults applied by the installer."""

from __future__ import annotations

import os
import shutil
import subprocess

from zekniri.core import get_env, log_msg

_FALSE_VALUES = {"false", "0", "no", "off"}
_TRUE_VALUES = {"true", "1", "yes", "on"}


def _is_bar_section(section: str) -> bool:
    """True for ``[bar.name]`` but not nested ``[bar.name.child]``."""
    if not (section.startswith("[bar.") and section.endswith("]")):
        return False
    name = section[len("[bar.") : -1]
    return bool(name) and "." not in name and "[" not in name and "]" not in name


def _set_bar_sections(
    lines: list[str], enabled: bool, only_section: str | None = None
) -> tuple[list[str], bool]:
    """Force ``[bar.*]`` ``enabled`` keys, optionally only one section."""
    out: list[str] = []
    section = ""
    has_enabled = False
    changed = False
    target = "true" if enabled else "false"

    def close_section() -> None:
        nonlocal changed
        if (
            _is_bar_section(section)
            and (only_section is None or section == only_section)
            and not has_enabled
        ):
            out.append(f"    enabled = {target}\n")
            changed = True

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            close_section()
            section = stripped
            has_enabled = False
            out.append(line)
            continue
        if _is_bar_section(section) and (only_section is None or section == only_section):
            key, sep, value = line.partition("=")
            if sep and key.strip() == "enabled":
                has_enabled = True
                indent = line[: len(line) - len(line.lstrip())]
                normalized = value.strip().lower()
                if enabled:
                    if normalized in _TRUE_VALUES:
                        out.append(line)
                    else:
                        out.append(f"{indent}enabled = true\n")
                        changed = True
                elif normalized in _FALSE_VALUES:
                    out.append(line)
                else:
                    out.append(f"{indent}enabled = false\n")
                    changed = True
                continue
        out.append(line)
    close_section()
    return out, changed


def _any_bar_enabled(lines: list[str]) -> bool:
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            continue
        if _is_bar_section(section):
            key, sep, value = line.partition("=")
            if sep and key.strip() == "enabled" and value.strip().lower() in _TRUE_VALUES:
                return True
    return False


def _can_contact_noctalia() -> bool:
    if os.environ.get("ZEKNIRI_SANDBOX"):
        return False
    env = get_env()
    return env.run_mode == "system" or (env.repo_dir / "install.sh").is_file()


def _apply_native_bar_state(
    enabled: bool, only_section: str | None = None, skip_if_any_enabled: bool = False
) -> bool:
    env = get_env()
    state_file = env.state_home / "noctalia" / "settings.toml"
    try:
        lines = state_file.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return False

    if enabled and skip_if_any_enabled and _any_bar_enabled(lines):
        return False

    updated, changed = _set_bar_sections(lines, enabled, only_section=only_section)
    if not changed:
        return False

    try:
        state_file.write_text("".join(updated), encoding="utf-8")
    except OSError as exc:
        log_msg("ERROR", f"Cannot update Noctalia native bar state: {exc}")
        return False

    log_msg("INFO", f"{'Enabled' if enabled else 'Disabled'} Noctalia native bar(s) in settings.toml")

    # Apply immediately when Noctalia is running. Skip test/temp trees so unit
    # tests never poke the real session.
    if _can_contact_noctalia() and shutil.which("noctalia"):
        try:
            subprocess.run(
                ["noctalia", "msg", "config-reload"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return True


def disable_native_bar() -> bool:
    """Force Noctalia's native bar sections off in the runtime settings.

    This is only called after Waybar is confirmed available. ``settings.toml``
    is a no-clobber state file, so the repo seed itself keeps the native bar
    enabled for users who install Noctalia without Waybar.
    """
    return _apply_native_bar_state(False)


def enable_native_bar() -> bool:
    """Turn Noctalia's main native bar back on when Waybar is not being used.

    Only the main ``[bar.default]`` section is enabled, so a Noctalia-only
    install does not accidentally show both author bar presets. If any bar is
    already enabled, leave the user's choice alone.
    """
    return _apply_native_bar_state(
        True, only_section="[bar.default]", skip_if_any_enabled=True
    )
