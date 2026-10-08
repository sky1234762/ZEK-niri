"""Runtime configuration for the engine itself: ``ZEK-niri.conf``.

A flat ``key = value`` file (``#`` full-line comments, blank lines ignored,
``~`` / ``$HOME`` expanded). The repo/install root is the **single source of
truth** — the engine and the deployed shell helpers both read it. A copy at
``~/.config/<PROJECT_NAME>/ZEK-niri.conf`` is seeded on install only as a
fallback for helpers that cannot locate the install tree; it is never layered
into the engine, so a stale copy cannot shadow the real file.

This tunes engine behaviour only. Per-app configuration still lives under
``configs/<app>/`` and is described by the manifest system.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from zekniri.constants import PROJECT_NAME
from zekniri.core import get_env

CONF_NAME = "ZEK-niri.conf"

_TRUE = {"1", "true", "yes", "on"}

# Recognized keys and shipped defaults. Empty string means "unset"; callers
# then fall back to a computed location (e.g. <Pictures>/wallpaper).
_DEFAULTS = {
    "ask_language_each_start": "false",
    "wallpaper_dir": "",
    "preset_palette": "",
    "log_path": "",
    "noctalia_scheme_source": "wallpaper",
    "noctalia_scheme_name": "soft",
    "wallpaper_palette": [],
}

# Repeatable keys: every line is appended instead of overwriting.
_LIST_KEYS = {"wallpaper_palette"}


@dataclass(frozen=True)
class Config:
    ask_language_each_start: bool
    wallpaper_dirs: tuple[Path, ...]
    preset_palettes: tuple[Path, ...]
    wallpaper_palettes: tuple[tuple[Path, Path], ...]
    log_path: Optional[Path]
    noctalia_scheme_source: str
    noctalia_scheme_name: str

    @property
    def wallpaper_dir(self) -> Optional[Path]:
        """Primary wallpaper dir (first entry); None = auto ``<Pictures>/wallpaper``."""
        return self.wallpaper_dirs[0] if self.wallpaper_dirs else None

    @property
    def preset_palette(self) -> Path:
        return self.preset_palettes[0]

    @property
    def preset_palette_name(self) -> str:
        """Noctalia palette name (file stem) for ``color-scheme-set custom``."""
        return self.preset_palette.stem

    @property
    def preset_palette_names(self) -> tuple[str, ...]:
        return tuple(p.stem for p in self.preset_palettes)

    def palette_for(self, wallpaper: Path) -> Optional[Path]:
        """Palette mapped to ``wallpaper`` (exact path first, then basename)."""
        target = Path(wallpaper)
        for wp, palette in self.wallpaper_palettes:
            if _same_path(wp, target):
                return palette
        for wp, palette in self.wallpaper_palettes:
            if wp.name == target.name:
                return palette
        return None


def user_conf_path() -> Path:
    """Fallback copy read only by shell helpers when the install tree is absent."""
    return get_env().nyx_dir / CONF_NAME


def default_preset_palette() -> Path:
    return get_env().config_dir / "noctalia" / "palettes" / f"{PROJECT_NAME}-preset.json"


def _as_bool(value: str) -> bool:
    return (value or "").strip().lower() in _TRUE


def _as_path(value: str) -> Optional[Path]:
    text = (value or "").strip()
    if not text:
        return None
    return Path(os.path.expanduser(os.path.expandvars(text)))


def _as_paths(value: str) -> tuple[Path, ...]:
    """Split a comma/semicolon-separated value into expanded paths."""
    out: list[Path] = []
    for part in (value or "").replace(";", ",").split(","):
        path = _as_path(part)
        if path is not None:
            out.append(path)
    return tuple(out)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b


def _as_pairs(values) -> tuple[tuple[Path, Path], ...]:
    """Parse ``wallpaper = palette`` values into path pairs (bad lines dropped)."""
    pairs: list[tuple[Path, Path]] = []
    for item in values or []:
        left, sep, right = str(item).partition("=")
        if not sep:
            continue
        wallpaper = _as_path(left)
        palette = _as_path(right)
        if wallpaper is not None and palette is not None:
            pairs.append((wallpaper, palette))
    return tuple(pairs)


def _parse_file(path: Path) -> dict:
    data = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip an inline comment only when it follows whitespace, so values
        # like URLs or ``#RRGGBB`` survive.
        for marker in (" #", "\t#"):
            idx = value.find(marker)
            if idx != -1:
                value = value[:idx].rstrip()
        if key:
            if key in _LIST_KEYS:
                data.setdefault(key, []).append(value)
            else:
                data[key] = value
    return data


def load_config() -> Config:
    """Read ``ZEK-niri.conf`` from the install tree and resolve every field."""
    env = get_env()
    raw = {key: (list(val) if isinstance(val, list) else val) for key, val in _DEFAULTS.items()}
    for key, value in _parse_file(env.repo_dir / CONF_NAME).items():
        if key in _LIST_KEYS:
            raw[key] = list(value)
        else:
            raw[key] = value
    return Config(
        ask_language_each_start=_as_bool(raw["ask_language_each_start"]),
        wallpaper_dirs=_as_paths(raw["wallpaper_dir"]),
        preset_palettes=_as_paths(raw["preset_palette"]) or (default_preset_palette(),),
        wallpaper_palettes=_as_pairs(raw.get("wallpaper_palette", [])),
        log_path=_as_path(raw["log_path"]),
        noctalia_scheme_source=(raw["noctalia_scheme_source"] or "wallpaper").strip(),
        noctalia_scheme_name=(raw["noctalia_scheme_name"] or "soft").strip(),
    )


_CONFIG: Optional[Config] = None


def get_config() -> Config:
    """Return the cached resolved configuration."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


def reload_config() -> None:
    """Forget the cached config (test hook; also used after seeding a new file)."""
    global _CONFIG
    _CONFIG = None
