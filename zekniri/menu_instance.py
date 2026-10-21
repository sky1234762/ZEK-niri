"""Single-instance toggle IPC for the standalone menu."""

from __future__ import annotations

import errno
import os
import socket
import stat
import time
from pathlib import Path


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "zekniri-menu.sock"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state / "ZEKniri" / "menu.sock"


def _send_toggle(path: Path, retries: int = 0) -> bool:
    for attempt in range(retries + 1):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.15)
        try:
            client.connect(str(path))
            client.sendall(b"toggle")
            return True
        except OSError:
            if attempt < retries:
                time.sleep(0.025)
        finally:
            client.close()
    return False


def start_or_toggle(path: Path | None = None, *, allow_start: bool = True) -> socket.socket | None:
    """Return a listening socket, or None after asking the existing menu to close."""
    path = path or socket_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    if _send_toggle(path):
        return None

    if path.exists() or path.is_symlink():
        try:
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise FileExistsError(errno.EEXIST, "menu socket path is not an owned socket", str(path))
            if _send_toggle(path, retries=4):
                return None
            path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass

    if not allow_start:
        return None

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
    except OSError as exc:
        server.close()
        if exc.errno == errno.EADDRINUSE and _send_toggle(path, retries=4):
            return None
        raise
    path.chmod(0o600)
    server.listen(4)
    server.setblocking(False)
    return server


def release_listener(server: socket.socket, path: Path | None = None) -> None:
    path = path or socket_path()
    try:
        owned_inode = server.fileno() >= 0 and path.is_socket()
    except OSError:
        owned_inode = False
    server.close()
    if owned_inode:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
