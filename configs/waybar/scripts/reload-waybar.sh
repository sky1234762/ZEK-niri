#!/usr/bin/env bash
# 仅在 Waybar 实际使用的 CSS 内容变化时重载，并合并并发请求。
set -euo pipefail
umask 077

CONF_DIR="${WAYBAR_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/waybar}"
CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/waybar"
STATE_ROOT="${XDG_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/waybar-reload}"
MIN_GAP_MS="${WAYBAR_RELOAD_GAP_MS:-1000}"

log() {
    if [[ "${WAYBAR_RELOAD_DEBUG:-0}" == "1" ]]; then
        printf '[waybar-reload] %s\n' "$*" >&2
    fi
}
warn() { printf '[waybar-reload] %s\n' "$*" >&2; }

if [[ ! "$MIN_GAP_MS" =~ ^[0-9]{1,7}$ ]]; then
    warn "WAYBAR_RELOAD_GAP_MS must be an integer from 0 to 3600000 (got: $MIN_GAP_MS)"
    exit 2
fi
MIN_GAP_MS=$((10#$MIN_GAP_MS))
if (( MIN_GAP_MS > 3600000 )); then
    warn "WAYBAR_RELOAD_GAP_MS must not exceed 3600000"
    exit 2
fi

# Cache each CSS tree separately; use one user lock because pkill signals every Waybar instance.
if ! read -r CONFIG_KEY < <(python3 - "$CONF_DIR" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1]).expanduser().resolve()
print(sha256(str(root).encode("utf-8")).hexdigest()[:20])
PY
); then
    warn "could not identify the Waybar config directory"
    exit 1
fi

CACHE_DIR="$CACHE_ROOT/$CONFIG_KEY"
FP_FILE="$CACHE_DIR/style-fingerprint"
STAMP="$STATE_ROOT/waybar-reload.stamp"
LOCK="$STAMP.lock"

mkdir -p "$STATE_ROOT" || { warn "cannot create state directory: $STATE_ROOT"; exit 1; }
if ! command -v flock >/dev/null 2>&1; then
    warn "flock is required to serialize reload requests"
    exit 1
fi
exec 9>"$LOCK" || { warn "cannot open reload lock: $LOCK"; exit 1; }
flock 9 || { warn "cannot acquire reload lock: $LOCK"; exit 1; }

# Fingerprint the stylesheet and all local CSS @imports recursively. CSS
# comments are ignored, so template metadata changes do not reload the bar.
read_fingerprint() {
    python3 - "$CONF_DIR" <<'PY'
from hashlib import sha256
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).expanduser().resolve()
entry = root / "style.css"
if not entry.is_file():
    print(f"missing Waybar stylesheet: {entry}", file=sys.stderr)
    raise SystemExit(2)

import_re = re.compile(
    r'''@import\s+(?:url\(\s*(?P<uquote>["']?)(?P<upath>[^"')]*)(?P=uquote)\s*\)|(?P<quote>["'])(?P<qpath>.*?)(?P=quote))\s*[^;]*;''',
    re.IGNORECASE | re.DOTALL,
)


def without_comments(text: str) -> str:
    out = []
    i = 0
    quote = None
    escaped = False
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("unterminated CSS comment")
            out.extend("\n" for c in text[i:end + 2] if c == "\n")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def imports_from(text: str):
    for match in import_re.finditer(text):
        value = match.group("upath")
        if value is None:
            value = match.group("qpath")
        value = value.strip()
        if value:
            yield value


fingerprint = sha256()
visited = set()


def add_css(path: Path) -> None:
    path = path.resolve()
    if path in visited:
        return
    visited.add(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
        normalized = without_comments(text)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"cannot read CSS dependency {path}: {exc}") from exc

    try:
        label = str(path.relative_to(root))
    except ValueError:
        label = str(path)
    fingerprint.update(label.encode("utf-8"))
    fingerprint.update(b"\0")
    fingerprint.update(normalized.encode("utf-8"))
    fingerprint.update(b"\0")

    for imported in imports_from(normalized):
        # Remote stylesheets cannot be hashed reliably offline. Their import
        # declaration remains part of the fingerprint; use WAYBAR_FORCE=1
        # when a remote stylesheet itself changes.
        if imported.startswith(("//", "#")) or re.match(r"^[a-z][a-z0-9+.-]*:", imported, re.I):
            continue
        dependency = Path(imported)
        if not dependency.is_absolute():
            dependency = path.parent / dependency
        if not dependency.is_file():
            raise RuntimeError(f"missing CSS import {imported!r} referenced by {path}")
        add_css(dependency)


try:
    add_css(entry)
except RuntimeError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)
print(fingerprint.hexdigest())
PY
}

