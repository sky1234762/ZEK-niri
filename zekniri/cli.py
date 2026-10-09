"""CLI entry point, command dispatcher, and interactive control panel."""

import os
import sys
from pathlib import Path
from typing import List, Optional

from zekniri.constants import (
    CLI_CMD,
    PACKAGE_NAME,
    PENDING_UPGRADE_ENV,
    PENDING_UPGRADE_MENU_ENV,
    PROJECT_NAME,
    Colors,
)
from zekniri.core import (
    acquire_lock,
    check_path_occlusion,
    ensure_cli_path,
    ensure_cli_symlink,
    get_env,
    init_logger,
    log_msg,
)
from zekniri.config import CONF_NAME, get_config
from zekniri.deploy import (
    assets_present,
    deploy_assets,
    deploy_runtime_conf,
    deploy_selected_configs,
    discover_config_items,
    render_completion_screen,
    test_deploy,
)
from zekniri.deps import (
    get_missing_deps,
    install_selected_deps,
    run_dep_menu_loop,
    run_optional_apps_menu_loop,
)
from zekniri.doctor import generate_bug_report, run_doctor, show_logs
from zekniri.i18n import msg
from zekniri.network import safe_git_pull
from zekniri.palette import apply_palette, install_watcher, list_mappings, remove_watcher, watch
from zekniri.state import (
    backup_configs,
    delete_backup,
    list_backups,
    rollback_configs,
    uninstall_zekniri,
)
from zekniri.tui import (
    CheckboxEntry,
    CheckboxList,
    Menu,
    MenuItem,
    alternate_screen,
    drain_stdin,
    press_any_key,
    prompt_confirm,
    select_language,
)


# --- Install workflow --------------------------------------------------------

def run_master_component_menu(mode: str = "full") -> Optional[dict]:
    """Checklist for choosing configs, assets, and backup behaviour."""
    entries: List[CheckboxEntry] = []
    for item in discover_config_items():
        entries.append(CheckboxEntry(key=f"config_{item}", label=item, checked=True))

    if mode == "full" and assets_present():
        entries.append(CheckboxEntry(key="assets", label=msg("master_item_assets"), checked=True))

    entries.append(CheckboxEntry(key="sep_behavior", label=msg("master_item_behavior"), is_separator=True))
    entries.append(CheckboxEntry(key="behavior_backup", label=msg("master_item_backup"), checked=True))

    chosen = CheckboxList("master_menu_title", entries, hint_key="selective_hint").run()
    if chosen is None:
        return None

    return {
        "configs": [k.removeprefix("config_") for k in chosen if k.startswith("config_")],
        "assets": "assets" in chosen,
        "backup": "behavior_backup" in chosen,
    }


def _phase_preflight_check(mode: str, chosen_configs: List[str], do_assets: bool, do_backup: bool) -> None:
    print(msg("preflight_summary"))
    print(msg("preflight_configs", len(chosen_configs)))
    if do_assets:
        print(msg("preflight_assets"))
    if mode == "full":
        print(msg("preflight_deps"))
    if do_backup:
        print(msg("preflight_backup"))
    print()


def install_configs_workflow(mode: str = "full") -> bool:
    """Full execution pipeline for configs, dependencies, and assets."""
    deploy_runtime_conf()
    if sys.stdin.isatty():
        chosen = run_master_component_menu(mode=mode)
        if not chosen:
            print(msg("install_cancelled"))
            return True
        chosen_configs = chosen["configs"]
        do_assets = chosen["assets"]
        do_backup = chosen["backup"]
        if not chosen_configs and not do_assets:
            print(msg("install_cancelled"))
            return True
    else:
        chosen_configs = discover_config_items()
        do_assets = assets_present()
        do_backup = False

    _phase_preflight_check(mode, chosen_configs, do_assets, do_backup)

    if mode == "full":
        missing = get_missing_deps()
        if missing:
            install_selected_deps(missing)

    if chosen_configs:
        print(msg("install_step_configs"))
        preserved: List[str] = []
        failed = deploy_selected_configs(do_backup=do_backup, items_to_deploy=chosen_configs, preserved_log=preserved)
        if failed:
            render_completion_screen(mode=mode, chosen_items=chosen_configs, preserved_lines=preserved, failed_items=failed)
            return False

    asset_result = None
    if do_assets:
        print(msg("install_step_assets"))
        asset_result = deploy_assets()

    render_completion_screen(
        mode=mode,
        chosen_items=chosen_configs,
        preserved_lines=preserved if chosen_configs else [],
        asset_result=asset_result,
    )
    return True


