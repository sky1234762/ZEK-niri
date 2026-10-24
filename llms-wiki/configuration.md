# Runtime configuration — `ZEK-niri.conf`

Engine-level settings, separate from the per-app manifest system. Flat
`key = value` lines, `#` full-line comments, blank lines ignored, values support
`~` and `$HOME`. **Two layers:** the install-tree `ZEK-niri.conf` ships defaults;
the copy at `~/.config/<PROJECT_NAME>/ZEK-niri.conf` — the one users edit —
overrides same-named keys (list keys are replaced, not appended). The engine and
the deployed shell helpers both apply the same order; the shell reads the user
copy first, then locates the install tree through the `~/.local/bin/<CLI_CMD>`
symlink. The user copy is seeded from the install tree on install but never
overwritten, so edits there stick. Source: `zekniri/config.py`.

## Keys

| Key | Default | Meaning |
|---|---|---|
| `ask_language_each_start` | `false` | prompt for language every launch, not just first run |
| `preset_palette` | first mapped palette | repeatable: `wallpaper file = palette file` pair, or a bare palette path (global fallback). The wallpaper deploy dir is derived from the paired files |
| `wallpaper_palette` | `[]` | alias for the pair form of `preset_palette` |
| `log_path` | empty → `~/.local/state/ZEKniri/install.log` | rolling log destination |
| `noctalia_scheme_source` | `wallpaper` | noctalia color-picker source used by `toggle-colors.sh` |
| `noctalia_scheme_name` | `soft` | noctalia scheme name used by `toggle-colors.sh` |

## Consumers

- `ask_language_each_start` → `tui.select_language()`
- `preset_palette` / `wallpaper_palette` → `config.wallpaper_palettes`; derived `wallpaper_dirs` → `deploy/assets.wallpaper_destinations()` (falls back to `get_pics_dir()/wallpaper`)
- `.palette_for()` → `zekniri/palette.py` (`ZEK-niri palette`, `list_mappings`)
- `log_path` → `core.init_logger()`
- `noctalia_scheme_source` / `noctalia_scheme_name` → `configs/waybar/scripts/toggle-colors.sh`, which reads the user copy first (bash defaults when absent)

`ZEK-niri show-config` prints the resolved values with paths already expanded.

## Per-wallpaper palettes

`preset_palette` pairs each wallpaper **file** with its palette, one per line:

    preset_palette = ~/图片/wallpaper/foo.jpg = ~/.config/noctalia/palettes/foo.json

`wallpaper_palette` is an alias for the same pair form. A bare
`preset_palette = <palette file>` (no `=`) is a global fallback used when a
wallpaper has no pair; `preset_palette_name` / `preset_palette_names` expose the
file stems.

The wallpaper **deploy** directory is derived from the parent dirs of the paired
wallpaper files — there is no separate `wallpaper_dir`. With no pairs it falls
back to `<Pictures>/wallpaper`, resolved from `$XDG_PICTURES_DIR` →
`~/.config/user-dirs.dirs` → `xdg-user-dir PICTURES` → `~/Pictures`, so
localised names like `~/图片` work without `xdg-user-dir`. Multiple wallpaper
files in a directory are always deployed in full.

After copying, `deploy_assets()` also rewrites Noctalia's `[wallpaper] directory`
in `~/.local/state/noctalia/settings.toml` when it is empty or still the
Pictures root, so the pack shows up directly in Noctalia's wallpaper picker. A
custom folder is left untouched.

`ZEK-niri palette` reads noctalia's current wallpaper (`[wallpaper.last].path`,
then `default`, then `monitors.*`, from `~/.local/state/noctalia/settings.toml`),
resolves the paired palette (exact path first, then filename), installs it into
noctalia's palettes dir if it lives elsewhere, and runs
`noctalia msg color-scheme-set custom <stem>`. Only applies while waybar is in
preset mode (the stable `colors-active.css` entry does not import
`colors-noctalia.css`), so preset and Noctalia-auto modes stay independent;
`--force` overrides. Pass a wallpaper path to override, or `ZEK-niri palette
list` to print the map. An unmapped wallpaper falls back to the bare global
`preset_palette` when set, otherwise to the built-in `ZEKniri-preset`.
`toggle-colors.sh` uses the same mapping for its preset mode via `ZEK-niri
palette`, with the same `ZEKniri-preset` fallback. Noctalia has no
wallpaper-change hook, so bind this command to run after switching wallpaper.

## Preset mode colours

Preset mode always uses the static `colors.css` (the ZEKniri preset); waybar's
`@import` is switched only between `colors.css` and `colors-noctalia.css` by
`toggle-colors.sh`. The per-wallpaper `waybar_colors` mapping was removed, so
`ZEK-niri palette` and the watcher change Noctalia's palette without touching
waybar's mode.

## Watcher & waybar

`ZEK-niri watch [seconds]` polls noctalia's `[wallpaper.last].path` and applies
the paired palette whenever the wallpaper changes. It is a no-op while waybar's
`colors-active.css` imports `colors-noctalia.css` (Noctalia-auto mode), takes no
single-instance lock, and only one watcher runs at a time (its own lock).

Start it once as a systemd user service (persists across sessions):

    ZEKniri watch install     # write + enable + start ~/.config/systemd/user/zekniri-watch.service
    ZEKniri watch remove

`configs/niri/cfg/autostart.kdl` also starts it at login as a fallback:

    spawn-at-startup "sh" "-c" "exec \"$HOME/.local/bin/ZEK-niri\" watch"

The shipped waybar wallpaper module triggers it right after a switch. `--wait`
keeps polling until noctalia's async wallpaper IPC lands, so the *new*
wallpaper's palette is applied:

    "on-click-right": "noctalia msg wallpaper-random; ZEK-niri palette --wait"
    "on-click-middle": "noctalia msg wallpaper-next; ZEK-niri palette --wait"
