"""Detect Niri output modes and optionally write them to ``config.kdl``."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from zekniri.core import get_env
from zekniri.i18n import msg
from zekniri.tui import Menu, MenuItem

_OUTPUT_RE = re.compile(r'^(?P<indent>\s*)output\s+"(?P<name>[^"]+)"\s*\{\s*$')
_MODE_RE = re.compile(r'^\s*mode\s+"[^"]*".*$')


def _read_outputs() -> dict:
    try:
        result = subprocess.run(
            ["niri", "msg", "--json", "outputs"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _mode_label(width: int, height: int, rate: float) -> str:
    return f"{width}x{height}@{rate / 1000:.2f}"


def detect_output_choices() -> list[tuple[str, list[str], int]]:
    """Return ``(output, sorted_modes, current_index)`` for connected outputs."""
    choices: list[tuple[str, list[str], int]] = []
    for key, entry in _read_outputs().items():
        if not isinstance(entry, dict):
            continue
        raw_modes = entry.get("modes") or []
        current_index = entry.get("current_mode")
        parsed: list[tuple[int, float, str]] = []
        current_label = None
        for index, mode in enumerate(raw_modes):
            if not isinstance(mode, dict):
                continue
            width = mode.get("width")
            height = mode.get("height")
            rate = mode.get("refresh_rate")
            if not isinstance(width, int) or not isinstance(height, int):
                continue
            if not isinstance(rate, (int, float)):
                continue
            label = _mode_label(width, height, float(rate))
            parsed.append((width * height, float(rate), label))
            if index == current_index:
                current_label = label
        if not parsed:
            continue

        parsed.sort(key=lambda item: (item[0], item[1]), reverse=True)
        modes: list[str] = []
        for _, _, label in parsed:
            if label not in modes:
                modes.append(label)
        current = modes.index(current_label) if current_label in modes else 0
        name = str(entry.get("name") or key)
        choices.append((name, modes, current))
    return choices


def detect_output_modes() -> list[tuple[str, str]]:
    """Return the current mode for every connected output."""
    return [(name, modes[current]) for name, modes, current in detect_output_choices()]


def _format_output_block(name: str, mode: str) -> str:
    return f'output "{name}" {{\n    mode "{mode}"\n}}\n'


def write_output_modes(path: Path, outputs: list[tuple[str, str]]) -> bool:
    """Update/insert ``output "<name>" { mode "..." }`` blocks in ``path``."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False

    lines = content.splitlines(keepends=True)
    wanted = dict(outputs)
    found: set[str] = set()
    out: list[str] = []
    index = 0
    while index < len(lines):
        match = _OUTPUT_RE.match(lines[index].rstrip())
        if not match:
            out.append(lines[index])
            index += 1
            continue

        name = match.group("name")
        indent = match.group("indent")
        block = [lines[index]]
        depth = lines[index].count("{") - lines[index].count("}")
        index += 1
        while index < len(lines) and depth > 0:
            block.append(lines[index])
            depth += lines[index].count("{") - lines[index].count("}")
            index += 1

        if name in wanted:
            found.add(name)
            for line_index in range(1, len(block)):
                if _MODE_RE.match(block[line_index].rstrip()):
                    block[line_index] = f'{indent}    mode "{wanted[name]}"\n'
                    break
            else:
                block.insert(1, f'{indent}    mode "{wanted[name]}"\n')
        out.extend(block)

    for name, mode in outputs:
        if name in found:
            continue
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        if out:
            out.append("\n")
        out.append(_format_output_block(name, mode))

    updated = "".join(out)
    if updated == content:
        return False

    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(updated, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


def choose_output_modes() -> list[tuple[str, str]] | None:
    """Show a TUI selector per output. Returns selected ``(name, mode)`` pairs."""
    choices = detect_output_choices()
    if not choices:
        print(msg("niri_output_none"), flush=True)
        return None

    selected: list[tuple[str, str]] = []
    for name, modes, current in choices:
        items: list[MenuItem] = []
        for index, mode in enumerate(modes):
            label = f"{mode}  {msg('niri_output_current')}" if index == current else mode
            items.append(MenuItem(label=label, group_header=name))
        items.append(MenuItem(label=msg("niri_output_keep"), group_header=name, style="subtle"))

        choice = Menu(
            "niri_output_choose_title",
            items,
            hint_key="submenu_hint",
            compact=True,
            initial_focus=current,
        ).run()
        if choice is None:
            print(msg("niri_output_skipped"), flush=True)
            return None
        if choice < len(modes):
            selected.append((name, modes[choice]))
    return selected


def choose_and_write_output_modes() -> bool:
    """Run the TUI selector and write the chosen modes to ``config.kdl``."""
    selected = choose_output_modes()
    if selected is None:
        return False
    if not selected:
        print(msg("niri_output_skipped"), flush=True)
        return False

    path = get_env().config_dir / "niri" / "config.kdl"
    if not path.is_file():
        print(msg("niri_output_missing", str(path)), flush=True)
        return False
    if write_output_modes(path, selected):
        print(msg("niri_output_written", str(path)), flush=True)
    else:
        print(msg("niri_output_unchanged", str(path)), flush=True)
    return True
