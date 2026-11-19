"""Configuration snapshots: create, list, delete, and roll back.

A snapshot is a copy of every deployed app under
``~/.config/<PROJECT_NAME>/backups/snapshot_<timestamp>``. Managed snapshots are
pruned to ``MAX_SNAPSHOTS``, oldest first, with the snapshot currently being
protected never removed.
"""

import datetime
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from zekniri.constants import MAX_SNAPSHOTS, PROJECT_NAME, Colors
from zekniri.core import copy_path, get_env, log_msg, register_temp_path
from zekniri.i18n import msg

_MANAGED_SNAPSHOT_RE = re.compile(
    r"^(?:snapshot|pre_rollback)_\d{8}_\d{6}(?:_\d+){0,2}$"
)


def get_backup_base_dir() -> Path:
    return get_env().config_dir / PROJECT_NAME / "backups"


def get_all_backups() -> List[Path]:
    base = get_backup_base_dir()
    if not base.is_dir():
        return []
    snaps = [
        d for d in base.iterdir()
        if d.is_dir() and not d.is_symlink() and _MANAGED_SNAPSHOT_RE.fullmatch(d.name)
    ]
    snaps.sort(key=lambda p: p.name)
    return snaps


def _prune_old_snapshots(base_dir: Path, protected_snapshot: Optional[Path] = None) -> None:
    if not base_dir.is_dir():
        return
    snapshots = [
        d for d in base_dir.iterdir()
        if d.is_dir() and not d.is_symlink() and _MANAGED_SNAPSHOT_RE.fullmatch(d.name)
    ]
    if len(snapshots) <= MAX_SNAPSHOTS:
        return
    snapshots.sort(key=lambda p: p.name)
    excess = len(snapshots) - MAX_SNAPSHOTS
    for old in snapshots:
        if old == protected_snapshot:
            continue
        shutil.rmtree(old, ignore_errors=True)
        log_msg("INFO", f"Pruned old snapshot {old.name}")
        excess -= 1
        if not excess:
            break


def backup_configs(
    note: str = "",
    interactive: bool = True,
    protected_snapshot: Optional[Path] = None,
) -> Optional[Path]:
    """Create a snapshot of all deployed app configs."""
    from zekniri.deploy import discover_config_items

    env = get_env()
    base_dir = get_backup_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    print(msg("backing_up"))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = base_dir / f"snapshot_{timestamp}"
    suffix = 1
    while backup_dir.exists() or backup_dir.is_symlink():
        backup_dir = base_dir / f"snapshot_{timestamp}_{suffix}"
        suffix += 1

    tmp_dir = Path(tempfile.mkdtemp(prefix=".snapshot.", dir=base_dir))
    register_temp_path(tmp_dir)

    for item in discover_config_items():
        cfg_path = env.config_dir / item
        if cfg_path.exists() or cfg_path.is_symlink():
            copy_path(cfg_path, tmp_dir / item)
            if interactive:
                print(msg("log_backup_item", item))

    if note.strip():
        (tmp_dir / "note.txt").write_text(note.strip(), encoding="utf-8")

    tmp_dir.rename(backup_dir)
    _prune_old_snapshots(base_dir, protected_snapshot=backup_dir)
    print(msg("backup_done", backup_dir.name))
    log_msg("INFO", f"Snapshot created: {backup_dir}")
    return backup_dir


def _resolve_snapshot(target: str) -> Optional[Path]:
    """Resolve a snapshot by 1-based index or exact name. Empty = latest."""
    snaps = get_all_backups()
    if not snaps:
        print(msg("no_snapshots"))
        return None
    if not target:
        return snaps[-1]
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(snaps):
            return snaps[idx - 1]
        print(msg("snapshot_index_out_of_range", target))
        return None
    for s in snaps:
        if s.name == target or s.name == f"snapshot_{target}":
            return s
    print(msg("snapshot_not_found", target))
    return None


def list_backups() -> List[Path]:
    snaps = get_all_backups()
    print(msg("snapshot_list_title"))
    if not snaps:
        print(f"  {Colors.DIM}{msg('no_snapshots')}{Colors.RESET}")
        return []
    for i, snap in enumerate(snaps, 1):
        note = ""
        note_file = snap / "note.txt"
        if note_file.is_file():
            try:
                note = note_file.read_text(encoding="utf-8").strip().replace("\n", " ")
            except OSError:
                note = ""
        label = f"  {i:>2}. {snap.name}"
        if note:
            label += f"  {Colors.DIM}{note}{Colors.RESET}"
        print(label)
    return snaps


def rollback_configs(target: str = "") -> bool:
    """Restore a snapshot into ~/.config, snapshotting current state first."""
    env = get_env()
    snap = _resolve_snapshot(target)
    if snap is None:
        return False

    protect = backup_configs(note=f"pre_rollback:{snap.name}", interactive=False)
    print(msg("rollback_restoring", snap.name))

    from zekniri.deploy import discover_config_items
    from zekniri.deploy.atomic import atomic_replace_item
    from zekniri.deploy.templates import _phase_render_templates

    ok = True
    for item in discover_config_items():
        snap_item = snap / item
        if not snap_item.exists():
            continue
        if not atomic_replace_item(snap_item, env.config_dir / item):
            ok = False
        else:
            _phase_render_templates(only_app=item)
    log_msg("INFO", f"Rolled back to {snap.name} (pre-rollback: {protect})")
    print(msg("rollback_done" if ok else "rollback_partial"))
    return ok


def delete_backup(target: str = "") -> bool:
    snap = _resolve_snapshot(target)
    if snap is None:
        return False
    if not sys.stdin.isatty():
        shutil.rmtree(snap, ignore_errors=True)
        print(msg("snapshot_deleted", snap.name))
        return True
    from zekniri.tui import prompt_confirm
    if not prompt_confirm("snapshot_delete_confirm", "n", snap.name):
        print(msg("snapshot_delete_cancelled"))
        return False
    shutil.rmtree(snap, ignore_errors=True)
    print(msg("snapshot_deleted", snap.name))
    log_msg("INFO", f"Snapshot deleted: {snap}")
    return True
