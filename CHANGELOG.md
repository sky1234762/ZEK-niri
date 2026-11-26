# Changelog

All notable changes to this project are documented here. One line per user-visible
change, natural language, only the net change versus the last release.

## [Unreleased]

- 移除仓库内桌面歌词插件集成，改由独立插件包管理。安装与升级共用执行流程，保持现有界面、选择项和服务失败回退行为。


## [1.1.3-rc2]

- Waybar wallpaper module: middle-click now opens Noctalia's desktop widgets editor instead of switching to the next wallpaper.
- Repeated `uninstall keep-data` preserves backups; `purge` stops the watcher, removes companion launchers/modules, and disables Waybar only when this installer recorded enabling it. Failed service cleanup aborts purge.
- Deployment renders only selected app trees; rollback renders only restored apps, leaving unrelated configs and snapshots untouched.
- Installation respects absolute XDG config/data/state/cache roots, isolates exported Pictures paths in sandbox tests, and propagates dependency failures while keeping optional service setup failures non-fatal.
- Wallpapers are deployed before optional autostart services; a broken Waybar or watcher unit can no longer prevent the wallpaper pack from being installed.
- Waybar and watcher service setup now clears `start-limit-hit`/failed state, restarts, and verifies the unit is active; Niri startup has a direct-run fallback when systemd is unavailable.
- Noctalia's native bar is disabled only after Waybar is confirmed running; a Noctalia-only install keeps it enabled. The state seed no longer ships author-specific wallpaper/avatar paths, and deployment repairs stale `directory`/`default`/`last`/monitor paths.

- `ZEK-niri test` now runs in a temporary HOME sandbox: it no longer writes to the real `~/.config`, Pictures directory, or Noctalia state, prints the sandbox path, and cleans it up on exit.
- After config deployment, the installer shows a TUI selector with every supported resolution/refresh combination per Niri output and writes the chosen modes to `~/.config/niri/config.kdl`.
- Install flow now installs and restarts `zekniri-watch.service` (wallpaper palette + Waybar font hot reload) automatically when Waybar/Noctalia is selected.
- New `font_size` in `ZEK-niri.conf` controls the base Waybar CSS font size; the marked base `font-size` line in `style.css` is rendered at deploy time, and `ZEK-niri watch` hot-reloads it when the config changes (no reinstall).
- Install flow enables, resets, restarts, and verifies the systemd user `waybar.service` for the Waybar component, with a Niri startup fallback.
- Noctalia's native bar sections (`[bar.*] enabled`) are disabled only after Waybar is verified running; the seeded state keeps them enabled, and other settings are preserved.
- ZEK-menu: `memo_path` is now repeatable; each entry renders as "打开 <filename>" and opens text files in the terminal editor (directories via `xdg-open`).

## [1.1.1a]

- Waybar reloads now fingerprint the active CSS import tree, ignore CSS comments, and coalesce identical requests under one per-user signal lock, with per-config CSS caches. The script honors XDG paths, supports forced reloads and safe suppression, retries after missing Waybar or signal errors, uses monotonic timing, and provides optional debug logs.

## [1.1.0]

- ZEK-menu now opens with `Ctrl+Middle` only; the right-Shift trigger was removed.
- Removed the per-wallpaper `waybar_colors` mapping; preset mode now keeps the static `colors.css` (ZEKniri-preset), and `ZEK-niri palette`/the watcher no longer rewrite waybar's `@import`. Existing `waybar_colors` lines in `ZEK-niri.conf` are ignored.
- The wallpaper pack now also points Noctalia's `[wallpaper] directory` at `<Pictures>/wallpaper` when it was still the Pictures root, so the pack appears directly in Noctalia's wallpaper picker; a custom directory is left untouched.
- Wallpaper destination detection now reads `$XDG_PICTURES_DIR` (exported env or `~/.config/user-dirs.dirs`) before `xdg-user-dir`/`~/Pictures`, so localised folders like `~/图片` deploy correctly even when `xdg-user-dir` is missing.
- `ZEK-menu` is now installed with the config package: launcher → `~/.local/bin/ZEK-menu`, Python modules → `~/.local/share/ZEKniri/zekniri/`, sample config → `~/.config/ZEKniri/ZEKniri-menu.conf` (no-clobber). `configs/ZEKniri-menu` declares `deploy = false` so it is not mistaken for a `~/.config` dotfile app.
- `toggle-colors.sh` now falls back to a direct waybar reload when `noctalia` is not installed, instead of leaving the click with no visible effect.

## [1.0.5]

- Waybar hardening: `style.css` now imports a stable `colors-active.css` entry that is preserved across deploys (the chosen mode no longer resets on `install`/`update`); unmapped wallpapers fall back to `ZEKniri-preset` / `colors.css`; cava is UTF-8-safe and uses a temp config; the reload stamp is user-scoped; waybar/noctalia declare their package dependencies.
- Optional `ZEKlive` install option: bundles `ZEK-blv` / `ZEK-danmaku` / `bilibili_live_stream` into `~/.local`.
- Preset and Noctalia-auto modes are independent: `ZEK-niri palette` (and the watcher) only apply the config mappings while waybar is in preset mode; `--force` overrides.
- `waybar_colors = <wallpaper> = <css>` mapping: per-wallpaper waybar colours, applied by `ZEK-niri palette`/the watcher (rewrites the stable `colors-active.css` entry and reloads waybar).
- `ZEK-niri watch` follows noctalia wallpaper changes and applies each wallpaper's palette; `watch install` sets up a systemd user service, niri autostarts it, and `ZEK-niri palette --wait` fixes the waybar click race.
- `ZEK-niri watch` follows noctalia wallpaper changes and applies each wallpaper's palette; auto-started from niri and triggered from the waybar wallpaper module.

## [1.0.0]

- Fix: `ZEK-niri.conf` is read from the install tree by both the engine and shell helpers (single source of truth); a stale `~/.config/ZEKniri/ZEK-niri.conf` no longer shadows it.
- Per-wallpaper palettes: `wallpaper_palette = <壁纸> = <配色>` mapping with a `ZEK-niri palette` command that applies noctalia's current wallpaper palette.
- First run self-installs the CLI: `~/.local/bin/<CLI_CMD>` symlink plus idempotent PATH registration (fish/zsh/bash), so `ZEK-niri` works in the next terminal.
- Runtime config `ZEK-niri.conf` (language prompt, wallpaper dir + preset palette, log path, noctalia picker) with a `show-config` command; wallpaper and preset paths accept comma-separated lists.
- First release: atomic config deployment with `__custom__` preservation, snapshots,
  a health check, and an interactive panel.
