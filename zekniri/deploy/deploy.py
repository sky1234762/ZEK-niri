"""Deploy orchestrator — config discovery, the atomic-deploy phase, the
completion screen, and the deploy/test entry points.

Coordinates the deploy siblings: atomic (swap + preserve), manifest (app
discovery), templates (placeholder render), assets (static files).
"""

import shutil
import sys
from pathlib import Path
from typing import List, Optional

from zekniri.constants import CLI_CMD, Colors
from zekniri.config import CONF_NAME, get_config
from zekniri.core import get_env, log_msg
from zekniri.i18n import msg
from zekniri.tui import read_key, show_logo, raw_input_mode, _drain_pending, enter_alt_screen
from zekniri.deploy.atomic import atomic_replace_item
from zekniri.deploy.assets import AssetDeployResult, assets_present, deploy_assets
from zekniri.deploy.manifest import discover_deployable_apps, load_manifest
from zekniri.deploy.templates import _phase_render_templates

_CONFIG_ITEMS_CACHE: List[str] = []


def discover_config_items() -> List[str]:
    """Deployable app names (dirs shipping real config)."""
    global _CONFIG_ITEMS_CACHE
    if _CONFIG_ITEMS_CACHE:
        return _CONFIG_ITEMS_CACHE
    _CONFIG_ITEMS_CACHE = discover_deployable_apps()
    return _CONFIG_ITEMS_CACHE


def _deploy_state_files(app: str, src: Path, state_files: List[str]) -> None:
    """Install manifest ``state`` files into <state_home>/<app>/ (no-clobber).

    These are runtime state files an app owns (e.g. noctalia's settings.toml),
    so a file already present is left alone — the repo copy is only a seed.
    """
    if not state_files:
        return
    env = get_env()
    dest_dir = env.state_home / app
    for rel in state_files:
        src_file = src / rel
        dest_file = dest_dir / rel
        if not src_file.is_file() or dest_file.exists():
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        print(msg("log_deploy_state_item", app, rel))
        log_msg("INFO", f"Deployed state file ~/.local/state/{app}/{rel}")


def deploy_runtime_conf() -> bool:
    """Refresh the fallback ``~/.config/<PROJECT_NAME>/ZEK-niri.conf``.

    The install-tree ``ZEK-niri.conf`` is the single source of truth; this is a
    copy for deployed shell helpers that cannot locate the install tree. It is
    rewritten whenever it differs from the source.
    """
    env = get_env()
    src = env.repo_dir / CONF_NAME
    dest = env.nyx_dir / CONF_NAME
    if not src.is_file():
        return False
    try:
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            return False
    except OSError:
        pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    log_msg("INFO", f"Refreshed fallback config {dest}")
    return True


def _warn_missing_preset() -> None:
    """Warn only when a preset's noctalia dir exists but the file is absent."""
    for palette in get_config().preset_palettes:
        if palette.parent.is_dir() and not palette.is_file():
            log_msg("WARN", f"Configured preset palette missing: {palette}")


def _phase_atomic_deployment(
    items_to_deploy: List[str],
    preserved_log: Optional[List[str]] = None,
    test_mode: bool = False,
) -> List[str]:
    """Atomic copy for the selected configuration units.

    Each app's manifest drives the preserve list and the executable globs. The
    Dunder walk inside atomic_replace_item is untouched.
    """
    env = get_env()
    config_dir = env.config_dir
    config_dir.mkdir(parents=True, exist_ok=True)

    failed_items: List[str] = []
    for item in items_to_deploy:
        src = env.configs_src / item
        dest = config_dir / item

        if not src.exists():
            failed_items.append(item)
            print(msg("log_deploy_config_failed", item), file=sys.stderr)
            log_msg("ERROR", f"Missing config source: {src}")
            continue

        manifest = load_manifest(src)

        if not atomic_replace_item(
            src,
            dest,
            preserved_log=preserved_log,
            test_mode=test_mode,
            preserve=manifest.preserve,
            exclude=manifest.state,
        ):
            failed_items.append(item)
            print(msg("log_deploy_config_failed", item), file=sys.stderr)
            continue

        for pattern in manifest.chmod:
            for p in dest.glob(pattern):
                if p.is_file():
                    try:
                        p.chmod(0o755)
                    except OSError:
                        pass

        _deploy_state_files(item, src, manifest.state)

        print(msg("log_deploy_config_item", item))
        log_msg("INFO", f"Deployed config ~/.config/{item}")

    _warn_missing_preset()
    return failed_items


