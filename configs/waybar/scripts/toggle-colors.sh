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
MANUAL="colors.css"
NOCTALIA="colors-noctalia.css"

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/noctalia"
APPS_TOML="$CONF_DIR/templates-apps.toml"
APPS_OFF="$APPS_TOML.disabled"
ASSETS="/usr/share/noctalia/assets/templates"

# 读取 ZEK-niri 配置：优先安装树里的 ZEK-niri.conf（仓库=唯一真源，靠 ~/.local/bin/ZEK-niri
# 软链定位），找不到再回退用户副本 ~/.config/ZEKniri/ZEK-niri.conf。
_resolve_conf() {
    local launcher="$HOME/.local/bin/ZEK-niri" tree=""
    if [ -L "$launcher" ]; then
        tree="$(cd "$(dirname "$(readlink -f "$launcher" 2>/dev/null)")" 2>/dev/null && pwd)"
        if [ -n "$tree" ] && [ -f "$tree/ZEK-niri.conf" ]; then
            printf '%s' "$tree/ZEK-niri.conf"
            return
        fi
    fi
    printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}/ZEKniri/ZEK-niri.conf"
}
CONF_FILE="$(_resolve_conf)"
trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }
conf_get() {  # conf_get KEY DEFAULT
    local key="$1" def="$2" line k v
    [[ -f "$CONF_FILE" ]] || { printf '%s' "$def"; return; }
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
        line="${line%%[[:space:]]#*}"
        [[ "$line" == *=* ]] || continue
        k="$(trim "${line%%=*}")"
        [[ "$k" == "$key" ]] || continue
        v="$(trim "${line#*=}")"
        printf '%s' "${v/#\~/$HOME}"
        return
    done < "$CONF_FILE"
    printf '%s' "$def"
}

# 预设配色文件路径（多值时取第一个；noctalia 只支持一个 custom palette）
PRESET_PALETTE_PATH="$(conf_get preset_palette "$HOME/.config/noctalia/palettes/ZEKniri-preset.json")"
PRESET_PALETTE_PATH="$(trim "${PRESET_PALETTE_PATH%%,*}")"
PRESET_PALETTE="$(basename "$PRESET_PALETTE_PATH" .json)"

# noctalia模式取色器（source + name）
NOCTALIA_SCHEME_SOURCE="$(conf_get noctalia_scheme_source "wallpaper")"
NOCTALIA_SCHEME_NAME="$(conf_get noctalia_scheme_name "soft")"

# 静默调用 noctalia IPC
ns() { noctalia msg "$@" >/dev/null 2>&1 || true; }

# 当前生效的配色文件名
active() {
    grep -oE '@import "(colors[^"]*\.css)"' "$STYLE" | head -1 | sed -E 's/@import "(.*)"/\1/'
}

# 启用 Alacritty / cava 模板并渲染；templates-apply 触发 waybar 模板的 post_hook 重载
apps_enable() {
    if [[ -f "$APPS_OFF" ]]; then
        mv -f "$APPS_OFF" "$APPS_TOML"
    fi
    ns config-reload
    sleep 0.3
    ns templates-apply
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
      sed -i -E "s|@import \"$NOCTALIA\";|@import \"$MANUAL\";|" "$STYLE"
      apps_disable
      # 让 Noctalia 同步固定调色板
      ns color-scheme-set custom "$PRESET_PALETTE"
      # 单次重载：借 waybar 模板的 post_hook（已防抖）
      ns templates-apply
    else
      # -> Noctalia 模式
      sed -i -E "s|@import \"$MANUAL\";|@import \"$NOCTALIA\";|" "$STYLE"
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
