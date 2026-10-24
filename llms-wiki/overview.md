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
- **update** — refresh the repo (`git pull`), then re-exec and deploy on the new
  code. Presets, if any, live in the repo, so a pull updates their source too.

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
