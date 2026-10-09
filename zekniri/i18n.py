"""Internationalization — a tiny lookup table, no gettext.

Add a string = add the key to BOTH ``zh`` and ``en``. ``tests/test_i18n.py``
scans every ``msg()`` / ``prompt_confirm()`` call and fails on any key that is
missing or orphaned.
"""

import os
from pathlib import Path
from typing import Optional

from zekniri.constants import PROJECT_NAME

_FALLBACK_LANG = "en"
_LANGUAGE: Optional[str] = None


def _lang_file() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))) / ".config" / PROJECT_NAME / "language"


def _detect_language() -> str:
    env = (os.environ.get("LC_ALL") or "") + (os.environ.get("LANG") or "")
    return "zh" if "zh" in env.lower() else "en"


def get_language() -> str:
    global _LANGUAGE
    if _LANGUAGE is not None:
        return _LANGUAGE
    try:
        stored = _lang_file().read_text(encoding="utf-8").strip()
        if stored in ("zh", "en"):
            _LANGUAGE = stored
            return _LANGUAGE
    except OSError:
        pass
    _LANGUAGE = _detect_language()
    return _LANGUAGE


def set_language(lang: str) -> None:
    global _LANGUAGE
    if lang not in ("zh", "en"):
        return
    _LANGUAGE = lang
    try:
        path = _lang_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(lang, encoding="utf-8")
    except OSError:
        pass


def _reset_language_cache() -> None:
    """Test hook: forget the cached language."""
    global _LANGUAGE
    _LANGUAGE = None


def has_stored_language() -> bool:
    """True when the user has already picked a language (so we don't ask again)."""
    try:
        return _lang_file().is_file()
    except OSError:
        return False


def msg(key: str, *args) -> str:
    """Return the localized string for ``key``, formatted with ``args``."""
    lang = get_language()
    table = TRANSLATIONS.get(lang, TRANSLATIONS[_FALLBACK_LANG])
    template = table.get(key)
    if template is None:
        template = TRANSLATIONS[_FALLBACK_LANG].get(key, key)
    if args:
        try:
            return template.format(*args)
        except (IndexError, KeyError):
            return template
    return template


