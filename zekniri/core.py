"""Core runtime infrastructure: paths, single-instance lock, logging, temp-path
registry, path primitives, and version detection.

Nothing here knows about any particular app. The Environment object is the one
place that resolves where the source tree, the user config tree and the
transient state live.
"""

import atexit
import datetime
import fcntl
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from zekniri.constants import (
    ASSETS_DIR_NAME,
    CLI_CMD,
    CONFIG_DIR_NAME,
    PROJECT_NAME,
)

# --- Temporary path registry -------------------------------------------------

_CLEANUP_TEMP_PATHS: set[Path] = set()


def register_temp_path(path: Path | str) -> None:
    """Register a temporary path to be swept on process exit."""
    if path:
        _CLEANUP_TEMP_PATHS.add(Path(path))


def remove_path(path: Path) -> None:
    """Remove a path without following a top-level symlink.

    The symlink check precedes is_dir() so a symlink to a directory is
    unlinked, never rmtree'd through the link.
    """
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def copy_path(src: Path, dest: Path) -> None:
    """Copy one path, preserving a top-level symlink as a symlink."""
    if src.is_symlink():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)
        dest.symlink_to(os.readlink(src))
    elif src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def cleanup_temp_paths() -> None:
    """Remove every registered temporary file and directory."""
    for p in list(_CLEANUP_TEMP_PATHS):
        remove_path(p)
    _CLEANUP_TEMP_PATHS.clear()


atexit.register(cleanup_temp_paths)


# --- Environment -------------------------------------------------------------

def _detect_run_mode(root_dir: Path, cache_dir: Path):
    """Decide (run_mode, mode_label, repo_dir) from the package root.

    "Where you run it is the mode it is." The .system-install marker wins first
    so a packaged install that also ships configs/ + assets/ is not misread as
    a local checkout.
    """
    if (root_dir / ".system-install").is_file():
        return ("system", "System Package", root_dir)
    if root_dir.resolve() == cache_dir.resolve():
        return ("standalone", "Remote Cache", cache_dir)
    if (root_dir / CONFIG_DIR_NAME).is_dir() and (root_dir / ASSETS_DIR_NAME).is_dir():
        return ("repo", "Local Path", root_dir)
    return ("standalone", "Remote Cache", cache_dir)


class Environment:
    def __init__(self):
        self.home = Path(os.environ.get("HOME", str(Path.home())))
        self.config_dir = self.home / ".config"

        raw_state = os.environ.get("XDG_STATE_HOME")
        if raw_state:
            state_path = Path(raw_state)
            try:
                if state_path.is_relative_to(self.home):
                    self.state_home = state_path
                else:
                    self.state_home = self.home / ".local/state"
            except (ValueError, AttributeError):
                self.state_home = self.home / ".local/state"
        else:
            self.state_home = self.home / ".local/state"
        # Tool-owned runtime transients live under <state_home>/<PROJECT_NAME>.
        self.state_dir = self.state_home / PROJECT_NAME

        self.cache_dir = self.home / ".cache" / PROJECT_NAME

        current_file = Path(__file__).resolve()
        pkg_dir = current_file.parent
        root_dir = pkg_dir.parent
        self.run_mode, self.mode_label, self.repo_dir = _detect_run_mode(root_dir, self.cache_dir)

        self.configs_src = self.repo_dir / CONFIG_DIR_NAME
        self.assets_src = self.repo_dir / ASSETS_DIR_NAME
        # Tool-owned user data lives under ~/.config/<PROJECT_NAME>.
        self.nyx_dir = self.config_dir / PROJECT_NAME
        self.version = get_version(self.repo_dir)


_ENV: Optional[Environment] = None


def get_env() -> Environment:
    """Return the global Environment, initializing it on first use."""
    global _ENV
    if _ENV is None:
        _ENV = Environment()
    return _ENV


# --- Pictures directory ------------------------------------------------------

_PICS_DIR_CACHE: Optional[Path] = None


def get_pics_dir() -> Path:
    """Resolve the user's Pictures directory (XDG), with a safe fallback.

    Used as the base for the wallpaper folder so files land where desktop tools
    expect them (e.g. ``~/图片``) instead of a dot directory.
    """
    global _PICS_DIR_CACHE
    if _PICS_DIR_CACHE is not None:
        return _PICS_DIR_CACHE
    home = get_env().home
    try:
        res = subprocess.run(
            ["xdg-user-dir", "PICTURES"],
            capture_output=True, text=True, check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
        d = res.stdout.strip()
        if d and d != str(home):
            _PICS_DIR_CACHE = Path(d)
            return _PICS_DIR_CACHE
    except Exception:
        pass
    _PICS_DIR_CACHE = home / "Pictures"
    return _PICS_DIR_CACHE


# --- Version -----------------------------------------------------------------

_VERSION_CACHE: str = ""


def get_version(target_dir: Path) -> str:
    global _VERSION_CACHE
    if _VERSION_CACHE:
        return _VERSION_CACHE
    changelog = target_dir / "CHANGELOG.md"
    if changelog.is_file():
        try:
            content = changelog.read_text(encoding="utf-8")
            for candidate in re.findall(r"^##\s+\[([^\]]+)\]", content, re.MULTILINE):
                if candidate.lower() != "unreleased":
                    _VERSION_CACHE = candidate
                    return _VERSION_CACHE
        except Exception:
            pass
    if (target_dir / ".git").is_dir():
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=target_dir, capture_output=True, text=True, check=False,
                env={**os.environ, "LC_ALL": "C"},
            )
            v = res.stdout.strip()
            if v:
                _VERSION_CACHE = v
                return _VERSION_CACHE
        except Exception:
            pass
    _VERSION_CACHE = "dev"
    return _VERSION_CACHE


