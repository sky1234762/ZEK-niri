# Runtime configuration — `ZEK-niri.conf`

Engine-level settings, separate from the per-app manifest system. Flat
`key = value` lines, `#` full-line comments, blank lines ignored, values support
`~` and `$HOME`. **Single source of truth: the repo/install-root `ZEK-niri.conf`.**
The engine and the deployed shell helpers both read it — the shell locates it
through the `~/.local/bin/<CLI_CMD>` symlink.

A copy at `~/.config/<PROJECT_NAME>/ZEK-niri.conf` is seeded on install only as a
fallback for helpers that cannot find the install tree; it is never layered into
the engine, so a stale copy cannot shadow the real file. Source: `zekniri/config.py`.

## Keys

| Key | Default | Meaning |
|---|---|---|
| `ask_language_each_start` | `false` | prompt for language every launch, not just first run |
| `wallpaper_dir` | empty → `<Pictures>/wallpaper` | comma-separated destination dirs; wallpapers are mirrored into each |
| `preset_palette` | `~/.config/noctalia/palettes/ZEKniri-preset.json` | comma-separated preset palette files; stems are the noctalia custom-palette names |
| `wallpaper_palette` | `[]` | repeatable `wallpaper = palette` pairs; `ZEK-niri palette` applies the match |
| `log_path` | empty → `~/.local/state/ZEKniri/install.log` | rolling log destination |
| `noctalia_scheme_source` | `wallpaper` | noctalia color-picker source used by `toggle-colors.sh` |
| `noctalia_scheme_name` | `soft` | noctalia scheme name used by `toggle-colors.sh` |

## Consumers

- `ask_language_each_start` → `tui.select_language()`
- `wallpaper_dir` → `deploy/assets.wallpaper_destination()` (falls back to `get_pics_dir()/wallpaper` when empty)
- `preset_palette` (and `.preset_palette_name`) → deploy preset check, `ZEK-niri show-config`
- `wallpaper_palette` → `zekniri/palette.py` (`palette_for()`, `ZEK-niri palette`)
- `log_path` → `core.init_logger()`
- `noctalia_scheme_source` / `noctalia_scheme_name` → `configs/waybar/scripts/toggle-colors.sh`, which reads `~/.config/ZEKniri/ZEK-niri.conf` directly (bash defaults when absent)

`ZEK-niri show-config` prints the resolved values with paths already expanded.

## Multiple paths

`wallpaper_dir` and `preset_palette` both accept comma- or semicolon-separated
lists. Wallpapers are mirrored into every destination; every preset is checked,
and `preset_palette_name` / `preset_palette_names` expose the file stems (noctalia
uses the first, since it takes a single custom palette). Multiple wallpaper or
palette *files* in one directory are always deployed in full.

## Per-wallpaper palettes

`wallpaper_palette` maps a wallpaper to a palette, one pair per line (repeatable):

    wallpaper_palette = ~/图片/wallpaper/foo.jpg = ~/.config/noctalia/palettes/foo.json

`ZEK-niri palette` reads noctalia's current wallpaper (`[wallpaper.last].path`,
then `default`, then `monitors.*`, from `~/.local/state/noctalia/settings.toml`),
resolves the mapped palette (exact path first, then filename), installs it into
noctalia's palettes dir if it lives elsewhere, and runs
`noctalia msg color-scheme-set custom <stem>`. Pass a wallpaper path to override,
or `ZEK-niri palette list` to print the map. An unmapped wallpaper is reported and
exits non-zero. Noctalia has no wallpaper-change hook, so bind this command
(keybind / waybar) to run after switching wallpaper.
