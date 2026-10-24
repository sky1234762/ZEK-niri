"""Best-effort fullscreen detection for the focused Niri window."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def _find_container(payload: Any, key: str) -> dict | None:
    if isinstance(payload, dict):
        if key in payload:
            return payload
        for value in payload.values():
            found = _find_container(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_container(value, key)
            if found is not None:
                return found
    return None


def _window_is_fullscreen(window: dict, output: dict) -> bool:
    for key in ("is_fullscreen", "is-fullscreen", "fullscreen"):
        state = window.get(key)
        if isinstance(state, bool):
            return state

    logical = output.get("logical")
    if not isinstance(logical, dict):
        return False
    width, height = logical.get("width"), logical.get("height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return False

    layout = window.get("layout")
    if not isinstance(layout, dict):
        return False
    for key in ("tile_size", "window_size"):
        size = layout.get(key)
        if isinstance(size, (list, tuple)) and len(size) == 2:
            if all(isinstance(value, (int, float)) for value in size):
                if abs(size[0] - width) <= 2 and abs(size[1] - height) <= 2:
                    return True
    return False


def focused_window_is_fullscreen() -> bool:
    """Return True for explicit fullscreen state or exact output-sized geometry.

    IPC errors fail open so a missing socket or compositor does not disable the
    launcher. Niri has shipped versions without an explicit fullscreen field.
    """
    try:
        window_result = subprocess.run(
            ["niri", "msg", "--json", "focused-window"],
            capture_output=True,
            text=True,
            timeout=0.35,
            check=False,
        )
        if window_result.returncode != 0:
            return False
        window_payload = json.loads(window_result.stdout)
        window = _find_container(window_payload, "layout")
        if window is None:
            return False
        for key in ("is_fullscreen", "is-fullscreen", "fullscreen"):
            if isinstance(window.get(key), bool):
                return window[key]

        output_result = subprocess.run(
            ["niri", "msg", "--json", "focused-output"],
            capture_output=True,
            text=True,
            timeout=0.35,
            check=False,
        )
        if output_result.returncode != 0:
            return False
        output = _find_container(json.loads(output_result.stdout), "logical")
        return output is not None and _window_is_fullscreen(window, output)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False

def _bool_field(payload: Any, keys: tuple[str, ...]) -> bool | None:
    """Find an explicit pointer/window state in a Niri JSON payload."""
    found_false = False
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value is True:
                return True
            if value is False:
                found_false = True
        for value in payload.values():
            found = _bool_field(value, keys)
            if found is True:
                return True
            found_false = found_false or found is False
    elif isinstance(payload, list):
        for value in payload:
            found = _bool_field(value, keys)
            if found is True:
                return True
            found_false = found_false or found is False
    return False if found_false else None


def pointer_over_window() -> bool:
    """Return whether Niri reports the pointer over a client window.

    Niri versions that expose the pointer hit-test include one of the
    ``is_under_cursor``/``under_cursor`` fields in the focused-window or
    windows JSON. Older versions do not expose this state; in that case the
    check fails open so the launcher remains usable.
    """
    keys = (
        "is_under_cursor",
        "under_cursor",
        "is_under_pointer",
        "under_pointer",
        "pointer_over",
        "is_pointer_over",
    )
    try:
        result = subprocess.run(
            ["niri", "msg", "--json", "windows"],
            capture_output=True,
            text=True,
            timeout=0.35,
            check=False,
        )
        if result.returncode != 0:
            return False
        state = _bool_field(json.loads(result.stdout), keys)
        if state is not None:
            return state

        # Some Niri releases only expose the focused window command.
        result = subprocess.run(
            ["niri", "msg", "--json", "focused-window"],
            capture_output=True,
            text=True,
            timeout=0.35,
            check=False,
        )
        if result.returncode != 0:
            return False
        state = _bool_field(json.loads(result.stdout), keys)
        return bool(state) if state is not None else False
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False