# --- Single-instance lock (fcntl.flock — auto-releases on process death) ------

_LOCK_FILE: Optional[Path] = None
_LOCK_FD: Optional[int] = None
_LOCK_ACQUIRED = False


def acquire_lock() -> None:
    """Acquire the single-instance lock.

    flock is kernel-level and releases when the process exits (even on SIGKILL),
    so there is no stale-lock healing and no check-then-write race. A PID is
    still written to the file for diagnostics only.
    """
    global _LOCK_FILE, _LOCK_FD, _LOCK_ACQUIRED
    env = get_env()
    env.state_dir.mkdir(parents=True, exist_ok=True)
    _LOCK_FILE = env.state_dir / f"{CLI_CMD}.lock"
    lock_fd: Optional[int] = None
    try:
        lock_fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        _LOCK_FD = None
        _LOCK_ACQUIRED = False
        pid = "unknown"
        try:
            content = _LOCK_FILE.read_text().strip()
            if content.isdigit():
                pid = content
        except Exception:
            pass
        from zekniri.i18n import msg
        print(msg("err_already_running", pid), file=sys.stderr)
        sys.exit(1)
    _LOCK_FD = lock_fd
    _LOCK_ACQUIRED = True
    try:
        os.ftruncate(_LOCK_FD, 0)
        os.write(_LOCK_FD, str(os.getpid()).encode())
    except Exception:
        pass


def release_lock() -> None:
    """Release the lock held by this process, keeping the stable lock path."""
    global _LOCK_FD, _LOCK_ACQUIRED
    if _LOCK_ACQUIRED and _LOCK_FD is not None:
        try:
            fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            try:
                os.close(_LOCK_FD)
            except Exception:
                pass
            _LOCK_FD = None
            _LOCK_ACQUIRED = False


atexit.register(release_lock)


# --- Rolling log -------------------------------------------------------------

