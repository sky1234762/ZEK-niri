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
