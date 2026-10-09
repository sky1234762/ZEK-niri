# Changelog

All notable changes to this project are documented here. One line per user-visible
change, natural language, only the net change versus the last release.

## [Unreleased]

- Preset and Noctalia-auto modes are independent: `ZEK-niri palette` (and the watcher) only apply the config mappings while waybar is in preset mode; `--force` overrides.
- `waybar_colors = <wallpaper> = <css>` mapping: per-wallpaper waybar colours, applied by `ZEK-niri palette`/the watcher (switches `style.css`'s `@import` and reloads waybar).
- `ZEK-niri watch` follows noctalia wallpaper changes and applies each wallpaper's palette; `watch install` sets up a systemd user service, niri autostarts it, and `ZEK-niri palette --wait` fixes the waybar click race.
- `ZEK-niri watch` follows noctalia wallpaper changes and applies each wallpaper's palette; auto-started from niri and triggered from the waybar wallpaper module.

## [1.0.0]

- Fix: `ZEK-niri.conf` is read from the install tree by both the engine and shell helpers (single source of truth); a stale `~/.config/ZEKniri/ZEK-niri.conf` no longer shadows it.
- Per-wallpaper palettes: `wallpaper_palette = <壁纸> = <配色>` mapping with a `ZEK-niri palette` command that applies noctalia's current wallpaper palette.
- First run self-installs the CLI: `~/.local/bin/<CLI_CMD>` symlink plus idempotent PATH registration (fish/zsh/bash), so `ZEK-niri` works in the next terminal.
- Runtime config `ZEK-niri.conf` (language prompt, wallpaper dir + preset palette, log path, noctalia picker) with a `show-config` command; wallpaper and preset paths accept comma-separated lists.
- First release: atomic config deployment with `__custom__` preservation, snapshots,
  a health check, and an interactive panel.
