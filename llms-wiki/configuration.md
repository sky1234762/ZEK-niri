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
| `waybar_colors` | `[]` | repeatable `wallpaper file = waybar css` pair; switches waybar's `@import` per wallpaper |
| `log_path` | empty → `~/.local/state/ZEKniri/install.log` | rolling log destination |
| `noctalia_scheme_source` | `wallpaper` | noctalia color-picker source used by `toggle-colors.sh` |
| `noctalia_scheme_name` | `soft` | noctalia scheme name used by `toggle-colors.sh` |

## Consumers

- `ask_language_each_start` → `tui.select_language()`
- `preset_palette` / `wallpaper_palette` → `config.wallpaper_palettes`; derived `wallpaper_dirs` → `deploy/assets.wallpaper_destinations()` (falls back to `get_pics_dir()/wallpaper`)
- `.palette_for()` → `zekniri/palette.py` (`ZEK-niri palette`, `list_mappings`)
- `.waybar_colors_for()` → `zekniri/palette.py` (`apply_waybar_colors`, called by `ZEK-niri palette`)
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
back to `<Pictures>/wallpaper`. Multiple wallpaper files in a directory are
always deployed in full.

`ZEK-niri palette` reads noctalia's current wallpaper (`[wallpaper.last].path`,
then `default`, then `monitors.*`, from `~/.local/state/noctalia/settings.toml`),
resolves the paired palette (exact path first, then filename), installs it into
noctalia's palettes dir if it lives elsewhere, and runs
`noctalia msg color-scheme-set custom <stem>`. Only applies while waybar is in
preset mode (`style.css` does not import `colors-noctalia.css`), so preset and
Noctalia-auto modes stay independent; `--force` overrides. Pass a wallpaper path
to override, or `ZEK-niri palette list` to print the map. An unmapped wallpaper is
reported and exits non-zero, unless a bare global `preset_palette` is set (then
that is used). `toggle-colors.sh` uses the same mapping for its preset mode via
`ZEK-niri palette`; it no longer forces the first mapping when nothing matches. Noctalia has no
wallpaper-change hook, so bind this command to run after switching wallpaper.

## Waybar colours per wallpaper

`waybar_colors` pairs a wallpaper with a waybar CSS file (repeatable):

    waybar_colors = ~/图片/wallpaper/foo.jpg = ~/.config/waybar/colors/foo.css

When the wallpaper changes, `ZEK-niri palette` (and the watcher) rewrites waybar's
`style.css` `@import` to that CSS — relative to `~/.config/waybar/` when possible,
otherwise the external file is copied to `~/.config/waybar/colors-wallpaper.css` —
and reloads waybar. A wallpaper without a mapping keeps the preset/auto mode
chosen by `toggle-colors.sh`.

## Watcher & waybar

`ZEK-niri watch [seconds]` polls noctalia's `[wallpaper.last].path` and applies
the paired palette whenever the wallpaper changes. It is a no-op while waybar's
`style.css` imports `colors-noctalia.css` (Noctalia-auto mode), takes no
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