def offer_overwrite_upgrade(flag: str = "") -> bool:
    """Update flow: pull happened in the parent, now deploy the new code."""
    deploy_runtime_conf()
    if flag == "--no-deploy":
        return True
    if not sys.stdin.isatty() or flag in ("--force", "--deploy"):
        failed = deploy_selected_configs(do_backup=bool(flag))
        if failed:
            render_completion_screen(mode="install", failed_items=failed)
            return False
        asset_result = deploy_assets()
        render_completion_screen(mode="install", asset_result=asset_result)
        return True

    items = [
        MenuItem(label=msg("overwrite_opt1")),
        MenuItem(label=msg("overwrite_opt2"), style="subtle"),
    ]
    choice = Menu("overwrite_title", items, hint_key="submenu_hint").run()
    if choice == 0:
        return install_configs_workflow("full")
    print(msg("log_config_deploy_skipped"))
    return True


def check_new_deps_post_update() -> None:
    missing = get_missing_deps()
    if not missing:
        return
    print(msg("new_deps_detected", " ".join(missing)))
    if not sys.stdin.isatty():
        install_selected_deps(missing)
        return
    if prompt_confirm("prompt_install_missing_deps", "y"):
        install_selected_deps(missing)


# --- Submenus ----------------------------------------------------------------

def snapshot_menu_loop() -> None:
    while True:
        items = [
            MenuItem(label=msg("snapshot_sub_create")),
            MenuItem(label=msg("snapshot_sub_list")),
            MenuItem(label=msg("snapshot_sub_delete"), style="warn"),
            MenuItem(label=msg("snapshot_sub_rollback")),
            MenuItem(label=msg("snapshot_sub_back"), style="subtle"),
        ]
        choice = Menu("snapshot_menu_title", items, hint_key="submenu_hint", compact=True).run()
        if choice == 0:
            sys.stdout.write(msg("snapshot_note_prompt"))
            sys.stdout.flush()
            drain_stdin()
            note = sys.stdin.readline().strip()
            backup_configs(note=note, interactive=True)
            press_any_key()
        elif choice == 1:
            list_backups()
            press_any_key()
        elif choice == 2:
            delete_backup("")
            press_any_key()
        elif choice == 3:
            rollback_configs("")
            press_any_key()
        elif choice == 4 or choice is None:
            break


def deps_menu_loop() -> None:
    if not sys.stdin.isatty():
        print(msg("interactive_terminal_required"), file=sys.stderr)
        return
    while True:
        items = [
            MenuItem(label=msg("deps_sub_core")),
            MenuItem(label=msg("deps_sub_apps")),
            MenuItem(label=msg("deps_sub_back"), style="subtle"),
        ]
        choice = Menu("deps_menu_title", items, hint_key="submenu_hint", compact=True).run()
        if choice == 0:
            run_dep_menu_loop()
        elif choice == 1:
            run_optional_apps_menu_loop()
        elif choice == 2 or choice is None:
            break


