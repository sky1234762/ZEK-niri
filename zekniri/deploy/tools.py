"""Bundled companion tools installed into ``~/.local``.

Unlike ``configs/<app>/`` (deployed to ``~/.config``) or ``assets/`` (wallpapers),
these are standalone executables shipped in the repo. ``ZEKlive`` provides the
``ZEK-blv`` TUI, the ``ZEK-danmaku`` helper, and the ``bilibili_live_stream``
dependency script. Each tool is a separate, opt-in install option.
"""

import os
import shutil
import subprocess
import time
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


def _service_active(name: str) -> bool:
    try:
        return subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", name],
            timeout=10,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def enable_waybar_service() -> bool:
    """Enable the distro Waybar user service and (re)start it.

    A previous invalid Waybar CSS can leave the unit in systemd's
    ``start-limit-hit`` state. Clear that first, restart with the freshly
    deployed config, and verify the unit is actually active instead of trusting
    ``systemctl start``'s return code alone.
    """
    env = get_env()
    if os.environ.get("ZEKNIRI_SANDBOX"):
        return False
    if shutil.which("systemctl") is None:
        log_msg("INFO", "systemctl not found; skipping waybar.service")
        return False
    if env.run_mode != "system" and not (env.repo_dir / "install.sh").is_file():
        return False  # test/temp tree: never touch the real user manager

    # This marker also lets Niri's startup fallback know that Waybar was chosen.
    try:
        env.state_dir.mkdir(parents=True, exist_ok=True)
        (env.state_dir / "waybar-enabled").touch()
    except OSError:
        pass

    try:
        was_enabled = subprocess.run(
            ["systemctl", "--user", "is-enabled", "--quiet", "waybar.service"],
            timeout=15, check=False,
        ).returncode == 0

        # Clear failed/start-limit state left by an older install; ignore the
        # return code because a clean unit returns non-zero here on some distros.
        subprocess.run(
            ["systemctl", "--user", "reset-failed", "waybar.service"],
            timeout=15, check=False,
        )

        for action in ("enable", "restart"):
            result = subprocess.run(
                ["systemctl", "--user", action, "waybar.service"],
                timeout=30, check=False,
            )
            if result.returncode != 0:
                log_msg("ERROR", f"waybar.service {action} failed")
                return False
            if action == "enable" and not was_enabled:
                env.state_dir.mkdir(parents=True, exist_ok=True)
                (env.state_dir / "waybar-service-owned").touch()

        for _ in range(10):
            if _service_active("waybar.service"):
                return True
            time.sleep(0.1)
        log_msg("ERROR", "waybar.service did not become active")
        return False
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_msg("ERROR", f"waybar.service setup failed: {exc}")
        return False


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
