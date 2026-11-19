"""Checkbox-style uninstall.

Removes selected deployed configs, then (optionally) the tool's own data
(backups / presets / state). Deployed config removal always comes before the
tool-data removal so a failure never orphans the user's config.
"""

import sys
import subprocess
from typing import List

from zekniri.constants import PROJECT_NAME, CLI_CMD
from zekniri.core import get_env, log_msg, remove_path, is_cli_symlink
from zekniri.i18n import msg
from zekniri.tui import CheckboxEntry, CheckboxList, prompt_confirm


def _installed_items() -> List[str]:
    env = get_env()
    from zekniri.deploy import discover_config_items
    items = []
    for name in discover_config_items():
        path = env.config_dir / name
        if path.exists() or path.is_symlink():
            items.append(name)
    return items


def _remove_item(name: str) -> bool:
    env = get_env()
    target = env.config_dir / name
    if not (target.exists() or target.is_symlink()):
        return False
    remove_path(target)
    print(msg("uninstall_removed", name))
    log_msg("INFO", f"Uninstalled config ~/.config/{name}")
    return True


def _remove_tool_data() -> None:
    env = get_env()
    remove_path(env.nyx_dir)
    remove_path(env.state_dir)
    log_msg("INFO", f"Removed tool data {env.nyx_dir} and {env.state_dir}")


def _remove_installed_tools() -> bool:
    """Stop owned services before removing their executables or records."""
    env = get_env()
    unit = env.config_dir / "systemd/user/zekniri-watch.service"
    services = []
    if unit.is_file():
        services.append("zekniri-watch.service")
    if (env.state_dir / "waybar-service-owned").is_file():
        services.append("waybar.service")
    try:
        for service in services:
            result = subprocess.run(
                ["systemctl", "--user", "disable", "--now", service],
                timeout=30, check=False,
            )
            if result.returncode != 0:
                log_msg("ERROR", f"Cannot stop {service}; keeping installed tools")
                return False
        if unit.is_file():
            unit.unlink()
            result = subprocess.run(
                ["systemctl", "--user", "daemon-reload"], timeout=30, check=False,
            )
            if result.returncode != 0:
                return False
        bin_dir = env.home / ".local/bin"
        for name in ("ZEK-menu", "ZEK-blv", "ZEK-danmaku"):
            (bin_dir / name).unlink(missing_ok=True)
        if is_cli_symlink(bin_dir / CLI_CMD):
            (bin_dir / CLI_CMD).unlink()
        remove_path(env.data_home / "ZEKniri/zekniri")
        # ZEKlive currently installs its helper at this fixed location.
        (env.home / ".local/share/ZEK-blv/bilibili_live_stream").unlink(missing_ok=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_msg("ERROR", f"Tool cleanup failed: {exc}")
        return False
    return True


def uninstall_zekniri(target: str = "") -> bool:
    """Uninstall configs.

    target: "" / "standard" → interactive checkbox; "purge" / "--all" →
    remove everything without asking; "keep-data" → configs only.
    """
    env = get_env()
    purge_all = target in ("purge", "--all", "all", "3")
    keep_data = target in ("keep-data", "1")

    installed = _installed_items()
    if not installed:
        print(msg("uninstall_nothing"))
        if purge_all:
            if not _remove_installed_tools():
                return False
            _remove_tool_data()
        return True

    chosen: List[str]
    if purge_all:
        chosen = installed
    elif not sys.stdin.isatty():
        chosen = installed
    else:
        entries = [CheckboxEntry(key=f"cfg_{name}", label=name, checked=True) for name in installed]
        if not keep_data:
            entries.append(CheckboxEntry(key="sep_data", label=msg("uninstall_data_section"), is_separator=True))
            entries.append(CheckboxEntry(key="remove_data", label=msg("uninstall_data_label", PROJECT_NAME), checked=False))
        result = CheckboxList("uninstall_title", entries, hint_key="uninstall_hint").run()
        if result is None:
            print(msg("uninstall_cancelled"))
            return True
        chosen = [k.removeprefix("cfg_") for k in result if k.startswith("cfg_")]
        keep_data = "remove_data" not in result

    if not chosen:
        print(msg("uninstall_none_selected"))

    if purge_all and not _remove_installed_tools():
        return False

    protected_any = False
    for name in chosen:
        _remove_item(name)

    if purge_all or not keep_data:
        if purge_all or not sys.stdin.isatty() or prompt_confirm("uninstall_data_confirm", "n", PROJECT_NAME):
            _remove_tool_data()
            protected_any = True

    print(msg("uninstall_done" if protected_any else "uninstall_done_keep_data"))
    return True
