"""Self-describing app manifests (``.module.toml`` + ``.optional-apps.toml``).

A ``configs/<app>/`` directory is the first-class unit. By convention it is
self-describing: the directory name drives every default, and a sibling
``.module.toml`` overrides a default only when the app is exceptional.

Two independent axes:
  * **has config** — a ``configs/<app>/`` dir exists → deployed by install.
  * **is optional** — listed in ``.optional-apps.toml`` → offered in the apps
    menu and marked optional.

They are orthogonal on purpose: adding config to an optional app must not
"graduate" it into a required one.

Pure stdlib (``tomllib``, 3.11+). No app names are hardcoded.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from zekniri.core import get_env

_MANIFEST_NAME = ".module.toml"
_OPTIONAL_APPS_NAME = ".optional-apps.toml"


@dataclass(frozen=True)
class ModuleManifest:
    """Resolved manifest for one app. Every field has a concrete value."""

    name: str
    packages_repo: List[str]
    packages_aur: List[str]
    packages_flatpak: List[str]
    preserve: List[str]
    chmod: List[str]
    label: str
    category: str
    detect: str
    is_deployable: bool
    is_optional: bool = False
    # Files deployed to <state_home>/<app>/ instead of ~/.config/<app>/.
    state: List[str] = field(default_factory=list)


def _manifest_path(app_src: Path) -> Path:
    """Locate the manifest for a dir-type or file-type app source."""
    if app_src.is_dir():
        return app_src / _MANIFEST_NAME
    return app_src.parent / (app_src.name + _MANIFEST_NAME)


def _is_deployable(app_src: Path) -> bool:
    """An app is deployable iff it ships real config (more than a manifest)."""
    if app_src.is_file():
        return True
    try:
        for entry in app_src.iterdir():
            if entry.name in ("__pycache__", _MANIFEST_NAME):
                continue
            return True
    except OSError:
        pass
    return False


def load_manifest(app_src: Path, is_optional: bool = False) -> ModuleManifest:
    """Load a manifest for an app source; defaults are derived from the name."""
    name = app_src.name
    mpath = _manifest_path(app_src)
    data = {}
    if mpath.is_file():
        with open(mpath, "rb") as f:
            data = tomllib.load(f)

    packages = data.get("packages", {}) or {}
    pkg_repo = packages.get("repo")
    if pkg_repo is None:
        pkg_repo = [name]
    deploy = bool(packages.get("deploy", True))

    return ModuleManifest(
        name=name,
        packages_repo=list(pkg_repo),
        packages_aur=list(packages.get("aur", [])),
        packages_flatpak=list(packages.get("flatpak", [])),
        preserve=list(packages.get("preserve", [])),
        chmod=list(packages.get("chmod", [])),
        state=list(packages.get("state", [])),
        label=packages.get("label", name),
        category=packages.get("category", ""),
        detect=packages.get("detect", name),
        is_deployable=_is_deployable(app_src) and deploy,
        is_optional=is_optional,
    )


def _optional_toml_path() -> Path:
    return get_env().configs_src / _OPTIONAL_APPS_NAME


def load_optional_apps() -> Dict[str, dict]:
    """Return ``{name: entry}`` from ``.optional-apps.toml`` (empty if absent)."""
    path = _optional_toml_path()
    if not path.is_file():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    result: Dict[str, dict] = {}
    for entry in data.get("app", []) or []:
        name = entry.get("name")
        if name:
            result[name] = entry
    return result


def _manifest_from_optional(name: str, entry: dict) -> ModuleManifest:
    return ModuleManifest(
        name=name,
        packages_repo=list(entry.get("repo", [name])),
        packages_aur=list(entry.get("aur", [])),
        packages_flatpak=list(entry.get("flatpak", [])),
        preserve=[],
        chmod=[],
        label=entry.get("label", name),
        category=entry.get("category", ""),
        detect=entry.get("detect", name),
        is_deployable=False,
        is_optional=True,
    )


def _merge_optional_entry(m: ModuleManifest, entry: dict) -> ModuleManifest:
    """Overlay the optional-axis entry onto a dual app (config dir + optional)."""
    return ModuleManifest(
        name=m.name,
        packages_repo=list(entry.get("repo", m.packages_repo)),
        packages_aur=list(entry.get("aur", m.packages_aur)),
        packages_flatpak=list(entry.get("flatpak", m.packages_flatpak)),
        preserve=m.preserve,
        chmod=m.chmod,
        state=m.state,
        label=entry.get("label", m.label),
        category=entry.get("category", m.category),
        detect=entry.get("detect", m.detect),
        is_deployable=m.is_deployable,
        is_optional=True,
    )


def _app_src(app_name: str) -> Path:
    return get_env().configs_src / app_name


def load_manifest_for(app_name: str) -> ModuleManifest:
    """Convenience: load a manifest by app name (configs/<name> path)."""
    return load_manifest(_app_src(app_name))


def _is_configs_metadata(name: str) -> bool:
    # Hidden entries (.gitkeep, dotfiles) and manifests are repo metadata, not apps.
    return (
        name.startswith(".")
        or name == "__pycache__"
        or name == _OPTIONAL_APPS_NAME
        or name.endswith(".module.toml")
    )


_MANIFEST_CACHE: Optional[List[Tuple[str, ModuleManifest]]] = None


def discover_manifest_apps() -> List[Tuple[str, ModuleManifest]]:
    """Scan configs/ dirs + read .optional-apps.toml; merge both axes.

    Result is cached per process (manifest files cannot change under a running
    engine). Sorted by name for deterministic output.
    """
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    env = get_env()
    if not env.configs_src.is_dir():
        return []

    optional = load_optional_apps()
    apps: List[Tuple[str, ModuleManifest]] = []
    seen: set = set()

    for p in sorted(env.configs_src.iterdir(), key=lambda x: x.name):
        if _is_configs_metadata(p.name):
            continue
        try:
            m = load_manifest(p, is_optional=(p.name in optional))
            if p.name in optional:
                m = _merge_optional_entry(m, optional[p.name])
        except Exception:
            continue
        apps.append((p.name, m))
        seen.add(p.name)

    for name, entry in optional.items():
        if name in seen:
            continue
        apps.append((name, _manifest_from_optional(name, entry)))

    apps.sort(key=lambda x: x[0])
    _MANIFEST_CACHE = apps
    return apps


def discover_deployable_apps() -> List[str]:
    """Names of apps that ship real config (have a configs/<app>/ dir)."""
    return [name for name, m in discover_manifest_apps() if m.is_deployable]


def discover_optional_apps() -> List[str]:
    """Names of apps listed in .optional-apps.toml (axis B)."""
    return [name for name, m in discover_manifest_apps() if m.is_optional]
