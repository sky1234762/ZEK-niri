"""Atomic swap deployment + Dunder preservation + manifest-declared snapshots.

``atomic_replace_item`` is the heart of the deploy: build the complete new
directory in a sibling temp path, then swap it into place with a single rename.
Two preserve mechanisms live here and stay deliberately separate:

* the Dunder ``__custom__`` walk (magic filename, any depth), and
* the manifest ``preserve`` snapshot (files referenced by name, e.g. a file
  that another config includes by exact path).

Keeping them separate is intentional: one is "the user edits anything and it
survives", the other is "this exact filename is referenced and must keep its
name". Merging them would force renaming referenced files into magic names.
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional

from zekniri.core import get_env, log_msg, register_temp_path, remove_path
from zekniri.i18n import msg


def _deploy_ignore_factory(root_src: Path, exclude: Optional[List[str]] = None):
    """copytree ignore: drop repo-only entries and explicitly excluded paths.

    ``exclude`` holds repo-relative paths (e.g. a manifest ``state`` file) that
    are deployed elsewhere and must not also land in ~/.config.
    """
    ex = {e for e in (exclude or []) if e}

    def _ignore(src_dir, names):
        skip = {n for n in names if n in ("__pycache__", ".module.toml")}
        if ex:
            cur = Path(src_dir)
            for name in names:
                if name in skip:
                    continue
                try:
                    rel = (cur / name).relative_to(root_src).as_posix()
                except ValueError:
                    rel = name
                if rel in ex:
                    skip.add(name)
        return skip

    return _ignore


def atomic_replace_item(
    src: Path,
    dest: Path,
    preserved_log: Optional[List[str]] = None,
    test_mode: bool = False,
    preserve: Optional[List[str]] = None,
    preserve_custom: bool = True,
    exclude: Optional[List[str]] = None,
) -> bool:
    """Atomic swap with Dunder protocol preservation.

    ``preserve`` injects manifest-declared files into the temp directory
    *before* the rename, so the swapped-in directory is already complete — no
    post-rename restore window for file watchers to catch a half state.
    """
    pid = os.getpid()
    dest_parent = dest.parent
    home = get_env().home

    if src.is_file():
        tmp_file = dest.with_name(f"{dest.name}.new.{pid}")
        register_temp_path(tmp_file)
        old_dest = None
        try:
            dest_parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp_file)
            if dest.exists() or dest.is_symlink():
                old_dest = dest.with_name(f"{dest.name}.old.{pid}")
                dest.rename(old_dest)
                tmp_file.rename(dest)
                remove_path(old_dest)
            else:
                tmp_file.rename(dest)
            return True
        except Exception as e:
            remove_path(tmp_file)
            if old_dest is not None and old_dest.exists():
                try:
                    old_dest.rename(dest)
                except Exception:
                    pass
            log_msg("ERROR", f"Atomic replace failed for {dest}: {e}")
            return False

    tmp_new = dest.with_name(f"{dest.name}.new.{pid}")
    register_temp_path(tmp_new)

    try:
        dest_parent.mkdir(parents=True, exist_ok=True)
        if tmp_new.exists() or tmp_new.is_symlink():
            remove_path(tmp_new)
        shutil.copytree(src, tmp_new, symlinks=True, ignore=_deploy_ignore_factory(src, exclude))

        # Dunder protocol: inherit *__custom__* files and directories from dest.
        if preserve_custom and dest.is_dir():
            preserve_entries = []
            for root, dirs, files in os.walk(dest):
                custom_dirs = [d for d in dirs if "__custom__" in d]
                for d in custom_dirs:
                    dirs.remove(d)
                    preserve_entries.append(("dir", root, d))
                for f in files:
                    if "__custom__" in f:
                        preserve_entries.append(("file", root, f))

            for entry_type, root, name in preserve_entries:
                rel_path = Path(root).relative_to(dest) / name
                src_item = dest / rel_path
                target_item = tmp_new / rel_path
                target_item.parent.mkdir(parents=True, exist_ok=True)
                if entry_type == "dir":
                    shutil.rmtree(target_item, ignore_errors=True)
                    shutil.copytree(src_item, target_item, symlinks=True)
                elif src_item.is_symlink():
                    target_item.unlink(missing_ok=True)
                    target_item.symlink_to(os.readlink(src_item))
                else:
                    shutil.copy2(src_item, target_item)
                rel_display = str(dest.relative_to(get_env().config_dir) / rel_path)
                suffix = "/" if entry_type == "dir" else ""
                print(msg("log_keep_custom_dir" if entry_type == "dir" else "log_keep_custom_file", rel_display + suffix))
                if preserved_log is not None:
                    preserved_log.append(f"~/.config/{rel_display}{suffix}")

        # Manifest-declared preserve, injected before the swap. Symlinks are
        # kept as links so runtime link state survives a deploy; directories
        # are kept wholesale (repo-metadata dirs stay user-owned).
        if preserve and dest.is_dir():
            for rel in preserve:
                src_p = dest / rel
                tgt_p = tmp_new / rel
                tgt_p.parent.mkdir(parents=True, exist_ok=True)
                if src_p.is_symlink():
                    tgt_p.unlink(missing_ok=True)
                    tgt_p.symlink_to(os.readlink(src_p))
                elif src_p.is_dir():
                    shutil.rmtree(tgt_p, ignore_errors=True)
                    shutil.copytree(src_p, tgt_p, symlinks=True)
                elif src_p.is_file():
                    shutil.copy2(src_p, tgt_p)
                else:
                    continue
                print(msg("log_keep_preserved_file", dest.name, rel))
                if preserved_log is not None:
                    preserved_log.append(f"~/.config/{dest.name}/{rel}")

        if dest.exists() or dest.is_symlink():
            old_dest = dest.with_name(f"{dest.name}.old.{pid}")
            dest.rename(old_dest)
            try:
                tmp_new.rename(dest)
                remove_path(old_dest)
            except Exception:
                old_dest.rename(dest)
                raise
            return True
        tmp_new.rename(dest)
        return True
    except Exception as e:
        remove_path(tmp_new)
        log_msg("ERROR", f"Atomic replace failed for directory {dest}: {e}")
        return False
