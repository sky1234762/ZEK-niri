# Manifest Schema — `.module.toml` + `.optional-apps.toml`

> Two manifest files, all fields optional, no file = all defaults. The directory
> name drives every default. Source: `zekniri/deploy/manifest.py`.

## `.module.toml` (an app that has config)

`configs/<app>/.module.toml`. Only write it when a default must be overridden.
All fields live under `[packages]`:

| Field | Default | Purpose |
|---|---|---|
| `repo` | `[<dir name>]` | pacman package name(s) |
| `aur` | `[]` | AUR package name(s) |
| `flatpak` | `[]` | Flathub app IDs |
| `preserve` | `[]` | exact filenames kept across deploys |
| `chmod` | `[]` | globs (relative to app dir) set executable |
| `state` | `[]` | files deployed to `<state_home>/<app>/` instead of `~/.config` (no-clobber seed; e.g. noctalia `settings.toml`) |
| `deploy` | `true` | set `false` for a `configs/<app>/` directory that ships a bundled tool instead of `~/.config/<app>` dotfiles (e.g. `ZEKniri-menu`) |
| `label` | `<dir name>` | menu display name |
| `detect` | `<dir name>` | command name used to detect installation |

A file-type app uses a sidecar: `configs/prompt.toml` +
`configs/prompt.toml.module.toml`.

## `.optional-apps.toml` (optional software, no config)

One file at the configs root. Each `[[app]]` block:

| Field | Default | Purpose |
|---|---|---|
| `name` | required | app identifier |
| `repo` | `[<name>]` | pacman package(s); Flatpak-only apps must set `repo = []` |
| `aur` | `[]` | AUR package(s) |
| `flatpak` | `[]` | Flathub app IDs |
| `label` | `<name>` | display name |
| `category` | `""` | menu grouping key; block order = menu order |
| `detect` | `<name>` | command name used to detect installation |

Block order is menu order. An app in both files is one entry with
`is_deployable=True` and `is_optional=True`: optional-axis fields come from the
toml, config-axis fields (`preserve`, `chmod`, `state`) stay in the `.module.toml`.

## Runtime files and preservation

- `state` — repo-relative paths that are **excluded** from the `~/.config/<app>/`
  deploy and instead copied (once, never overwriting) to
  `<XDG_STATE_HOME>/<app>/<path>`. For app-owned runtime files that don't belong
  in `~/.config`, e.g. noctalia's `settings.toml` → `~/.local/state/noctalia/`.
- `preserve` — files already in the destination that must survive a deploy.

## Boundaries

Not in a manifest (it would grow into a mini-language): doctor checks,
post-install hooks, i18n keys. Those belong in `DOCTOR_CHECKS` / code /
`TRANSLATIONS`.
