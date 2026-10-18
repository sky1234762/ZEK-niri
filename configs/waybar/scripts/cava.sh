#!/bin/bash
# 强制 UTF-8：下面按“字符”而不是“字节”切分 CHARS；C locale 会把 ▁ 当 3 字节。
export LC_ALL=C.UTF-8

# 配置
CHARS="▁▂▃▄▅▆▇█"
BARS=10
CONF="$(mktemp -t waybar_cava_config.XXXXXX)"

# 初始化
len=$((${#CHARS}-1))
idle_char="${CHARS:0:1}"
idle_output=$(printf "%0.s$idle_char" $(seq 1 $BARS))

# 生成 Cava 配置
cat > "$CONF" <<EOF
[general]
bars = $BARS
[input]
method = pulse
source = auto
[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = $len
EOF

cleanup() {
    trap - EXIT INT TERM
    pkill -P $$ 2>/dev/null
    rm -f "$CONF"
    echo "$idle_output"
    exit 0
}
trap cleanup EXIT INT TERM

# 核心检测：是否存在未暂停的音频流
is_audio_active() {
    pactl list sink-inputs 2>/dev/null | grep -q "Corked: no"
}

# 初始状态
echo "$idle_output"

while true; do
    # 如果存在未静音的音频
    if is_audio_active; then
        if ! pgrep -P $$ -x cava >/dev/null; then
            # 这里的 sed 字典是根据你的 CHARS 动态生成的
            sed_dict="s/;//g;"
            for ((i=0; i<=${len}; i++)); do
                sed_dict="${sed_dict}s/$i/${CHARS:$i:1}/g;"
            done
            cava -p "$CONF" 2>/dev/null | sed -u "$sed_dict" &
        fi
        # 正在播放时，稍微降低检查频率减少 CPU 占用
        sleep 1
    else
        if pgrep -P $$ -x cava >/dev/null; then
            pkill -P $$ -x cava 2>/dev/null
            wait 2>/dev/null
            echo "$idle_output"
        fi
        # 没声音时，使用 subscribe 等待事件，被动唤醒，不产生任何循环开销
        timeout 5s pactl subscribe 2>/dev/null | grep --line-buffered "sink-input" | head -n 1 >/dev/null
    fi
done
