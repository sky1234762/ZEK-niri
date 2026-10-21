#!/usr/bin/env bash
# 一键切换 Waybar 配色：预设模式 <-> Noctalia 模式
#
# 用法：
#   toggle-colors.sh status   # 供 waybar custom 模块读取状态（JSON）
#   toggle-colors.sh toggle   # 切换配色并重载 waybar
#
# 切换逻辑：
#   - 改写 style.css 的 @import 行：colors.css（手写） <-> colors-noctalia.css
#   - Noctalia模式：启用并应用 Alacritty / cava 的 Noctalia 模板同时启用自动取色方案
#   - 预设模式：撤销并禁用模板，恢复固定主题
#
# 重载方式：不直接给 waybar 发 SIGUSR2，走 “noctalia msg templates-apply”
#   触发 waybar 用户模板的 post_hook 来完成一次重载。
#   原因：短时间内两次 SIGUSR2 会让 waybar 在重载未完成时再次重载而崩溃。
set -euo pipefail

STYLE="${WAYBAR_STYLE:-$HOME/.config/waybar/style.css}"
ACTIVE_FILE="${WAYBAR_ACTIVE:-$HOME/.config/waybar/colors-active.css}"
MANUAL="colors.css"
NOCTALIA="colors-noctalia.css"

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/noctalia"
APPS_TOML="$CONF_DIR/templates-apps.toml"
APPS_OFF="$APPS_TOML.disabled"
ASSETS="/usr/share/noctalia/assets/templates"

# 配置来源：用户副本优先（个人配置在这改），安装树里的 ZEK-niri.conf 作为默认兜底。
_user_conf="${XDG_CONFIG_HOME:-$HOME/.config}/ZEKniri/ZEK-niri.conf"
_repo_conf=""
_launcher="$HOME/.local/bin/ZEK-niri"
if [ -L "$_launcher" ]; then
    _tree="$(cd "$(dirname "$(readlink -f "$_launcher" 2>/dev/null)")" 2>/dev/null && pwd)"
    [ -n "$_tree" ] && [ -f "$_tree/ZEK-niri.conf" ] && _repo_conf="$_tree/ZEK-niri.conf"