if ! FP="$(read_fingerprint)"; then
    warn "could not calculate the active Waybar stylesheet fingerprint"
    exit 1
fi
if [[ ! "$FP" =~ ^[[:xdigit:]]{64}$ ]]; then
    warn "fingerprint helper returned an invalid value"
    exit 1
fi

LAST_FP=""
if [[ -r "$FP_FILE" ]]; then
    IFS= read -r LAST_FP < "$FP_FILE" || true
fi
if [[ "${WAYBAR_FORCE:-0}" != "1" && "$FP" == "$LAST_FP" ]]; then
    log "active CSS is unchanged; skipping reload"
    exit 0
fi
if [[ "${WAYBAR_NO_RELOAD:-0}" == "1" ]]; then
    log "reload suppressed; fingerprint was not marked as applied"
    exit 0
fi

now_ms() {
    local seconds
    IFS=' ' read -r seconds _ < /proc/uptime || return 1
    awk -v seconds="$seconds" 'BEGIN { if (seconds !~ /^[0-9]+([.][0-9]+)?$/) exit 1; printf "%.0f\n", seconds * 1000 }'
}

LAST_MS=0
if [[ -r "$STAMP" ]]; then
    IFS= read -r LAST_MS < "$STAMP" || LAST_MS=0
    [[ "$LAST_MS" =~ ^[0-9]+$ ]] || LAST_MS=0
fi
NOW_MS="$(now_ms)" || { warn "cannot read monotonic system uptime"; exit 1; }
DELTA_MS=$((NOW_MS - LAST_MS))
# A persisted state stamp can outlive a reboot if XDG_RUNTIME_DIR is unset.
if (( DELTA_MS < 0 )); then
    DELTA_MS=0
    LAST_MS=0
fi
if (( LAST_MS > 0 && DELTA_MS < MIN_GAP_MS )); then
    WAIT_MS=$((MIN_GAP_MS - DELTA_MS))
    log "waiting ${WAIT_MS}ms to respect the reload interval"
    sleep "$(awk -v ms="$WAIT_MS" 'BEGIN { printf "%.3f", ms / 1000 }')"
fi

# Re-read after waiting so edits made while requests were coalescing are
# applied by this reload rather than requiring a second reload immediately.
if ! FP="$(read_fingerprint)"; then
    warn "could not recalculate the active Waybar stylesheet fingerprint"
    exit 1
fi
if [[ "${WAYBAR_FORCE:-0}" != "1" && "$FP" == "$LAST_FP" ]]; then
    log "active CSS returned to the already applied version; skipping reload"
    exit 0
fi

if pkill -USR2 -x waybar 2>/dev/null; then
    :
else
    PKILL_STATUS=$?
    if (( PKILL_STATUS == 1 )); then
        log "Waybar is not running; no signal sent and fingerprint left pending"
        exit 0
    fi
    warn "failed to send SIGUSR2 to Waybar (pkill status $PKILL_STATUS); fingerprint left pending"
    exit "$PKILL_STATUS"
fi

# Cache only after a successful signal. A failed/missing Waybar process can
# therefore be retried on the next invocation. Use atomic replacement.
if mkdir -p "$CACHE_DIR"; then
    TMP_FP="$(mktemp "$CACHE_DIR/.style-fingerprint.XXXXXX")" || TMP_FP=""
    if [[ -n "$TMP_FP" ]]; then
        if printf '%s\n' "$FP" > "$TMP_FP" && mv -f -- "$TMP_FP" "$FP_FILE"; then
            :
        else
            rm -f -- "$TMP_FP"
            warn "Waybar was signaled, but the fingerprint cache could not be updated"
        fi
    else
        warn "Waybar was signaled, but a temporary fingerprint file could not be created"
    fi
else
    warn "Waybar was signaled, but the fingerprint cache directory is unavailable"
fi

NOW_MS="$(now_ms)" || NOW_MS=0
if [[ "$NOW_MS" =~ ^[0-9]+$ ]] && (( NOW_MS > 0 )); then
    TMP_STAMP="$(mktemp "$STATE_ROOT/.waybar-stamp.XXXXXX")" || TMP_STAMP=""
    if [[ -n "$TMP_STAMP" ]]; then
        if printf '%s\n' "$NOW_MS" > "$TMP_STAMP" && mv -f -- "$TMP_STAMP" "$STAMP"; then
            :
        else
            rm -f -- "$TMP_STAMP"
            warn "Waybar was signaled, but the throttle timestamp could not be updated"
        fi
    else
        warn "Waybar was signaled, but a temporary throttle file could not be created"
    fi
fi
log "Waybar received SIGUSR2 for changed CSS"