_LOG_FILE: Optional[Path] = None
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def init_logger() -> None:
    """Create the state directory and truncate the log to the last 800 lines."""
    global _LOG_FILE
    from zekniri.config import get_config

    env = get_env()
    env.state_dir.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = get_config().log_path or (env.state_dir / "install.log")
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _LOG_FILE.is_file():
        try:
            lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > 800:
                _LOG_FILE.write_text("\n".join(lines[-800:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"{now} [INFO] {PROJECT_NAME} session started ({env.version}) [mode: {env.mode_label}]\n"
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(header)
    except Exception:
        pass


def log_msg(level: str, message: str) -> None:
    """Append a timestamped, ANSI-free line to the log."""
    if _LOG_FILE is None:
        return
    clean_text = ANSI_ESCAPE_RE.sub("", message)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{now} [{level}] {clean_text}\n")
    except Exception:
        pass


def timed_run(cmd: list, timeout: float, **kw) -> Optional[subprocess.CompletedProcess]:
    """subprocess.run that degrades a timeout to None instead of raising.

    Every external command with a timeout goes through here: a stalled network
    call or unresponsive daemon is polish failing, not a reason to abort the
    whole flow mid-deploy.
    """
    try:
        return subprocess.run(cmd, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        log_msg("WARN", f"Command timed out after {timeout}s: {cmd[0]}")
        return None


# --- CLI symlink -------------------------------------------------------------

def _cli_link_marker() -> Path:
    return get_env().state_dir / f"{CLI_CMD}.link"


def _cli_link_record(path: Path) -> Optional[str]:
    if not path.is_symlink():
        return None
    try:
        st = path.lstat()
        return f"{path.resolve(strict=False)}\n{st.st_dev}:{st.st_ino}\n"
    except (OSError, RuntimeError):
        return None


def _record_cli_symlink(path: Path) -> bool:
    record = _cli_link_record(path)
    marker = _cli_link_marker()
    if record is None or marker.is_symlink() or (marker.exists() and not marker.is_file()):
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(record, encoding="utf-8")
        marker.chmod(0o600)
        return True
    except OSError:
        return False


def is_cli_symlink(path: Path) -> bool:
    """Whether path is the CLI symlink this tool recorded."""
    if not path.is_symlink():
        return False
    record = _cli_link_record(path)
    marker = _cli_link_marker()
    if record is not None and not marker.is_symlink() and marker.is_file():
        try:
            return marker.read_text(encoding="utf-8") == record
        except OSError:
            pass
    try:
        raw_target = os.readlink(path)
        target_path = Path(raw_target)
        if target_path.name == "install.sh":
            resolved_str = str(path.resolve(strict=False))
            raw_str = str(target_path)
            if PROJECT_NAME in raw_str or PROJECT_NAME in resolved_str:
                return True
            env = get_env()
            if target_path in (env.repo_dir / "install.sh", env.cache_dir / "install.sh"):
                return True
    except (OSError, RuntimeError):
        pass
    return False


def clear_cli_symlink_marker() -> None:
    """Forget a CLI link only after its recorded link has been removed."""
    marker = _cli_link_marker()
    if marker.is_file() and not marker.is_symlink():
        try:
            marker.unlink()
        except OSError:
            pass


def ensure_cli_symlink() -> None:
    """Ensure ~/.local/bin/<CLI_CMD> points at install.sh.

    In system mode the package owns the entry point and this is a no-op. A
    stale user link shadowing a system package is surfaced by
    check_path_occlusion().
    """
    env = get_env()
    if env.run_mode == "system":
        return

    bin_dir = env.home / ".local/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target_bin = bin_dir / CLI_CMD

    root_installer = env.repo_dir / "install.sh"
    if not root_installer.is_file():
        if (env.cache_dir / "install.sh").is_file():
            root_installer = env.cache_dir / "install.sh"
        else:
            return

    try:
        if target_bin.is_symlink():
            if not is_cli_symlink(target_bin):
                return
            if target_bin.resolve(strict=False) == root_installer.resolve(strict=False):
                _record_cli_symlink(target_bin)
                root_installer.chmod(0o755)
                return
            target_bin.unlink(missing_ok=True)
        elif target_bin.exists():
            return
        target_bin.symlink_to(root_installer)
        if _record_cli_symlink(target_bin):
            root_installer.chmod(0o755)
        else:
            target_bin.unlink(missing_ok=True)
    except Exception:
        pass


# --- PATH registration -------------------------------------------------------

_CLI_PATH_MARKER = "# >>> ZEKniri: ~/.local/bin on PATH >>>"
_CLI_PATH_EXPORT = 'export PATH="$HOME/.local/bin:$PATH"'
_CLI_PATH_FISH = "fish_add_path -g $HOME/.local/bin"


def _shell_name() -> str:
    return Path(os.environ.get("SHELL", "")).name or "sh"


def _cli_path_target() -> Path:
    """Startup file that puts ~/.local/bin on PATH for the user's shell."""
    home = get_env().home
    shell = _shell_name()
    if shell == "fish":
        return home / ".config" / "fish" / "conf.d" / "zekniri-path.fish"
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "bash":
        return home / ".bashrc"
    return home / ".profile"


def ensure_cli_path() -> Optional[Path]:
    """Persist ~/.local/bin on PATH for the user's shell (idempotent).

    Writes only when the directory is absent from both the live PATH and the
    shell's startup file. System installs own their entry point, so they are
    skipped. Returns the file written, or None when nothing changed.
    """
    env = get_env()
    if env.run_mode == "system":
        return None

    if str(env.home / ".local" / "bin") in os.environ.get("PATH", "").split(os.pathsep):
        return None

    target = _cli_path_target()
    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    except OSError:
        existing = ""
    if ".local/bin" in existing or _CLI_PATH_MARKER in existing:
        return None

    line = _CLI_PATH_FISH if _shell_name() == "fish" else _CLI_PATH_EXPORT
    block = f"\n{_CLI_PATH_MARKER}\n{line}\n"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(block)
    except OSError:
        return None
    log_msg("INFO", f"Added ~/.local/bin to PATH via {target}")
    return target


def cli_path_status() -> str:
    """"active" when on the live PATH, "pending" when persisted, else "missing"."""
    env = get_env()
    bin_dir = str(env.home / ".local" / "bin")
    if bin_dir in os.environ.get("PATH", "").split(os.pathsep):
        return "active"
    target = _cli_path_target()
    try:
        if target.is_file() and ".local/bin" in target.read_text(encoding="utf-8"):
            return "pending"
    except OSError:
        pass
    return "missing"


def check_path_occlusion() -> bool:
    """In system mode, warn if ~/.local/bin/<CLI_CMD> shadows /usr/bin.

    Returns True when an occlusion was reported.
    """
    env = get_env()
    if env.run_mode != "system":
        return False
    user_link = env.home / ".local/bin" / CLI_CMD
    if user_link.is_symlink() or user_link.exists():
        from zekniri.i18n import msg
        print(msg("path_occlusion_warn"))
        log_msg("WARN", "A user-territory CLI link shadows the system package")
        return True
    return False
