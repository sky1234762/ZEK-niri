"""Portable template rendering — replace deploy-time values in already
deployed config files.

``/home/user`` becomes the real ``$HOME``; the base Waybar ``font-size`` line
marked ``ZEKniri: base font size`` becomes the ``font_size`` value from
``ZEK-niri.conf``. Side-effect-light on purpose: text substitution over
``~/.config/<app>``. Binary files are skipped by attempting a strict UTF-8
decode.
"""

import re
from pathlib import Path
from typing import Optional

from zekniri.config import get_config, reload_config
from zekniri.core import get_env, log_msg

PLACEHOLDER = "/home/user"
FONT_SIZE_MARKER = "ZEKniri: base font size"
_FONT_SIZE_RE = re.compile(
    r"(?m)^(\s*font-size:\s*)[^;]+(;.*" + re.escape(FONT_SIZE_MARKER) + r".*)$"
)
_TEXT_EXTENSIONS = {
    ".kdl", ".conf", ".toml", ".json", ".jsonc", ".ini", ".css", ".sh", ".fish",
    ".lua", ".yml", ".yaml", ".txt", ".md", ".cfg", ".theme", ".desktop", ".xml",
}


def _is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _render_file(path: Path, home: str) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    rendered = content.replace(PLACEHOLDER, home)
    if FONT_SIZE_MARKER in rendered:
        reload_config()
        rendered = _FONT_SIZE_RE.sub(
            rf"\g<1>{get_config().font_size}\g<2>", rendered, count=1
        )
    if rendered == content:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def _phase_render_templates(only_app: Optional[str] = None) -> None:
    """Render placeholders across deployed config files.

    ``only_app`` restricts rendering to one app; None renders only repository-managed apps. Called after every deploy and after backup restores.
    """
    env = get_env()
    config_dir = env.config_dir
    home = str(env.home)

    if only_app is not None:
        roots = [config_dir / only_app]
    else:
        from zekniri.deploy.manifest import discover_deployable_apps
        roots = [config_dir / name for name in discover_deployable_apps()]

    rendered = 0
    for root in roots:
        if root.is_symlink() or root == env.nyx_dir:
            continue
        if root.is_file():
            if _is_probably_text(root) and _render_file(root, home):
                rendered += 1
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if not _is_probably_text(path):
                continue
            if _render_file(path, home):
                rendered += 1
    if rendered:
        log_msg("INFO", f"Rendered placeholder in {rendered} file(s)")
