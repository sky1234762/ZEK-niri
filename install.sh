#!/usr/bin/env bash

# ==============================================================================
# zekniri — generic dotfiles installer bootstrap
# Lightweight Bash wrapper: environment preflight, then hands over to the
# pure-stdlib Python engine. No pip, no build step, no root.
# ==============================================================================

set -euo pipefail

# --- ANSI palette (mirrors zekniri/constants.py:Colors) ---
RED=$'\033[1;31m'; GRN=$'\033[1;32m'; YEL=$'\033[1;33m'; BLU=$'\033[1;34m'; OFF=$'\033[0m'

# --- Bilingual helper: the bootstrap runs before Python i18n exists ---
_lang_is_zh() { [[ "${LANG:-}${LC_ALL:-}" == *zh* ]]; }
say() { if _lang_is_zh; then printf '%s' "$1"; else printf '%s' "${2:-$1}"; fi; }

CACHE_DIR="$HOME/.cache/ZEKniri"
BOOTSTRAP_URL="https://raw.githubusercontent.com/sky1234762/ZEK-niri/main/install.sh"

# Normalize XDG variables so a sandbox HOME cannot leak into the host.
if [ -n "${XDG_STATE_HOME:-}" ] && [[ "$XDG_STATE_HOME" != "$HOME/"* ]]; then
    export XDG_STATE_HOME="$HOME/.local/state"
fi
if [ -n "${XDG_CONFIG_HOME:-}" ] && [[ "$XDG_CONFIG_HOME" != "$HOME/"* ]]; then
    export XDG_CONFIG_HOME="$HOME/.config"
fi
if [ -n "${XDG_CACHE_HOME:-}" ] && [[ "$XDG_CACHE_HOME" != "$HOME/"* ]]; then
    export XDG_CACHE_HOME="$HOME/.cache"
fi

# ZEKNIRI_REPO: single-source override, never silently replaced.
if [ -n "${ZEKNIRI_REPO:-}" ]; then
    case "$ZEKNIRI_REPO" in
        https://*|git@*|ssh://*) ;;
        *)
            printf '%s[✗] %s%s\n' "$RED" \
                "$(say "ZEKNIRI_REPO 指定的地址不受支持: ${ZEKNIRI_REPO}" "Unsupported ZEKNIRI_REPO address: ${ZEKNIRI_REPO}")" \
                "$OFF" >&2
            exit 1
            ;;
    esac
fi

REPO_URL="${ZEKNIRI_REPO:-https://github.com/sky1234762/ZEK-niri.git}"

git_clone_timeout() {
    local url="$1" target_dir="$2"
    local git_args=(clone)
    if [ -t 2 ]; then
        git_args+=(--progress)
    fi
    git_args+=(-c http.lowSpeedTime=15 -c http.lowSpeedLimit=1000 --depth 1 "$url" "$target_dir")
    env GIT_TERMINAL_PROMPT=0 git "${git_args[@]}"
}

exec_python_engine() {
    local target_dir="$1"
    shift

    cd -- "$target_dir" || return 1
    # -I -S blocks PYTHON* / sitecustomize startup injection; the fixed launcher
    # receives the validated tree and user arguments separately.
    local python_launcher='import sys; target = sys.argv.pop(1); sys.path.insert(0, target); sys.argv[0] = "ZEK-niri"; from zekniri.cli import main; main()'

    # Only reconnect to /dev/tty when stdin is piped (curl | bash) AND no subcommand args are given.
    if [ "$#" -eq 0 ] && [ ! -t 0 ] && [ -t 1 ] && [ -r /dev/tty ]; then
        exec python3 -I -S -c "$python_launcher" "$target_dir" "$@" < /dev/tty
    else
        exec python3 -I -S -c "$python_launcher" "$target_dir" "$@"
    fi
}

engine_is_complete() {
    local target_dir="$1"
    local module
    [ -f "$target_dir/install.sh" ] || return 1
    for module in __init__ __main__ cli constants core deps doctor i18n menu_app menu_config menu_fullscreen menu_instance network tui; do
        [ -f "$target_dir/zekniri/$module.py" ] || return 1
    done
    for module in __init__ atomic assets deploy manifest templates; do
        [ -f "$target_dir/zekniri/deploy/$module.py" ] || return 1
    done
    for module in __init__ backup uninstall; do
        [ -f "$target_dir/zekniri/state/$module.py" ] || return 1
    done
    [ -d "$target_dir/configs" ] && [ -d "$target_dir/assets" ]
}