def main_menu_loop() -> None:
    while True:
        items = [
            MenuItem(label=msg("menu_opt1"), group_header=msg("menu_group_deploy")),
            MenuItem(label=msg("menu_opt2")),
            MenuItem(label=msg("menu_opt3"), group_header=msg("menu_group_maint")),
            MenuItem(label=msg("menu_opt4")),
            MenuItem(label=msg("menu_opt5"), style="warn"),
            MenuItem(label=msg("menu_opt6"), group_header=msg("menu_group_system")),
            MenuItem(label=msg("menu_opt7")),
            MenuItem(label=msg("menu_opt0"), style="subtle"),
        ]
        choice = Menu("menu_title", items, hint_key="menu_hint").run()

        if choice == 0:
            install_configs_workflow("full")
        elif choice == 1:
            deps_menu_loop()
        elif choice == 2:
            snapshot_menu_loop()
        elif choice == 3:
            env = get_env()
            result = safe_git_pull(env.repo_dir)
            if result is True:
                print(msg("updating_done"))
                press_any_key()
                try:
                    os.execve(sys.executable, [sys.executable, "-m", PACKAGE_NAME],
                              {**os.environ, PENDING_UPGRADE_ENV: "",
                               PENDING_UPGRADE_MENU_ENV: "1"})
                except Exception as e:
                    log_msg("ERROR", f"Re-exec failed: {e}")
                    print(msg("update_restart_needed"), file=sys.stderr)
                    press_any_key()
            elif result is False:
                print(msg("updating_failed"), file=sys.stderr)
                press_any_key()
        elif choice == 4:
            uninstall_zekniri("")
            press_any_key()
        elif choice == 5:
            run_doctor()
            press_any_key()
        elif choice == 6:
            show_logs()
            press_any_key()
        elif choice == 7 or choice is None:
            sys.exit(0)


# --- Show resolved config ----------------------------------------------------

def announce_self_install(path_file: Optional[Path]) -> None:
    """One-time notice that the ``ZEK-niri`` command is installed."""
    env = get_env()
    marker = env.state_dir / ".installed"
    if marker.exists():
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")
    except OSError:
        return
    link = env.home / ".local" / "bin" / CLI_CMD
    if not (link.exists() or link.is_symlink()):
        return
    if path_file is not None:
        print(msg("first_run_ready_path", str(path_file)))
    else:
        print(msg("first_run_ready"))


def show_config() -> None:
    """Print the resolved runtime config, with paths already expanded."""
    env = get_env()
    cfg = get_config()
    print(f"{Colors.BOLD_WHITE}{msg('config_title')}{Colors.RESET}\n")
    user_conf = env.nyx_dir / CONF_NAME
    conf_source = user_conf if user_conf.exists() else (env.repo_dir / CONF_NAME)
    print(msg("config_file_line", str(conf_source)))
    rows = [
        ("ask_language_each_start", "true" if cfg.ask_language_each_start else "false"),
        ("wallpaper_dir", ", ".join(str(p) for p in cfg.wallpaper_dirs) if cfg.wallpaper_dirs else "(auto: <Pictures>/wallpaper)"),
        ("preset_palette", ", ".join(str(p) for p in cfg.default_palettes) if cfg.default_palettes else "(auto: first mapped / ZEKniri-preset)"),
        ("preset_palette_name", ", ".join(cfg.preset_palette_names)),
        ("wallpaper_palette", ", ".join(f"{w.name}->{p.stem}" for w, p in cfg.wallpaper_palettes) if cfg.wallpaper_palettes else "(none)"),
        ("waybar_colors", ", ".join(f"{w.name}->{c.name}" for w, c in cfg.waybar_colors) if cfg.waybar_colors else "(none)"),
        ("log_path", str(cfg.log_path) if cfg.log_path else str(env.state_dir / "install.log")),
        ("noctalia_scheme_source", cfg.noctalia_scheme_source),
        ("noctalia_scheme_name", cfg.noctalia_scheme_name),
    ]
    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        print(f"  {Colors.CYAN}{key.ljust(width)}{Colors.RESET} = {value}")
    print(f"\n{Colors.DIM}{msg('config_hint')}{Colors.RESET}")


# --- Dispatcher --------------------------------------------------------------

def print_help(file=None) -> None:
    if file is None:
        file = sys.stdout
    print(msg("cli_help", PROJECT_NAME, CLI_CMD), file=file)


def exit_usage(usage: str) -> None:
    print(msg("err_invalid_args", usage), file=sys.stderr)
    sys.exit(2)


def _cmd_install(sub_args: List[str]) -> int:
    mode = sub_args[0] if sub_args else "full"
    if len(sub_args) > 1 or mode not in ("full", "config"):
        exit_usage(f"{CLI_CMD} install [full|config]")
    return 0 if install_configs_workflow(mode) else 1


def _cmd_snapshot(sub_args: List[str]) -> int:
    if sub_args and sub_args[0] in ("delete", "rm"):
        if len(sub_args) > 2:
            exit_usage(f"{CLI_CMD} snapshot delete [index]")
        target = sub_args[1] if len(sub_args) > 1 else ""
        return 0 if delete_backup(target) else 1
    note = " ".join(sub_args)
    return 0 if backup_configs(note=note, interactive=False) else 1


