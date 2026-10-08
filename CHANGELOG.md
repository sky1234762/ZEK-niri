# Changelog

All notable changes to this project are documented here. One line per user-visible
change, natural language, only the net change versus the last release.

## [1.0.0]

- Fix: `ZEK-niri.conf` is read from the install tree by both the engine and shell helpers (single source of truth); a stale `~/.config/ZEKniri/ZEK-niri.conf` no longer shadows it.
- Per-wallpaper palettes: `wallpaper_palette = <壁纸> = <配色>` mapping with a `ZEK-niri palette` command that applies noctalia's current wallpaper palette.
- First run self-installs the CLI: `~/.local/bin/<CLI_CMD>` symlink plus idempotent PATH registration (fish/zsh/bash), so `ZEK-niri` works in the next terminal.
- Runtime config `ZEK-niri.conf` (language prompt, wallpaper dir + preset palette, log path, noctalia picker) with a `show-config` command; wallpaper and preset paths accept comma-separated lists.
- First release: atomic config deployment with `__custom__` preservation, snapshots,
  a health check, and an interactive panel.