TRANSLATIONS = {
    "en": {
        # brand
        "logo_name": "ZEKniri",
        "logo_tagline": "niri & noctaliaV5 windows manager for CPK themes",
        "logo_version": "v{0}",
        "logo_note": "kaguyaho~",
        # errors
        "err_root_denied": "[✗] Do not run as root. Use a normal user.",
        "err_already_running": "[✗] Another zekniri instance is running (pid {0}).",
        "err_unknown_command": "[✗] Unknown command: {0}",
        "err_invalid_args": "[✗] Invalid arguments. Usage: {0}",
        "err_engine_incomplete": "[✗] Engine files are incomplete or an update was interrupted. Rerun install.sh.",
        "interactive_terminal_required": "[✗] This action needs an interactive terminal.",
        # help
        "cli_help": (
            "{0} — ZEKniri installer\n\n"
            "Usage: {1} [command]\n\n"
            "  install [full|config]      deploy configs (full = + deps + assets)\n"
            "  update [--force|--no-deploy]\n"
            "  snapshot [note]            save current configs\n"
            "  rollback [index]           restore a snapshot\n"
            "  list                       list snapshots\n"
            "  deps [core|apps]           install packages\n"
            "  assets                     deploy wallpapers\n"
            "  show-config                show resolved runtime config\n"
            "  palette [--wait] [list|<wp>] apply the wallpaper's palette\n"
            "  watch [sec|install|remove] follow wallpaper changes / manage service\n"
            "  doctor                     self-check\n"
            "  bug                        logs\n"
            "  uninstall [standard|keep-data|purge]\n"
            "  test                       sandbox deploy (developers)\n"
            "  help\n\n"
            "Run without a command for the interactive panel."
        ),
        "config_title": "Resolved runtime configuration",
        "config_file_line": "source: {0}",
        "config_hint": "Edit the user file to override; changes apply on the next run.",
        "palette_list_title": "Wallpaper → palette mapping",
        "palette_list_empty": "No wallpaper_palette mapping configured.",
        "palette_no_noctalia": "noctalia command not found.",
        "palette_no_wallpaper": "Could not read noctalia's current wallpaper.",
        "palette_unmapped": "No palette mapped for wallpaper {0}.",
        "palette_applied": "[✓] Applied palette {1} (wallpaper {0})",
        "palette_apply_failed": "[!] Failed to apply palette {0}.",
        "palette_auto_mode_skip": "[ZEKniri] Noctalia-auto mode; palette mapping skipped (use --force).",
        "watch_started": "[ZEKniri] watching wallpaper changes (every {0}s)…",
        "watch_stopped": "[ZEKniri] watcher stopped.",
        "watch_already_running": "[ZEKniri] watcher already running.",
        "watch_no_systemd": "[!] systemctl not found; cannot install the watcher service.",
        "watch_installed": "[✓] Watcher service installed and started ({0}).",
        "watch_removed": "[✓] Watcher service removed.",
        "watch_not_installed": "[!] Watcher service is not installed.",
        # menu
        "menu_title": "Control panel",
        "menu_hint": "[↑↓] move  [Enter] select  [q] quit",
        "menu_group_deploy": "Deploy",
        "menu_group_maint": "Maintain",
        "menu_group_system": "System",
        "menu_opt1": "Install / deploy configs",
        "menu_opt2": "Dependencies & apps",
        "menu_opt3": "Snapshots",
        "menu_opt4": "Update from repository",
        "menu_opt5": "Uninstall",
        "menu_opt6": "Self-check",
        "menu_opt7": "Logs",
        "menu_opt0": "Quit",
        "submenu_hint": "[↑↓] move  [Enter] select  [q] back",
        "selective_hint": "[↑↓] move  [Space] toggle  [a] all  [n] none  [Enter] confirm  [q] cancel",
        "press_any_key": "Press any key to continue…",
        "lang_title": "Select language / 选择语言",
        "lang_hint": "[↑↓] move / 移动    [Enter] select / 选择",
        # install
        "master_menu_title": "Select what to deploy",
        "master_item_assets": "Wallpaper pack",
        "master_item_behavior": "Behaviour",
        "master_item_backup": "Snapshot before deploying",
        "preflight_summary": "Pre-flight summary:",
        "preflight_configs": "  - {0} config app(s)",
        "preflight_assets": "  - wallpaper pack",
        "preflight_deps": "  - system dependencies",
        "preflight_backup": "  - snapshot current configs first",
        "install_cancelled": "Cancelled.",
        "install_step_configs": "Deploying configs…",
        "install_step_assets": "Deploying wallpapers…",
        "copying_configs": "Deploying configs…",
        "copy_done": "Configs deployed.",
        # deploy logs
        "log_deploy_config_item": "[✓] deployed {0}",
        "log_deploy_state_item": "  installed ~/.local/state/{0}/{1}",
        "log_deploy_config_failed": "[✗] failed to deploy {0}",
        "deploy_failed": "[✗] Deploy failed: {0}",
        "log_keep_custom_file": "  kept {0}",
        "log_keep_custom_dir": "  kept {0}",
        "log_keep_preserved_file": "  kept ~/.config/{0}/{1}",
        "log_config_deploy_skipped": "Deploy skipped.",
        # summary
        "summary_title_install": "Done",
        "summary_title_test": "Test deploy complete",
        "summary_title_failed": "Finished with errors",
        "summary_section_details": "Details",
        "summary_item_configs_ok": "Deployed {0} config app(s)",
        "summary_item_configs_failed": "Failed: {0}",
        "summary_item_configs_skip": "No configs selected",
        "summary_item_assets_ok": "Copied {0} wallpaper(s)",
        "summary_item_assets_existing": "Wallpapers present",
        "summary_section_preserved": "Preserved",
        "summary_section_next": "Next",
        "summary_next_start": "Log out and back in, or restart the target app.",
        "summary_next_command": "From now on, type `{0}` in a terminal to open the control panel.",
        "summary_next_manual": "Docs: run `{0} help`.",
        "summary_exit_hint": "[Enter] exit",
        # deps
        "deps_title": "Missing dependencies",
        "deps_menu_title": "Dependencies",
        "deps_sub_core": "Core dependencies",
        "deps_sub_apps": "Recommended apps",
        "deps_sub_back": "Back",
        "deps_all_installed": "All dependencies are installed.",
        "deps_installing": "Installing: {0}",
        "deps_installed": "Installed.",
        "deps_failed": "Install failed. Check the output above.",
        "dep_installed": "(installed)",
        "new_deps_detected": "New dependencies: {0}",
        "prompt_install_missing_deps": "Install missing dependencies now?",
        "distro_unsupported": "[✗] This install step is for pacman-based systems.",
        "distro_unsupported_hint": "Install the packages with your own package manager.",
        "apps_title": "Recommended apps",
        "apps_none": "No optional apps are registered.",
        # update
        "updating_done": "Update complete.",
        "updating_failed": "Update failed.",
        "update_no_git": "[!] Not a git checkout; update is unavailable.",
        "update_timeout": "Timed out while contacting the remote.",
        "update_use_pacman": "This install is managed by the system package manager. Update it there.",
        "update_restart_needed": "[!] Code updated but the deploy did not run. Run `zekniri install`.",
        "overwrite_title": "Code updated",
        "overwrite_opt1": "Deploy the new configs",
        "overwrite_opt2": "Skip deployment",
        # snapshots
        "backing_up": "Creating snapshot…",
        "backup_done": "Snapshot saved: {0}",
        "log_backup_item": "  {0}",
        "no_snapshots": "No snapshots yet.",
        "snapshot_list_title": "Snapshots",
        "snapshot_not_found": "[✗] Snapshot not found: {0}",
        "snapshot_index_out_of_range": "[✗] Snapshot index out of range: {0}",
        "rollback_restoring": "Restoring {0}…",
        "rollback_done": "Rolled back.",
        "rollback_partial": "[!] Rolled back with errors; see the log.",
        "snapshot_deleted": "Snapshot deleted: {0}",
        "snapshot_delete_confirm": "Delete snapshot {0}?",
        "snapshot_delete_cancelled": "Cancelled.",
        "snapshot_menu_title": "Snapshots",
        "snapshot_sub_create": "Create a snapshot",
        "snapshot_sub_list": "List snapshots",
        "snapshot_sub_delete": "Delete a snapshot",
        "snapshot_sub_rollback": "Roll back",
        "snapshot_sub_back": "Back",
        "snapshot_note_prompt": "Note (optional): ",
        # uninstall
        "uninstall_title": "Select what to remove",
        "uninstall_hint": "[↑↓] move  [Space] toggle  [Enter] confirm  [q] cancel",
        "uninstall_data_section": "Tool data",
        "uninstall_data_label": "Also remove {0} data (snapshots, state)",
        "uninstall_nothing": "Nothing is installed.",
        "uninstall_none_selected": "Nothing selected.",
        "uninstall_removed": "[✓] removed {0}",
        "uninstall_done": "Uninstall complete.",
        "uninstall_done_keep_data": "Configs removed; tool data kept.",
        "uninstall_cancelled": "Cancelled.",
        "uninstall_data_confirm": "Also remove {0} snapshots and state?",
        # doctor
        "doctor_title": "{0} self-check — {1} ({2})",
        "doctor_configs_dir": "configs/ directory present",
        "doctor_assets_dir": "assets/ directory present",
        "doctor_config_home": "~/.config present",
        "doctor_state_dir": "state directory present",
        "doctor_manifests_ok": "all manifests parse",
        "doctor_manifests_bad": "broken manifest(s): {0}",
        "doctor_manifests_skip": "no configs/ to inspect",
        "doctor_snapshots": "{0} snapshot(s)",
        "doctor_deployed": "{0} app(s) deployed",
        "doctor_cli_link": "CLI symlink healthy",
        "doctor_cli_missing": "CLI symlink not found (~/.local/bin)",
        "doctor_cli_system": "system package owns the CLI",
        "doctor_cli_path": "~/.local/bin is on PATH",
        "doctor_cli_path_pending": "~/.local/bin configured (reopen terminal to activate)",
        "doctor_cli_path_missing": "~/.local/bin is not on PATH",
        "path_occlusion_warn": "[!] ~/.local/bin shadows the system package; the system install is not being used.",
        "first_run_ready": "[✓] ZEK-niri is installed; type `ZEK-niri` to run it.",
        "first_run_ready_path": "[✓] ZEK-niri installed; ~/.local/bin added to PATH via {0}. Reopen your terminal, then type `ZEK-niri`.",
        "bug_report_written": "Report written to {0}",
        "log_title": "Log: {0}",
        "log_empty": "No log entries yet.",
        "log_unreadable": "Log file could not be read.",
        "test_start": "Sandbox test deploy…",
    },
    "zh": {
        "logo_name": "ZEKniri",
        "logo_tagline": "niri & noctaliaV5 windows manager for CPK themes",
        "logo_version": "v{0}",
        "logo_note": "kaguyaho~",
        "err_root_denied": "[✗] 请勿以 root 运行，使用普通用户。",
        "err_already_running": "[✗] 已有另一个 zekniri 实例在运行（pid {0}）。",
        "err_unknown_command": "[✗] 未知命令：{0}",
        "err_invalid_args": "[✗] 参数不合法。用法：{0}",
        "err_engine_incomplete": "[✗] 引擎文件不完整或更新中途被打断。重新运行 install.sh 即可恢复。",
        "interactive_terminal_required": "[✗] 该操作需要交互式终端。",
        "cli_help": (
            "{0} — ZEKniri 安装器\n\n"
            "用法：{1} [命令]\n\n"
            "  install [full|config]      部署配置（full = 含依赖与资产）\n"
            "  update [--force|--no-deploy]\n"
            "  snapshot [备注]            存档当前配置\n"
            "  rollback [序号]            从存档恢复\n"
            "  list                       查看所有存档\n"
            "  deps [core|apps]           安装软件包\n"
            "  assets                     部署壁纸\n"
            "  show-config                查看解析后的运行配置\n"
            "  palette [--wait] [list|<壁纸>] 应用壁纸对应的配色\n"
            "  watch [秒|install|remove]  监听壁纸切换 / 管理监听服务\n"
            "  doctor                     自检\n"
            "  bug                        日志\n"
            "  uninstall [standard|keep-data|purge]\n"
            "  test                       沙箱部署（开发者）\n"
            "  help\n\n"
            "不带命令运行进入交互面板。"
        ),
        "config_title": "解析后的运行配置",
        "config_file_line": "来源：{0}",
        "config_hint": "修改用户文件即可覆盖；下次运行生效。",
        "palette_list_title": "壁纸 → 配色映射",
        "palette_list_empty": "未配置 wallpaper_palette 映射。",
        "palette_no_noctalia": "未找到 noctalia 命令。",
        "palette_no_wallpaper": "读不到 noctalia 当前壁纸。",
        "palette_unmapped": "壁纸 {0} 没有对应配色。",
        "palette_applied": "[✓] 已应用配色 {1}（壁纸 {0}）",
        "palette_apply_failed": "[!] 应用配色 {0} 失败。",
        "palette_auto_mode_skip": "[ZEKniri] 当前是 Noctalia 自动模式，已跳过配色映射（可用 --force 强制）。",
        "watch_started": "[ZEKniri] 正在监听壁纸切换（每 {0}s）…",
        "watch_stopped": "[ZEKniri] 监听已停止。",
        "watch_already_running": "[ZEKniri] 监听已在运行。",
        "watch_no_systemd": "[!] 未找到 systemctl，无法安装监听服务。",
        "watch_installed": "[✓] 监听服务已安装并启动（{0}）。",
        "watch_removed": "[✓] 监听服务已移除。",
        "watch_not_installed": "[!] 监听服务未安装。",
        "menu_title": "控制面板",
        "menu_hint": "[↑↓] 移动  [Enter] 选择  [q] 退出",
        "menu_group_deploy": "部署",
        "menu_group_maint": "维护",
        "menu_group_system": "系统",
        "menu_opt1": "安装 / 部署配置",
        "menu_opt2": "依赖与软件",
        "menu_opt3": "快照存档",
        "menu_opt4": "从仓库更新",
        "menu_opt5": "卸载",
        "menu_opt6": "自检",
        "menu_opt7": "日志",
        "menu_opt0": "退出",
        "submenu_hint": "[↑↓] 移动  [Enter] 选择  [q] 返回",
        "selective_hint": "[↑↓] 移动  [Space] 勾选  [a] 全选  [n] 全不选  [Enter] 确认  [q] 取消",
        "press_any_key": "按任意键继续…",
        "lang_title": "选择语言 / Select language",
        "lang_hint": "[↑↓] 移动 / move    [Enter] 选择 / select",
        "master_menu_title": "选择要部署的内容",
        "master_item_assets": "壁纸包",
        "master_item_behavior": "行为",
        "master_item_backup": "部署前先做快照",
        "preflight_summary": "部署前清单：",
        "preflight_configs": "  - {0} 个配置应用",
        "preflight_assets": "  - 壁纸包",
        "preflight_deps": "  - 系统依赖",
        "preflight_backup": "  - 先快照当前配置",
        "install_cancelled": "已取消。",
        "install_step_configs": "正在部署配置…",
        "install_step_assets": "正在部署壁纸…",
        "copying_configs": "正在部署配置…",
        "copy_done": "配置已部署。",
        "log_deploy_config_item": "[✓] 已部署 {0}",
        "log_deploy_state_item": "  已安装 ~/.local/state/{0}/{1}",
        "log_deploy_config_failed": "[✗] 部署失败 {0}",
        "deploy_failed": "[✗] 部署失败：{0}",
        "log_keep_custom_file": "  已保留 {0}",
        "log_keep_custom_dir": "  已保留 {0}",
        "log_keep_preserved_file": "  已保留 ~/.config/{0}/{1}",
        "log_config_deploy_skipped": "已跳过部署。",
        "summary_title_install": "完成",
        "summary_title_test": "测试部署完成",
        "summary_title_failed": "完成，但有错误",
        "summary_section_details": "详情",
        "summary_item_configs_ok": "已部署 {0} 个配置应用",
        "summary_item_configs_failed": "失败：{0}",
        "summary_item_configs_skip": "未选择任何配置",
        "summary_item_assets_ok": "已复制 {0} 个壁纸",
        "summary_item_assets_existing": "壁纸已存在",
        "summary_section_preserved": "已保留",
        "summary_section_next": "下一步",
        "summary_next_start": "注销后重新登录，或重启对应应用。",
        "summary_next_command": "以后在终端输入 `{0}` 即可打开控制面板。",
        "summary_next_manual": "文档：运行 `{0} help`。",
        "summary_exit_hint": "[Enter] 退出",
        "deps_title": "缺失的依赖",
        "deps_menu_title": "依赖",
        "deps_sub_core": "核心依赖",
        "deps_sub_apps": "推荐软件",
        "deps_sub_back": "返回",
        "deps_all_installed": "所有依赖已安装。",
        "deps_installing": "正在安装：{0}",
        "deps_installed": "已安装。",
        "deps_failed": "安装失败，请查看上方输出。",
        "dep_installed": "（已安装）",
        "new_deps_detected": "发现新依赖：{0}",
        "prompt_install_missing_deps": "现在安装缺失的依赖？",
        "distro_unsupported": "[✗] 该安装步骤仅适用于基于 pacman 的系统。",
        "distro_unsupported_hint": "请用你的包管理器自行安装这些软件包。",
        "apps_title": "推荐软件",
        "apps_none": "未登记任何可选软件。",
        "updating_done": "更新完成。",
        "updating_failed": "更新失败。",
        "update_no_git": "[!] 不是 git 检出，无法更新。",
        "update_timeout": "连接远端超时。",
        "update_use_pacman": "当前安装由系统包管理器接管，请在那里更新。",
        "update_restart_needed": "[!] 代码已更新但部署未执行。请运行 `zekniri install`。",
        "overwrite_title": "代码已更新",
        "overwrite_opt1": "部署新配置",
        "overwrite_opt2": "跳过部署",
        "backing_up": "正在创建快照…",
        "backup_done": "快照已保存：{0}",
        "log_backup_item": "  {0}",
        "no_snapshots": "暂无快照。",
        "snapshot_list_title": "快照",
        "snapshot_not_found": "[✗] 未找到快照：{0}",
        "snapshot_index_out_of_range": "[✗] 快照序号越界：{0}",
        "rollback_restoring": "正在恢复 {0}…",
        "rollback_done": "已回滚。",
        "rollback_partial": "[!] 回滚有错误，详见日志。",
        "snapshot_deleted": "已删除快照：{0}",
        "snapshot_delete_confirm": "删除快照 {0}？",
        "snapshot_delete_cancelled": "已取消。",
        "snapshot_menu_title": "快照存档",
        "snapshot_sub_create": "创建快照",
        "snapshot_sub_list": "查看快照",
        "snapshot_sub_delete": "删除快照",
        "snapshot_sub_rollback": "回滚",
        "snapshot_sub_back": "返回",
        "snapshot_note_prompt": "备注（可选）：",
        "uninstall_title": "选择要移除的内容",
        "uninstall_hint": "[↑↓] 移动  [Space] 勾选  [Enter] 确认  [q] 取消",
        "uninstall_data_section": "工具数据",
        "uninstall_data_label": "同时移除 {0} 数据（快照、状态）",
        "uninstall_nothing": "没有已安装的内容。",
        "uninstall_none_selected": "未选择任何内容。",
        "uninstall_removed": "[✓] 已移除 {0}",
        "uninstall_done": "卸载完成。",
        "uninstall_done_keep_data": "配置已移除，工具数据已保留。",
        "uninstall_cancelled": "已取消。",
        "uninstall_data_confirm": "同时移除 {0} 的快照与状态？",
        "doctor_title": "{0} 自检 — {1}（{2}）",
        "doctor_configs_dir": "configs/ 目录存在",
        "doctor_assets_dir": "assets/ 目录存在",
        "doctor_config_home": "~/.config 存在",
        "doctor_state_dir": "状态目录存在",
        "doctor_manifests_ok": "所有 manifest 解析正常",
        "doctor_manifests_bad": "损坏的 manifest：{0}",
        "doctor_manifests_skip": "没有 configs/ 可检查",
        "doctor_snapshots": "{0} 个快照",
        "doctor_deployed": "已部署 {0} 个应用",
        "doctor_cli_link": "CLI 软链正常",
        "doctor_cli_missing": "未找到 CLI 软链（~/.local/bin）",
        "doctor_cli_system": "由系统包提供 CLI",
        "doctor_cli_path": "~/.local/bin 已在 PATH 中",
        "doctor_cli_path_pending": "~/.local/bin 已配置（重开终端后生效）",
        "doctor_cli_path_missing": "~/.local/bin 不在 PATH 中",
        "path_occlusion_warn": "[!] ~/.local/bin 遮蔽了系统包，实际未使用系统安装。",
        "first_run_ready": "[✓] ZEK-niri 已安装，输入 ZEK-niri 即可运行。",
        "first_run_ready_path": "[✓] ZEK-niri 已安装；已把 ~/.local/bin 加入 PATH（{0}）。重开终端后输入 ZEK-niri 即可运行。",
        "bug_report_written": "报告已写入 {0}",
        "log_title": "日志：{0}",
        "log_empty": "暂无日志。",
        "log_unreadable": "日志文件无法读取。",
        "test_start": "沙箱测试部署…",
    },
}
