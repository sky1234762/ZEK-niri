#!/usr/bin/env bash
# 安装 ZEK-blv / ZEK-danmaku 到 ~/.local/bin。
# 用法：./install.sh   （可用 BILI_LIVE_STREAM_SRC=/path 指定原脚本位置）
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/ZEK-blv"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SRC="$SCRIPT_DIR/ZEK-blv"
DANMAKU_SRC="$SCRIPT_DIR/ZEK-danmaku"

# 找原房间控制脚本：环境变量 → 常见位置 → 新/旧安装位置
DEP_SRC=""
for cand in \
    "${BILI_LIVE_STREAM_SRC:-}" \
    "$HOME/下载/bilibili_live_stream" \
    "$SCRIPT_DIR/bilibili_live_stream" \
    "$SCRIPT_DIR/scirpt/bilibili_live_stream-1" \
    "$SHARE_DIR/bilibili_live_stream" \
    "$PREFIX/share/bili-live/bilibili_live_stream"; do
    if [ -n "$cand" ] && [ -f "$cand" ]; then DEP_SRC="$cand"; break; fi
done

mkdir -p "$BIN_DIR" "$SHARE_DIR"

# 1) 主程序（TUI）
install -m 755 "$MAIN_SRC" "$BIN_DIR/ZEK-blv"
echo "已安装主程序: $BIN_DIR/ZEK-blv"

# 1b) 弹幕工具
if [ -f "$DANMAKU_SRC" ]; then
    install -m 755 "$DANMAKU_SRC" "$BIN_DIR/ZEK-danmaku"
    echo "已安装弹幕工具: $BIN_DIR/ZEK-danmaku"
fi

# 2) 原房间控制脚本（依赖）
if [ -f "$DEP_SRC" ]; then
    install -m 644 "$DEP_SRC" "$SHARE_DIR/bilibili_live_stream"
    echo "已安装依赖脚本: $SHARE_DIR/bilibili_live_stream"
else
    echo "警告: 没找到原脚本 $DEP_SRC"
    echo "      可用 BILI_LIVE_STREAM_SRC=/path/to/bilibili_live_stream ./install.sh 指定，"
    echo "      或之后设环境变量 BILI_LIVE_STREAM_BIN。"
fi

# 3) 清理旧名字的安装（从 bili-live 升级过来时）
for old in "$BIN_DIR/bili-live" "$BIN_DIR/bili-danmaku"; do
    if [ -f "$old" ]; then rm -f "$old"; echo "已移除旧命令: $old"; fi
done
if [ -d "$PREFIX/share/bili-live" ]; then
    rm -rf "$PREFIX/share/bili-live"
    echo "已移除旧数据目录: $PREFIX/share/bili-live"
fi

# 4) PATH 检查
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "注意: $BIN_DIR 不在 PATH 里，请把下面这行加入 ~/.bashrc 或 ~/.zshrc："
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    echo "然后执行: source ~/.bashrc"
else
    echo "PATH 已包含 $BIN_DIR"
fi

echo ""
echo "完成。可直接运行:  ZEK-blv   /   ZEK-danmaku"
