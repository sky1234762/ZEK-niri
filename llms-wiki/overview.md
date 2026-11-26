# Overview — the model

> zekniri deploys selected configs atomically. The core tension: strong curated
> defaults that work out of the box, but a user's edits must never be lost.
> Layering resolves it.

## The mental model

```
default config  ←  __custom__ files  ←  manifest preserve
(lowest)           (user, always wins)   (fixed names kept)
```

Strictly there are three preserve/overlay layers, but the two the user reasons
about are:

1. **Configs** — everything under `configs/<app>/`, deployed to `~/.config/<app>/`.
2. **`__custom__`** — any file or directory whose name contains `__custom__`.
   It is copied forward on every deploy, so edits survive updates.
3. **`preserve`** — a manifest list of exact filenames kept across deploys
   (for files that cannot be renamed because something includes them by path).

## Two orthogonal axes

An app has two independent properties. They are decoupled on purpose: adding
config to an optional app must **not** graduate it to required.

| Axis | Source | Meaning |
|---|---|---|
| A: has config | a `configs/<app>/` dir exists | install deploys it |
| B: is optional | listed in `configs/.optional-apps.toml` | shown in the apps menu, package marked optional |

`discover_deployable_apps()` scans directories. `discover_optional_apps()` reads
the toml. `discover_manifest_apps()` merges both.

## The two verbs

- **install** — atomic reconcile from repo → `~/.config`, then imperative
  side-effects (placeholder render, assets). `install full` also checks deps.
  Install wallpapers first, then tries to enable `waybar.service` (systemd user)
  and install/restart `zekniri-watch.service`; optional service failures warn
  but do not abort the install. Waybar's service is reset from a failed
  `start-limit`, restarted, and verified active. Niri startup has a fallback to
  run Waybar/watcher directly when systemd is unavailable. Noctalia's native
  `[bar.*] enabled` is turned off only after Waybar is verified running; a
  Noctalia-only install keeps the native bar on. The state seed keeps the
  native bar enabled and ships empty wallpaper paths instead of author paths.
  After deployment it shows a TUI selector with every supported resolution/refresh
  combination per Niri output and writes the chosen modes to `~/.config/niri/config.kdl`.
- **update** — refresh the repo (`git pull`), then re-exec and deploy on the new
  code. Presets, if any, live in the repo, so a pull updates their source too.

## Install execution and compatibility

`cli.py` retains the existing menus, translated output, commands and completion UI.
`workflow.py` owns the immutable installation plan and the shared asset/service
execution used by installation and upgrades. Dependency failures stop before
configuration deployment; optional wallpaper/service failures retain the current
warning-and-continue policy. Native-bar selection still depends on verified Waybar
startup. `tests/fixtures/install_workflow.json` records English/Chinese workflow
output and operation order for 20 scenarios from before the refactor.

The Bash bootstrap validates all runtime modules before execution. Rebuilding a
cache clones and validates into a temporary sibling first, retains the previous
checkout under `.zekniri-previous.*`, and restores it if replacement fails. A failed
clone never deletes the existing cache. Package installation invalidates dependency
query caches so subsequent checks see newly installed packages.

Noctalia configuration deployment does not install or manage third-party plugins;
separately installed plugins remain untouched.

## Physical isolation

Repo source and `~/.config` are separate. Files reach `~/.config` only through
`atomic_replace_item`; symlinks from the repo into `~/.config` are forbidden.
Symlinks *inside* `~/.config` (runtime state) are fine and preserved.

Tool-owned data lives under `~/.config/<PROJECT_NAME>/` (snapshots) and
`~/.local/state/<PROJECT_NAME>/` (lock, log). Nothing of zekniri's own goes into
`~/.config/<app>/`; `__custom__` is part of the app's config, not zekniri metadata.

The standalone `ZEK-menu` is a GTK 3 / gtk-layer-shell overlay. The launcher is
installed to `~/.local/bin/ZEK-menu`, its Python package to
`~/.local/share/ZEKniri/zekniri/`, and its config to
`~/.config/ZEKniri/ZEKniri-menu.conf` (seeded once, never overwritten). It does
not depend on Noctalia and uses the `Ctrl+MouseMiddle` Niri binding to open.
`memo_path` is repeatable; each entry renders as `打开 <filename>` (text files
open in the terminal editor, directories via `xdg-open`).
