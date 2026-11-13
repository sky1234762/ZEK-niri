"""Noctalia runtime-state defaults applied by the installer."""

from __future__ import annotations

import shutil
import subprocess

from zekniri.core import get_env, log_msg

_FALSE_VALUES = {"false", "0", "no", "off"}


def _disable_bar_sections(lines: list[str]) -> tuple[list[str], bool]:
    """Return ``lines`` with every ``[bar.*]`` section forced to ``enabled = false``."""
    out: list[str] = []
    section = ""
    has_enabled = False
    changed = False

    def close_section() -> None:
        nonlocal changed
        if section.startswith("[bar.") and not has_enabled:
            out.append("    enabled = false\n")
            changed = True

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            close_section()
            section = stripped
            has_enabled = False
            out.append(line)
            continue
        if section.startswith("[bar."):
            key, sep, value = line.partition("=")
            if sep and key.strip() == "enabled":
                has_enabled = True
                indent = line[: len(line) - len(line.lstrip())]
                if value.strip().lower() not in _FALSE_VALUES:
                    out.append(f"{indent}enabled = false\n")
                    changed = True
                else:
                    out.append(line)
                continue
        out.append(line)
    close_section()
    return out, changed


def disable_native_bar() -> bool:
    """Force Noctalia's native bar sections off in the runtime settings.

    ``settings.toml`` is a no-clobber state file, so the repo seed only helps
    fresh installs. This targeted merge flips only ``enabled`` under
    ``[bar.*]`` and leaves every other setting untouched.
    """
    env = get_env()
    state_file = env.state_home / "noctalia" / "settings.toml"
    try:
        lines = state_file.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return False

    updated, changed = _disable_bar_sections(lines)
    if not changed:
        return False

    state_file.write_text("".join(updated), encoding="utf-8")
    log_msg("INFO", "Disabled Noctalia native bar(s) in settings.toml")

    # Apply immediately when Noctalia is running. Skip test/temp trees so unit
    # tests never poke the real session.
    if (env.repo_dir / "install.sh").is_file() and shutil.which("noctalia"):
        subprocess.run(
            ["noctalia", "msg", "config-reload"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return True