fi
CONF_FILES=()
[ -f "$_user_conf" ] && CONF_FILES+=("$_user_conf")
[ -f "$_repo_conf" ] && CONF_FILES+=("$_repo_conf")
trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }
conf_get() {  # conf_get KEY DEFAULT（用户副本优先，安装树兜底）
    local key="$1" def="$2" f line k v
    for f in "${CONF_FILES[@]}"; do
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
            line="${line%%[[:space:]]#*}"
            [[ "$line" == *=* ]] || continue
            k="$(trim "${line%%=*}")"
            [[ "$k" == "$key" ]] || continue
            v="$(trim "${line#*=}")"
            printf '%s' "${v/#\~/$HOME}"
            return
        done < "$f"
    done
    printf '%s' "$def"
}

# 预设配色兜底：优先裸写的 preset_palette（无 `=`），否则内置 ZEKniri-preset。
# 逐张壁纸的 `壁纸 = 配色` 配对不算默认，避免把第一张的配色当成全局默认。
conf_get_preset_default() {
    local f line k v
    for f in "${CONF_FILES[@]}"; do
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
            line="${line%%[[:space:]]#*}"
            [[ "$line" == *=* ]] || continue
            k="$(trim "${line%%=*}")"
            [[ "$k" == "preset_palette" ]] || continue
            v="$(trim "${line#*=}")"
            [[ "$v" == *=* ]] && continue
            printf '%s' "${v/#\~/$HOME}"
            return
        done < "$f"
    done
    printf '%s' "$HOME/.config/noctalia/palettes/ZEKniri-preset.json"
}
PRESET_PALETTE="$(basename "$(conf_get_preset_default)" .json)"

# noctalia模式取色器（source + name）
NOCTALIA_SCHEME_SOURCE="$(conf_get noctalia_scheme_source "wallpaper")"
NOCTALIA_SCHEME_NAME="$(conf_get noctalia_scheme_name "soft")"

# 静默调用 noctalia IPC
ns() { noctalia msg "$@" >/dev/null 2>&1 || true; }

HAS_NOCTALIA=0
command -v noctalia >/dev/null 2>&1 && HAS_NOCTALIA=1

# 没有 noctalia 时直接重载 waybar，避免“点了没反应”。
reload_waybar() {
    if [ -x "$HOME/.config/waybar/scripts/reload-waybar.sh" ]; then
        bash "$HOME/.config/waybar/scripts/reload-waybar.sh" >/dev/null 2>&1 || true
    elif command -v waybar >/dev/null 2>&1; then
        pkill -USR2 -x waybar >/dev/null 2>&1 || true
    fi
}

apply_templates() {
    if [ "$HAS_NOCTALIA" = 1 ]; then
        ns templates-apply
    else
        reload_waybar
    fi
}

# 当前生效的配色文件名（读 colors-active.css，不限制文件名前缀）
active() {
    grep -oE '@import "[^"]*\.css"' "$ACTIVE_FILE" | head -1 | sed -E 's/@import "(.*)"/\1/'
}

# 改写 colors-active.css 的 @import（模式切换只动这个稳定入口，不碰 style.css）
set_import() {
    printf '/* 当前生效的配色入口（由 toggle-colors.sh 改写）。 */\n@import "%s";\n' "$1" > "$ACTIVE_FILE"
}

# 启用 Alacritty / cava 模板并渲染；templates-apply 触发 waybar 模板的 post_hook 重载
apps_enable() {
    if [[ -f "$APPS_OFF" ]]; then
        mv -f "$APPS_OFF" "$APPS_TOML"
    fi
    ns config-reload
    sleep 0.3
    apply_templates
}

# 撤销并禁用 Alacritty / cava 模板
apps_disable() {
    if [[ -x "$ASSETS/alacritty/undo.sh" ]]; then
        bash "$ASSETS/alacritty/undo.sh" >/dev/null 2>&1 || true
    fi
    if [[ -x "$ASSETS/cava/undo.sh" ]]; then
        bash "$ASSETS/cava/undo.sh" >/dev/null 2>&1 || true
    fi
    if [[ -f "$APPS_TOML" ]]; then
        mv -f "$APPS_TOML" "$APPS_OFF"
    fi
    ns config-reload
}

case "${1:-status}" in
  status)
    if [[ "$(active)" == "$NOCTALIA" ]]; then
      printf '{"text":"󰏘","alt":"noctalia","class":"noctalia","tooltip":"当前状态：Noctalia\\n左键：切换方案"}\n'
    else
      printf '{"text":"󰏘","alt":"manual","class":"manual","tooltip":"当前状态：预设\\n左键：切换方案"}\n'
    fi
    ;;
  toggle)
    if [[ "$(active)" == "$NOCTALIA" ]]; then
      # -> 预设模式
      set_import "$MANUAL"
      apps_disable
      # 让 Noctalia 同步「当前壁纸对应」的配色；未映射时回退到 preset_palette 的默认预设
      if command -v ZEK-niri >/dev/null 2>&1; then
        ZEK-niri palette >/dev/null 2>&1 || ns color-scheme-set custom "$PRESET_PALETTE"
      else
        ns color-scheme-set custom "$PRESET_PALETTE"
      fi
      # 单次重载：有 noctalia 走模板 post_hook，没有就直接重载 waybar
      apply_templates
    else
      # -> Noctalia 模式
      set_import "$NOCTALIA"
      # 让 Noctalia 切到自动取色方案
      ns color-scheme-set "$NOCTALIA_SCHEME_SOURCE" "$NOCTALIA_SCHEME_NAME"
      # apps_enable 内部的 templates-apply 已触发 post_hook 重载（已防抖）
      apps_enable
    fi
    ;;
  *)
    echo "usage: $0 {status|toggle}" >&2
    exit 2
    ;;
esac
