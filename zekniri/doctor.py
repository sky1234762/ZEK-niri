"""Health checks.

Add a check = write ``_check_xxx(env) -> None`` and append it to
``DOCTOR_CHECKS``. ``run_doctor()`` never changes.
"""

import datetime
import platform
import tomllib
from pathlib import Path
from typing import Callable, List

from zekniri.constants import CLI_CMD, PROJECT_NAME, Colors
from zekniri.core import cli_path_status, get_env, is_cli_symlink
from zekniri.i18n import msg
from zekniri.deploy.manifest import discover_manifest_apps

DOCTOR_CHECKS: List[Callable] = []


def register(func: Callable) -> Callable:
    DOCTOR_CHECKS.append(func)
    return func


def _report(ok: bool, key: str, *args) -> None:
    if ok:
        tag = f"{Colors.GREEN}[✓]{Colors.RESET}"
    else:
        tag = f"{Colors.YELLOW}[!]{Colors.RESET}"
    print(f"    {tag} {msg(key, *args)}")


@register
def _check_layout(env) -> None:
    _report(env.configs_src.is_dir(), "doctor_configs_dir")
    _report(env.assets_src.is_dir(), "doctor_assets_dir")


@register
def _check_runtime_dirs(env) -> None:
    _report(env.config_dir.is_dir(), "doctor_config_home")
    _report(env.state_dir.is_dir(), "doctor_state_dir")


@register
def _check_manifests(env) -> None:
    if not env.configs_src.is_dir():
        _report(False, "doctor_manifests_skip")
        return
    bad = []
    for path in env.configs_src.iterdir():
        if path.name == ".optional-apps.toml" or path.name.endswith(".module.toml"):
            continue
        mpath = path / ".module.toml" if path.is_dir() else path.parent / (path.name + ".module.toml")
        if mpath.is_file():
            try:
                with open(mpath, "rb") as f:
                    tomllib.load(f)
            except Exception:
                bad.append(mpath.name)
    _report(not bad, "doctor_manifests_ok" if not bad else "doctor_manifests_bad", ", ".join(bad))


@register
def _check_snapshots(env) -> None:
    from zekniri.state import get_all_backups
    snaps = get_all_backups()
    _report(True, "doctor_snapshots", len(snaps))


@register
def _check_deployed(env) -> None:
    deployed = []
    for name, m in discover_manifest_apps():
        if not m.is_deployable:
            continue
        if (env.config_dir / name).exists():
            deployed.append(name)
    _report(bool(deployed), "doctor_deployed", len(deployed))


@register
def _check_cli_symlink(env) -> None:
    link = env.home / ".local" / "bin" / CLI_CMD
    if env.run_mode == "system":
        _report(True, "doctor_cli_system")
        return
    if link.exists() or link.is_symlink():
        _report(is_cli_symlink(link), "doctor_cli_link")
    else:
        _report(False, "doctor_cli_missing")


@register
def _check_cli_path(env) -> None:
    if env.run_mode == "system":
        return
    status = cli_path_status()
    if status == "active":
        _report(True, "doctor_cli_path")
    elif status == "pending":
        _report(True, "doctor_cli_path_pending")
    else:
        _report(False, "doctor_cli_path_missing")


def run_doctor() -> None:
    env = get_env()
    print(f"\n  {Colors.BOLD_WHITE}{msg('doctor_title', PROJECT_NAME, env.version, env.mode_label)}{Colors.RESET}\n")
    for check in DOCTOR_CHECKS:
        check(env)
    print()


def generate_bug_report() -> Path:
    """Write a diagnostic report the user can attach to an issue."""
    env = get_env()
    out_dir = env.cache_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    lines = [
        f"{PROJECT_NAME} bug report",
        f"time: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"version: {env.version}",
        f"mode: {env.mode_label} ({env.run_mode})",
        f"repo_dir: {env.repo_dir}",
        f"config_dir: {env.config_dir}",
        f"python: {platform.python_version()}",
        f"system: {platform.platform()}",
        "",
        "deployable apps:",
    ]
    try:
        for name, m in discover_manifest_apps():
            if m.is_deployable:
                lines.append(f"  - {name}")
    except Exception as e:
        lines.append(f"  (failed: {e})")
    lines.append("")
    lines.append(f"log: {env.state_dir / 'install.log'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(msg("bug_report_written", str(path)))
    return path


def show_logs(max_lines: int = 200) -> None:
    """Write the diagnostic report and print the recent log.

    Backs the "Logs" menu item: the report gives the environment snapshot, the
    tail gives what actually happened. The log is capped so the screen stays
    readable.
    """
    generate_bug_report()
    env = get_env()
    log_file = env.state_dir / "install.log"
    print()
    print(f"  {Colors.BOLD_WHITE}{msg('log_title', str(log_file))}{Colors.RESET}")
    if not log_file.is_file():
        print(f"  {Colors.DIM}{msg('log_empty')}{Colors.RESET}")
        return
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        print(f"  {Colors.DIM}{msg('log_unreadable')}{Colors.RESET}")
        return
    if not lines:
        print(f"  {Colors.DIM}{msg('log_empty')}{Colors.RESET}")
        return
    for line in lines[-max_lines:]:
        print(f"  {line}")