main() {
    # 1. Never run as root.
    if [ "$(id -u)" -eq 0 ]; then
        printf '\n%s[✗] %s%s\n\n' "$RED" \
            "$(say "请勿以 root 运行，使用普通用户重新执行: ./install.sh" "Do not run as root. Re-run as normal user: ./install.sh")" \
            "$OFF" >&2
        exit 1
    fi

    # 2. Locate the script.
    local real_script="" script_dir=""
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
        real_script="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
        script_dir="$(cd "$(dirname "$real_script")" 2>/dev/null && pwd)"
    fi

    # 3. Python 3.11+ (tomllib).
    if ! command -v python3 >/dev/null 2>&1; then
        printf '%s[✗] %s%s\n' "$RED" \
            "$(say "未找到 python3，请先安装 Python 3.11+。" "python3 is required but missing. Please install Python 3.11+ first.")" \
            "$OFF" >&2
        exit 1
    fi
    local python_version py_major py_minor
    python_version="$(python3 -I -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" || {
        printf '%s[✗] %s%s\n' "$RED" \
            "$(say "无法确定 Python 版本，请安装 Python 3.11+。" "Could not determine the Python version. Please install Python 3.11+.")" \
            "$OFF" >&2
        exit 1
    }
    IFS=. read -r py_major py_minor <<< "$python_version"
    if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 11 ]; }; then
        printf '%s[✗] %s%s\n' "$RED" \
            "$(say "需要 Python 3.11+（当前 $python_version），请升级后重试。" "Python 3.11+ is required (found $python_version). Please upgrade python3 and retry.")" \
            "$OFF" >&2
        exit 1
    fi

    # 4. Local repository execution.
    if [ -n "$script_dir" ] \
        && { [ -d "$script_dir/zekniri" ] || [ -d "$script_dir/configs" ] || [ -d "$script_dir/assets" ]; }; then
        if ! engine_is_complete "$script_dir"; then
            printf '%s[✗] %s: %s%s\n' "$RED" "$(say "zekniri 源码不完整" "zekniri source is incomplete")" "$script_dir" "$OFF" >&2
            printf '    %s\n' "$(say "请恢复或重新克隆仓库后再运行 ./install.sh。" "Restore or clone the repository again, then rerun ./install.sh.")" >&2
            exit 1
        fi
        exec_python_engine "$script_dir" "$@"
    fi

    # 5. Standalone / cache execution.
    if ! command -v git >/dev/null 2>&1; then
        printf '%s[✗] %s%s\n' "$RED" \
            "$(say "未找到 git，请先安装。" "git is missing. Please install git first.")" \
            "$OFF" >&2
        exit 1
    fi

    if [ -d "$CACHE_DIR/.git" ] && ! engine_is_complete "$CACHE_DIR"; then
        printf '%s[!] %s%s\n' "$YEL" \
            "$(say "缓存源码不完整，正在重建…" "Cached source is incomplete; rebuilding it…")" \
            "$OFF" >&2
        rm -rf "$CACHE_DIR"
        git_clone_timeout "$REPO_URL" "$CACHE_DIR" || exit 1
    elif [ ! -d "$CACHE_DIR/.git" ]; then
        printf '%s:: %s%s\n' "$BLU" "$(say "拉取仓库至缓存 ($CACHE_DIR)…" "Pulling repository to cache ($CACHE_DIR)…")" "$OFF" >&2
        git_clone_timeout "$REPO_URL" "$CACHE_DIR" || exit 1
    else
        printf '%s:: %s%s\n' "$BLU" "$(say "更新缓存仓库…" "Updating cache repository…")" "$OFF" >&2
        if [ -t 2 ]; then
            git -c http.lowSpeedTime=15 -c http.lowSpeedLimit=1000 -c http.connectTimeout=10 -c http.timeout=20 -C "$CACHE_DIR" pull --ff-only --progress || true
        else
            git -c http.lowSpeedTime=15 -c http.lowSpeedLimit=1000 -c http.connectTimeout=10 -c http.timeout=20 -C "$CACHE_DIR" pull --ff-only --quiet >/dev/null 2>&1 || true
        fi
    fi

    if engine_is_complete "$CACHE_DIR"; then
        exec_python_engine "$CACHE_DIR" "$@"
    else
        printf '%s[✗] %s: %s%s\n' "$RED" "$(say "缓存源码仍不完整" "Cached source is still incomplete")" "$CACHE_DIR" "$OFF" >&2
        printf '    %s\n' "$(say "请检查网络后重新运行引导。" "Check the network, then run the bootstrap again.")" >&2
        exit 1
    fi
}

main "$@"
