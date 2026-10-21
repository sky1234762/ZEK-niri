"""Bundled companion tools installed into ``~/.local``.

Unlike ``configs/<app>/`` (deployed to ``~/.config``) or ``assets/`` (wallpapers),
these are standalone executables shipped in the repo. ``ZEKlive`` provides the
``ZEK-blv`` TUI, the ``ZEK-danmaku`` helper, and the ``bilibili_live_stream``
dependency script. Each tool is a separate, opt-in install option.
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from zekniri.core import get_env, log_msg


@dataclass
class ToolDeployResult:
    name: str = ""
    copied: int = 0
    destination: str = ""


def zeklive_present() -> bool:
    """True when the repo ships the ZEKlive tool."""
    return (get_env().repo_dir / "ZEKlive" / "ZEK-blv").is_file()


def _copy_exec(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    dest.chmod(0o755)
    return True


def _find_live_stream(src_dir: Path, share_dir: Path) -> Optional[Path]:
    """Locate the ``bilibili_live_stream`` dependency (env → repo → installs)."""
    env = get_env()
    raw = os.environ.get("BILI_LIVE_STREAM_SRC")
    candidates = [
        Path(raw) if raw else None,
        env.home / "下载" / "bilibili_live_stream",
        src_dir / "bilibili_live_stream",
        src_dir / "scirpt" / "bilibili_live_stream-1",
        share_dir / "bilibili_live_stream",
        env.home / ".local" / "share" / "bili-live" / "bilibili_live_stream",
    ]
    for cand in candidates:
        if cand is not None and cand.is_file():
            return cand
    return None


def menu_present() -> bool:
    """True when the repo ships the standalone ZEK-menu launcher."""
    return (get_env().configs_src / "ZEKniri-menu" / "ZEK-menu").is_file()


def deploy_menu() -> ToolDeployResult:
    """Install ``ZEK-menu``, its Python package, and seed its config.

    Mirrors ``deploy_zeklive``: launcher into ``~/.local/bin``, support modules
    into ``~/.local/share/ZEKniri``, and the user config into
    ``~/.config/ZEKniri/ZEKniri-menu.conf`` (no-clobber).
    """
    env = get_env()
    src_dir = env.configs_src / "ZEKniri-menu"
    bin_dir = env.home / ".local" / "bin"
    package_dir = env.data_home / "ZEKniri" / "zekniri"
    result = ToolDeployResult(name="ZEK-menu", destination=str(bin_dir))
    if not menu_present():
        log_msg("INFO", "ZEK-menu not shipped; skipping")
        return result

    if _copy_exec(src_dir / "ZEK-menu", bin_dir / "ZEK-menu"):
        result.copied += 1

    package_dir.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "menu_app.py", "menu_config.py", "menu_instance.py", "menu_fullscreen.py"):
        src = env.repo_dir / "zekniri" / name
        if src.is_file():
            shutil.copy2(src, package_dir / name)
            result.copied += 1

    conf_src = src_dir / "ZEKniri-menu.conf"
    conf_dest = env.nyx_dir / "ZEKniri-menu.conf"
    if conf_src.is_file() and not conf_dest.exists():
        conf_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(conf_src, conf_dest)
        result.copied += 1

    log_msg("INFO", f"ZEK-menu deployed: {result.copied} file(s) -> {bin_dir}")
    return result


def deploy_zeklive() -> ToolDeployResult:
    """Install ``ZEK-blv`` / ``ZEK-danmaku`` and the live-stream helper.

    Mirrors ``ZEKlive/install.sh``: executables into ``~/.local/bin``, the
    helper into ``~/.local/share/ZEK-blv``, and old ``bili-live`` names cleaned.
    """
    env = get_env()
    src_dir = env.repo_dir / "ZEKlive"
    bin_dir = env.home / ".local" / "bin"
    share_dir = env.home / ".local" / "share" / "ZEK-blv"
    result = ToolDeployResult(name="ZEKlive", destination=str(bin_dir))
    if not zeklive_present():
        log_msg("INFO", "ZEKlive not shipped; skipping")
        return result

    for name in ("ZEK-blv", "ZEK-danmaku"):
        if _copy_exec(src_dir / name, bin_dir / name):
            result.copied += 1

    dep = _find_live_stream(src_dir, share_dir)
    if dep is not None:
        share_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dep, share_dir / "bilibili_live_stream")
        result.copied += 1

    for old in (bin_dir / "bili-live", bin_dir / "bili-danmaku"):
        old.unlink(missing_ok=True)
    shutil.rmtree(env.home / ".local" / "share" / "bili-live", ignore_errors=True)

    log_msg("INFO", f"ZEKlive deployed: {result.copied} file(s) -> {bin_dir}")
    return result
