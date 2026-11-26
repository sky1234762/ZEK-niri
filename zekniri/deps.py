"""Dependency detection, install, and the optional-apps menu.

Arch-oriented (pacman). On a host without pacman the checks degrade to "no
missing deps" instead of failing.
"""

import os
import shutil
from typing import List, Optional

from zekniri.constants import CORE_DEPS
from zekniri.core import log_msg, timed_run
from zekniri.deploy.manifest import discover_manifest_apps
from zekniri.i18n import msg
from zekniri.tui import CheckboxEntry, CheckboxList, press_any_key

_PACMAN_INSTALLED_CACHE: Optional[set] = None


def _get_pacman_installed() -> set:
    global _PACMAN_INSTALLED_CACHE
    if _PACMAN_INSTALLED_CACHE is not None:
        return _PACMAN_INSTALLED_CACHE
    if not shutil.which("pacman"):
        _PACMAN_INSTALLED_CACHE = set()
        return _PACMAN_INSTALLED_CACHE
    res = timed_run(["pacman", "-Qq"], 30, capture_output=True, text=True, check=False,
                    env={**os.environ, "LC_ALL": "C"})
    _PACMAN_INSTALLED_CACHE = set(res.stdout.split()) if res is not None and res.returncode == 0 else set()
    return _PACMAN_INSTALLED_CACHE


def is_dep_installed(name: str) -> bool:
    """Best-effort check: pacman package, then a binary of the same name."""
    if not name:
        return True
    if name in _get_pacman_installed():
        return True
    if shutil.which(name):
        return True
    return False


def _aggregate_required_packages() -> List[str]:
    pkgs: List[str] = list(CORE_DEPS)
    for _name, m in discover_manifest_apps():
        if m.is_optional:
            continue
        pkgs.extend(m.packages_repo)
    # De-duplicate, preserve order.
    seen = set()
    out = []
    for p in pkgs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def get_missing_deps() -> List[str]:
    """Required packages (core + required manifests) not installed."""
    try:
        return [p for p in _aggregate_required_packages() if not is_dep_installed(p)]
    except Exception:
        return []


def install_selected_deps(packages: List[str]) -> bool:
    """Install packages via pacman + optional AUR helper. Best-effort."""
    if not packages:
        print(msg("deps_all_installed"))
        return True
    if not shutil.which("pacman"):
        print(msg("distro_unsupported"))
        return False
    print(msg("deps_installing", " ".join(packages)))
    res = timed_run(["sudo", "pacman", "-S", "--needed", "--noconfirm", *packages],
                    timeout=1800, check=False)
    ok = res is not None and res.returncode == 0
    if ok:
        global _PACMAN_INSTALLED_CACHE
        _PACMAN_INSTALLED_CACHE = None
        print(msg("deps_installed"))
    else:
        print(msg("deps_failed"))
    log_msg("INFO" if ok else "WARN", f"pacman install {packages}: {'ok' if ok else 'failed'}")
    return ok


def run_dep_menu_loop() -> None:
    """Interactive core-dependency checklist."""
    if not shutil.which("pacman"):
        print(msg("distro_unsupported_hint"))
        return
    missing = get_missing_deps()
    if not missing:
        print(msg("deps_all_installed"))
        return
    entries = [CheckboxEntry(key=f"dep_{p}", label=p, checked=True) for p in missing]
    chosen = CheckboxList("deps_title", entries, hint_key="selective_hint").run()
    if not chosen:
        return
    install_selected_deps([k.removeprefix("dep_") for k in chosen])
    press_any_key()


def run_optional_apps_menu_loop() -> None:
    """Interactive optional-apps checklist, grouped by category label."""
    optional = [m for _n, m in discover_manifest_apps() if m.is_optional]
    if not optional:
        print(msg("apps_none"))
        return
    entries: List[CheckboxEntry] = []
    last_cat = None
    for m in optional:
        cat = m.category or "other"
        if cat != last_cat:
            last_cat = cat
            entries.append(CheckboxEntry(key=f"hdr_{cat}", label=cat, is_separator=True))
        installed = is_dep_installed(m.detect)
        status = msg("dep_installed") if installed else ""
        label = f"{m.label} {status}".strip()
        entries.append(CheckboxEntry(key=f"app_{m.name}", label=label, checked=not installed))
    chosen = CheckboxList("apps_title", entries, hint_key="selective_hint").run()
    if not chosen:
        return
    chosen_pkgs: List[str] = []
    by_name = {m.name: m for m in optional}
    for key in chosen:
        if not key.startswith("app_"):
            continue
        m = by_name.get(key.removeprefix("app_"))
        if m is None:
            continue
        chosen_pkgs.extend(m.packages_repo)
        chosen_pkgs.extend(m.packages_aur)
    if chosen_pkgs:
        install_selected_deps(chosen_pkgs)
    press_any_key()