def _cmd_rollback(sub_args: List[str]) -> int:
    if len(sub_args) > 1:
        exit_usage(f"{CLI_CMD} rollback [index]")
    return 0 if rollback_configs(sub_args[0] if sub_args else "") else 1


def _cmd_list(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} list")
    list_backups()
    return 0


def _cmd_uninstall(sub_args: List[str]) -> int:
    target = sub_args[0] if sub_args else ""
    valid = ("", "standard", "keep-data", "purge", "--all", "all", "1", "3")
    if len(sub_args) > 1 or target not in valid:
        exit_usage(f"{CLI_CMD} uninstall [standard|keep-data|purge]")
    return 0 if uninstall_zekniri(target) else 1


def _cmd_purge(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} purge")
    return 0 if uninstall_zekniri("purge") else 1


def _cmd_doctor(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} doctor")
    run_doctor()
    return 0


def _cmd_deps(sub_args: List[str]) -> int:
    sub = sub_args[0].lower() if sub_args else ""
    if len(sub_args) > 1 or sub not in ("", "core", "apps", "opt", "optional"):
        exit_usage(f"{CLI_CMD} deps [core|apps]")
    if sub == "core":
        run_dep_menu_loop()
    elif sub in ("apps", "opt", "optional"):
        run_optional_apps_menu_loop()
    else:
        deps_menu_loop()
    return 0


def _cmd_apps(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} apps")
    run_optional_apps_menu_loop()
    return 0


def _cmd_assets(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} assets")
    deploy_assets()
    return 0


def _cmd_bug(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} bug")
    generate_bug_report()
    return 0


def _cmd_test(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} test")
    return 0 if test_deploy() else 1


def _cmd_update(sub_args: List[str]) -> int:
    usage = f"{CLI_CMD} update [--force|--no-deploy]"
    flag = ""
    for cur in sub_args:
        if cur in ("--force", "--deploy", "--no-deploy"):
            if flag:
                exit_usage(usage)
            flag = cur
        else:
            exit_usage(usage)
    env = get_env()
    check_path_occlusion()
    result = safe_git_pull(env.repo_dir)
    if result is True:
        try:
            os.execve(sys.executable, [sys.executable, "-m", PACKAGE_NAME],
                      {**os.environ, PENDING_UPGRADE_ENV: flag})
        except Exception as e:
            log_msg("ERROR", f"Re-exec failed: {e}")
            print(msg("update_restart_needed"), file=sys.stderr)
            return 1
    if result is False:
        print(msg("updating_failed"), file=sys.stderr)
        return 1
    return 0


def _cmd_show_config(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} show-config")
    show_config()
    return 0


def _cmd_palette(sub_args: List[str]) -> int:
    usage = f"{CLI_CMD} palette [--wait] [--force] [list|<wallpaper>]"
    wait = 0.0
    force = False
    rest: List[str] = []
    for arg in sub_args:
        if arg in ("--wait", "-w"):
            wait = 2.0
        elif arg in ("--force", "-f"):
            force = True
        elif arg.startswith("--wait="):
            try:
                wait = float(arg.split("=", 1)[1])
            except ValueError:
                exit_usage(usage)
        elif arg.startswith("-"):
            exit_usage(usage)
        else:
            rest.append(arg)
    if rest and rest[0] in ("list", "ls"):
        if len(rest) > 1:
            exit_usage(usage)
        list_mappings()
        return 0
    if len(rest) > 1:
        exit_usage(usage)
    return 0 if apply_palette(rest[0] if rest else None, wait=wait, force=force) else 1


def _cmd_watch(sub_args: List[str]) -> int:
    if sub_args and sub_args[0] in ("install", "--install"):
        return 0 if install_watcher() else 1
    if sub_args and sub_args[0] in ("remove", "uninstall", "--remove"):
        return 0 if remove_watcher() else 1
    usage = f"{CLI_CMD} watch [seconds|install|remove]"
    interval = 1.0
    if sub_args:
        if len(sub_args) > 1:
            exit_usage(usage)
        try:
            interval = float(sub_args[0])
        except ValueError:
            exit_usage(usage)
    return watch(max(0.2, interval))


