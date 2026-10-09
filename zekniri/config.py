"""Runtime configuration for the engine itself: ``ZEK-niri.conf``.

A flat ``key = value`` file (``#`` full-line comments, blank lines ignored,
``~`` / ``$HOME`` expanded). Two layers: the install-tree ``ZEK-niri.conf``
ships defaults, and the copy at ``~/.config/<PROJECT_NAME>/ZEK-niri.conf`` — the
one users edit — overrides same-named keys. Repeatable list keys are replaced by
the later file, not appended.

Wallpapers are addressed per file, not per folder:

    preset_palette = <wallpaper file> = <palette file>     # repeatable

Each mapped palette belongs to its own wallpaper and is applied by
``ZEK-niri palette``. A bare ``preset_palette = <palette file>`` (no ``=``) is a
global fallback. The wallpaper *deploy* directory is derived from the parent
dirs of the mapped wallpaper files; with no mapping it falls back to
``<Pictures>/wallpaper``. ``wallpaper_palette`` is an alias for the pair form.

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

# Recognized keys and shipped defaults. Repeatable keys start as empty lists.
_DEFAULTS = {
    "ask_language_each_start": "false",
    "log_path": "",
    "noctalia_scheme_source": "wallpaper",
    "noctalia_scheme_name": "soft",
    "preset_palette": [],
    "wallpaper_palette": [],
    "waybar_colors": [],
}

# Repeatable keys: every line is collected instead of overwriting.
_LIST_KEYS = {"preset_palette", "wallpaper_palette", "waybar_colors"}


@dataclass(frozen=True)
class Config:
    ask_language_each_start: bool
    wallpaper_palettes: tuple[tuple[Path, Path], ...]
    waybar_colors: tuple[tuple[Path, Path], ...]
    default_palettes: tuple[Path, ...]
    log_path: Optional[Path]
    noctalia_scheme_source: str
    noctalia_scheme_name: str

    @property
    def wallpaper_dirs(self) -> tuple[Path, ...]:
        """Deploy dirs derived from the mapped wallpaper files' parent dirs."""
        dirs: list[Path] = []
        for wallpaper, _ in self.wallpaper_palettes:
            parent = wallpaper.parent
            if parent not in dirs:
                dirs.append(parent)
        return tuple(dirs)

    @property
    def wallpaper_dir(self) -> Optional[Path]:
        """Primary derived dir; None = auto ``<Pictures>/wallpaper``."""
        return self.wallpaper_dirs[0] if self.wallpaper_dirs else None

    @property
    def preset_palette(self) -> Path:
        """Global/fallback palette: first bare ``preset_palette`` or first mapped."""
        if self.default_palettes:
            return self.default_palettes[0]
        if self.wallpaper_palettes:
            return self.wallpaper_palettes[0][1]
        return default_preset_palette()

    @property
    def preset_palette_name(self) -> str:
        """Noctalia palette name (file stem) for ``color-scheme-set custom``."""
        return self.preset_palette.stem

    @property
    def preset_palette_names(self) -> tuple[str, ...]:
        if self.default_palettes:
            return tuple(p.stem for p in self.default_palettes)
        return tuple(p.stem for _, p in self.wallpaper_palettes)

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

    def waybar_colors_for(self, wallpaper: Path) -> Optional[Path]:
        """Waybar CSS mapped to ``wallpaper`` (exact path first, then basename)."""
        target = Path(wallpaper)
        for wp, css in self.waybar_colors:
            if _same_path(wp, target):
                return css
        for wp, css in self.waybar_colors:
            if wp.name == target.name:
                return css
        return None


def user_conf_path() -> Path:
    """The config users edit; seeded from the install tree, overrides its defaults."""
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
    """Read install-tree defaults, then the user-copy override, and resolve."""
    env = get_env()
    raw = {key: (list(val) if isinstance(val, list) else val) for key, val in _DEFAULTS.items()}
    # Defaults from the install tree, then ``~/.config/<PROJECT_NAME>/ZEK-niri.conf``
    # overrides. List keys are replaced by the later file (not appended).
    for path in (env.repo_dir / CONF_NAME, user_conf_path()):
        for key, value in _parse_file(path).items():
            if key in _LIST_KEYS:
                raw[key] = list(value)
            else:
                raw[key] = value

    pair_lines: list[str] = []
    single_lines: list[str] = []
    for line in raw.get("preset_palette", []):
        (pair_lines if "=" in str(line) else single_lines).append(line)
    pair_lines += list(raw.get("wallpaper_palette", []))

    default_palettes: list[Path] = []
    for line in single_lines:
        default_palettes.extend(_as_paths(line))

    return Config(
        ask_language_each_start=_as_bool(raw["ask_language_each_start"]),
        wallpaper_palettes=_as_pairs(pair_lines),
        waybar_colors=_as_pairs(raw.get("waybar_colors", [])),
        default_palettes=tuple(default_palettes),
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
