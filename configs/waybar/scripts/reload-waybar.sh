#!/usr/bin/env bash
# 防抖重载 waybar
#
# 作用：保证两次 SIGUSR2 之间至少间隔 MIN_GAP_MS 毫秒。
# 背景：waybar 在上一次重载尚未完成时收到第二次 SIGUSR2 会崩溃（实测 0.2s 间隔必崩）。
#       当一个操作会触发多次重载（例如 color-scheme-set 引起的主题重载 + templates-apply）
#       时，用本脚本串行化并拉开间隔，避免崩溃。
set -euo pipefail

MIN_GAP_MS="${WAYBAR_RELOAD_GAP_MS:-1000}"
STAMP="${XDG_RUNTIME_DIR:-/tmp}/waybar-reload-$UID.stamp"
LOCK="${STAMP}.lock"

now_ms() { date +%s%3N; }

# 串行化并发调用
exec 9>"$LOCK"
flock 9

if [[ -f "$STAMP" ]]; then
    last="$(cat "$STAMP" 2>/dev/null || echo 0)"
    [[ "$last" =~ ^[0-9]+$ ]] || last=0
    now="$(now_ms)"
    delta=$(( now - last ))
    if (( delta < MIN_GAP_MS )); then
        wait_ms=$(( MIN_GAP_MS - delta ))
        sleep "$(awk -v ms="$wait_ms" 'BEGIN{printf "%.3f", ms/1000}')"
    fi
fi

now_ms > "$STAMP"
pkill -SIGUSR2 waybar 2>/dev/null || true