def _cmd_help(sub_args: List[str]) -> int:
    if sub_args:
        exit_usage(f"{CLI_CMD} help")
    print_help()
    return 0


COMMANDS = {
    "install":   (_cmd_install,   f"{CLI_CMD} install [full|config]"),
    "deploy":    (_cmd_install,   f"{CLI_CMD} install [full|config]"),
    "snapshot":  (_cmd_snapshot,  f"{CLI_CMD} snapshot [note]"),
    "backup":    (_cmd_snapshot,  f"{CLI_CMD} snapshot [note]"),
    "rollback":  (_cmd_rollback,  f"{CLI_CMD} rollback [index]"),
    "restore":   (_cmd_rollback,  f"{CLI_CMD} rollback [index]"),
    "list":      (_cmd_list,      f"{CLI_CMD} list"),
    "uninstall": (_cmd_uninstall, f"{CLI_CMD} uninstall [standard|keep-data|purge]"),
    "remove":    (_cmd_uninstall, f"{CLI_CMD} uninstall [standard|keep-data|purge]"),
    "purge":     (_cmd_purge,     f"{CLI_CMD} purge"),
    "doctor":    (_cmd_doctor,    f"{CLI_CMD} doctor"),
    "deps":      (_cmd_deps,      f"{CLI_CMD} deps [core|apps]"),
    "apps":      (_cmd_apps,      f"{CLI_CMD} apps"),
    "recommended": (_cmd_apps,    f"{CLI_CMD} apps"),
    "assets":    (_cmd_assets,    f"{CLI_CMD} assets"),
    "show-config": (_cmd_show_config, f"{CLI_CMD} show-config"),
    "config":    (_cmd_show_config, f"{CLI_CMD} show-config"),
    "palette":   (_cmd_palette,   f"{CLI_CMD} palette [list|<wallpaper>]"),
    "watch":     (_cmd_watch,     f"{CLI_CMD} watch [seconds|install|remove]"),
    "bug":       (_cmd_bug,       f"{CLI_CMD} bug"),
    "report":    (_cmd_bug,       f"{CLI_CMD} bug"),
    "test":      (_cmd_test,      f"{CLI_CMD} test"),
    "update":    (_cmd_update,    f"{CLI_CMD} update [--force|--no-deploy]"),
    "help":      (_cmd_help,      f"{CLI_CMD} help"),
    "-h":        (_cmd_help,      f"{CLI_CMD} help"),
    "--help":    (_cmd_help,      f"{CLI_CMD} help"),
}


def main() -> None:
    """Main CLI entrypoint."""
    if os.getuid() == 0:
        print(msg("err_root_denied"), file=sys.stderr)
        sys.exit(1)

    # The long-running watcher must not hold the single-instance lock.
    if not (len(sys.argv) > 1 and sys.argv[1].lower() == "watch"):
        acquire_lock()
    init_logger()
    get_env()
    ensure_cli_symlink()
    announce_self_install(ensure_cli_path())

    pending_flag = os.environ.pop(PENDING_UPGRADE_ENV, None)
    pending_from_menu = os.environ.pop(PENDING_UPGRADE_MENU_ENV, None)

    args = sys.argv[1:]
    if args:
        cmd = args[0].lower()
        sub_args = args[1:]
        entry = COMMANDS.get(cmd)
        if entry:
            handler, _ = entry
            sys.exit(handler(sub_args))
        print(msg("err_unknown_command", args[0]), file=sys.stderr)
        print_help(file=sys.stderr)
        sys.exit(2)

    if pending_flag is not None:
        deploy_ok = offer_overwrite_upgrade(pending_flag)
        check_new_deps_post_update()
        print(msg("updating_done"))
        if not sys.stdin.isatty():
            sys.exit(0 if deploy_ok else 1)
        press_any_key()
        if not pending_from_menu:
            sys.exit(0 if deploy_ok else 1)

    if not sys.stdin.isatty():
        sys.exit(0 if install_configs_workflow("full") else 1)

    with alternate_screen():
        select_language()
        main_menu_loop()


if __name__ == "__main__":
    main()
