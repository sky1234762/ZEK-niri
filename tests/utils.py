"""Shared test utilities: full environment isolation to a temp HOME.

Tests must NEVER touch the real ~/.config, ~/.local, or ~/.cache. TempEnv
points HOME at a throwaway directory and resets every module-level cache so
state cannot leak between tests.
"""

import os
import tempfile
from pathlib import Path

import zekniri.core as core


class TempEnv:
    """Context manager isolating the Environment to a temp HOME (repo mode)."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._old_env = {}

    def __enter__(self):
        home = self.home
        (home / ".config").mkdir(parents=True, exist_ok=True)
        (home / ".local" / "bin").mkdir(parents=True, exist_ok=True)
        (home / ".local" / "state" / "ZEKniri").mkdir(parents=True, exist_ok=True)
        (home / ".cache").mkdir(parents=True, exist_ok=True)
        # A per-test source tree so tests never read or write the real repo.
        (home / "configs").mkdir(parents=True, exist_ok=True)
        (home / "assets").mkdir(parents=True, exist_ok=True)

        for key in ("HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            self._old_env[key] = os.environ.get(key)
        os.environ["HOME"] = str(home)
        os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
        os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
        os.environ["XDG_CACHE_HOME"] = str(home / ".cache")

        core._ENV = None
        core._VERSION_CACHE = ""
        core._LOG_FILE = None
        core._PICS_DIR_CACHE = None

        import zekniri.config as _config
        import zekniri.deploy.deploy as _deploy_core
        import zekniri.deploy.manifest as _deploy_manifest
        import zekniri.deps as _deps
        import zekniri.i18n as _i18n
        _config._CONFIG = None
        _deploy_core._CONFIG_ITEMS_CACHE = []
        _deploy_manifest._MANIFEST_CACHE = None
        _deps._PACMAN_INSTALLED_CACHE = None
        _i18n._reset_language_cache()

        env = core.get_env()
        env.run_mode = "repo"
        env.mode_label = "Local Path"
        env.repo_dir = home
        env.configs_src = home / "configs"
        env.assets_src = home / "assets"
        self.env = env
        return self

    def __exit__(self, *exc):
        for key, val in self._old_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        core._ENV = None
        import zekniri.config as _config
        _config._CONFIG = None
        self._tmp.cleanup()
        return False
