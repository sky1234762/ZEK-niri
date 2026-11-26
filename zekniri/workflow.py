"""Installation execution shared by CLI entry points, without changing their UI.

The CLI supplies operations so menu rendering and localized messages remain in
one place. Selection is immutable; steps cannot accidentally expand its scope.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class InstallPlan:
    configs: Tuple[str, ...]
    assets: bool = False
    zeklive: bool = False
    backup: bool = False

    @property
    def empty(self) -> bool:
        return not (self.configs or self.assets or self.zeklive)


def _wallpapers(api):
    try:
        return api.deploy_assets()
    except Exception as exc:
        # Wallpapers and optional services must not suppress the remaining tools.
        api.log_msg("ERROR", f"Wallpaper deployment failed: {exc}")
        print(api.msg("install_warn_assets", str(exc)), file=api.sys.stderr)
        return None


def _services(api, configs, announce):
    waybar_ok = False
    if "waybar" in configs:
        if announce:
            print(api.msg("install_step_waybar_service"))
        waybar_ok = api.enable_waybar_service()
        if not waybar_ok:
            print(api.msg("install_warn_waybar_service"), file=api.sys.stderr)
    if ("waybar" in configs or "noctalia" in configs) and api._service_setup_available():
        if announce:
            print(api.msg("install_step_watch_service"))
        if not api.install_watcher():
            print(api.msg("install_warn_watch_service"), file=api.sys.stderr)
    # Only replace the native bar after verifying that Waybar is available.
    api._apply_native_bar_policy(configs, waybar_ok)


def install(api, mode="full"):
    api.deploy_runtime_conf()
    if api.sys.stdin.isatty():
        chosen = api.run_master_component_menu(mode=mode)
        if not chosen:
            print(api.msg("install_cancelled"))
            return True
        plan = InstallPlan(tuple(chosen["configs"]), chosen["assets"], chosen["zeklive"], chosen["backup"])
        if plan.empty:
            print(api.msg("install_cancelled"))
            return True
    else:
        plan = InstallPlan(tuple(api.discover_config_items()), api.assets_present(), api.zeklive_present())
    configs = list(plan.configs)
    api._phase_preflight_check(mode, configs, plan.assets, plan.zeklive, plan.backup)
    if mode == "full":
        missing = api.get_missing_deps()
        if missing and not api.install_selected_deps(missing):
            return False

    preserved = []
    if configs:
        print(api.msg("install_step_configs"))
        failed = api.deploy_selected_configs(do_backup=plan.backup, items_to_deploy=configs, preserved_log=preserved)
        if failed:
            api.render_completion_screen(mode=mode, chosen_items=configs, preserved_lines=preserved, failed_items=failed)
            return False

    asset_result = None
    if plan.assets:
        print(api.msg("install_step_assets"))
        asset_result = _wallpapers(api)
    _services(api, configs, announce=True)
    tool_result = None
    if plan.zeklive:
        print(api.msg("install_step_zeklive"))
        tool_result = api.deploy_zeklive()
    if "niri" in configs and api.sys.stdin.isatty():
        api.choose_and_write_output_modes()
    api.render_completion_screen(mode=mode, chosen_items=configs, preserved_lines=preserved,
                                 asset_result=asset_result, tool_result=tool_result)
    return True


def upgrade(api, flag=""):
    api.deploy_runtime_conf()
    if flag == "--no-deploy":
        return True
    if not api.sys.stdin.isatty() or flag in ("--force", "--deploy"):
        plan = InstallPlan(tuple(api.discover_config_items()), assets=True, backup=bool(flag))
        configs = list(plan.configs)
        failed = api.deploy_selected_configs(do_backup=plan.backup, items_to_deploy=configs)
        if failed:
            api.render_completion_screen(mode="install", failed_items=failed)
            return False
        asset_result = _wallpapers(api)
        _services(api, configs, announce=False)
        api.render_completion_screen(mode="install", asset_result=asset_result)
        return True

    items = [api.MenuItem(label=api.msg("overwrite_opt1")),
             api.MenuItem(label=api.msg("overwrite_opt2"), style="subtle")]
    choice = api.Menu("overwrite_title", items, hint_key="submenu_hint").run()
    if choice == 0:
        return api.install_configs_workflow("full")
    print(api.msg("log_config_deploy_skipped"))
    return True