def deploy_selected_configs(
    do_backup: bool = False,
    items_to_deploy: Optional[List[str]] = None,
    preserved_log: Optional[List[str]] = None,
) -> List[str]:
    """Deploy selected dotfile items with optional backup and placeholder render."""
    if items_to_deploy is None:
        items_to_deploy = discover_config_items()
    if preserved_log is None:
        preserved_log = []

    if do_backup:
        from zekniri.state.backup import backup_configs
        backup_configs(note="auto_snapshot_before_deploy", interactive=False)

    print(msg("copying_configs"))
    failed_items = _phase_atomic_deployment(items_to_deploy, preserved_log=preserved_log)
    if failed_items:
        print(msg("deploy_failed", ", ".join(failed_items)), file=sys.stderr)
        return failed_items
    _phase_render_templates()
    print(msg("copy_done"))
    return []


def render_completion_screen(
    mode: str = "install",
    chosen_items: Optional[List[str]] = None,
    preserved_lines: Optional[List[str]] = None,
    asset_result: Optional[AssetDeployResult] = None,
    failed_items: Optional[List[str]] = None,
) -> None:
    """Render the minimal completion screen."""
    if chosen_items is None:
        chosen_items = discover_config_items()
    if preserved_lines is None:
        preserved_lines = []
    if failed_items is None:
        failed_items = []

    title_key = "summary_title_failed" if failed_items else (
        "summary_title_test" if mode == "test" else "summary_title_install"
    )

    def _render_body():
        title_color = Colors.BOLD_RED if failed_items else Colors.BOLD_GREEN
        sys.stdout.write(f"  {title_color}{msg(title_key)}{Colors.RESET}\n\n")
        sys.stdout.write(f"  {Colors.BOLD_WHITE}{msg('summary_section_details')}{Colors.RESET}\n")

        if failed_items:
            sys.stdout.write(f"    {Colors.BOLD_RED}[✗]{Colors.RESET} {msg('summary_item_configs_failed', ', '.join(failed_items))}\n")
        elif chosen_items or mode == "test":
            sys.stdout.write(f"    {Colors.BOLD_GREEN}[✓]{Colors.RESET} {msg('summary_item_configs_ok', len(chosen_items))}\n")
        else:
            sys.stdout.write(f"    {Colors.BOLD_YELLOW}[!]{Colors.RESET} {msg('summary_item_configs_skip')}\n")

        if asset_result is not None and asset_result.copied:
            sys.stdout.write(f"    {Colors.BOLD_GREEN}[✓]{Colors.RESET} {msg('summary_item_assets_ok', asset_result.copied)}\n")
        elif assets_present():
            sys.stdout.write(f"    {Colors.BOLD_GREEN}[✓]{Colors.RESET} {msg('summary_item_assets_existing')}\n")

        if preserved_lines:
            sys.stdout.write(f"\n  {Colors.BOLD_WHITE}{msg('summary_section_preserved')}{Colors.RESET}\n")
            for line in sorted(set(preserved_lines)):
                sys.stdout.write(f"    {line}\n")

    if not sys.stdin.isatty() or mode == "test":
        sys.stdout.write(Colors.CLEAR_SCREEN)
        show_logo()
        _render_body()
        sys.stdout.write(f"\n  {Colors.BOLD_WHITE}{msg('summary_section_next')}{Colors.RESET}\n")
        sys.stdout.write(f"    {msg('summary_next_start')}\n")
        sys.stdout.write(f"    {msg('summary_next_command', CLI_CMD)}\n")
        sys.stdout.write(f"    {msg('summary_next_manual', CLI_CMD)}\n\n")
        return

    enter_alt_screen()
    sys.stdout.write(Colors.CURSOR_HIDE)
    fd = sys.stdin.fileno()
    try:
        with raw_input_mode(fd):
            _drain_pending(fd, debounce=True)
            sys.stdout.write(Colors.CLEAR_SCREEN)
            show_logo()
            _render_body()
            sys.stdout.write(f"\n{msg('summary_exit_hint')}\n")
            sys.stdout.flush()
            while True:
                key = read_key()
                if key in ("ENTER", "SPACE", "q", "Q", "ESC", "EXIT"):
                    break
    finally:
        _drain_pending(fd, debounce=True)
        sys.stdout.write(Colors.CURSOR_SHOW)
        sys.stdout.flush()


def test_deploy() -> bool:
    """Developer test command: fast idempotent re-deploy in the current env."""
    print(msg("test_start"))

    preserved_log: List[str] = []
    items = discover_config_items()
    failed_items = _phase_atomic_deployment(items, preserved_log=preserved_log, test_mode=True)
    if failed_items:
        print(msg("deploy_failed", ", ".join(failed_items)), file=sys.stderr)
        render_completion_screen(mode="test", chosen_items=items, preserved_lines=preserved_log, failed_items=failed_items)
        return False
    _phase_render_templates()
    asset_result = deploy_assets()
    render_completion_screen(
        mode="test",
        chosen_items=items,
        preserved_lines=preserved_log,
        asset_result=asset_result,
    )
    return True
