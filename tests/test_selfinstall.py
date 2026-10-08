import os
import unittest

import zekniri.core as core
from zekniri import cli
from tests.utils import TempEnv


class _EnvVar:
    """Temporarily set env vars, restoring the previous values afterwards."""

    def __init__(self, **values):
        self.values = values
        self.old = {}

    def __enter__(self):
        for key, val in self.values.items():
            self.old[key] = os.environ.get(key)
            os.environ[key] = val
        return self

    def __exit__(self, *exc):
        for key, val in self.old.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        return False


class SelfInstallTest(unittest.TestCase):
    def test_fish_path_written_once(self):
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/fish", PATH="/usr/bin:/bin"):
            target = core.ensure_cli_path()
            self.assertEqual(target, t.home / ".config" / "fish" / "conf.d" / "zekniri-path.fish")
            text = target.read_text(encoding="utf-8")
            self.assertIn("fish_add_path -g $HOME/.local/bin", text)
            self.assertIn("ZEKniri", text)
            # idempotent even though the live PATH still lacks the dir
            self.assertIsNone(core.ensure_cli_path())

    def test_bash_path(self):
        with TempEnv() as t, _EnvVar(SHELL="/bin/bash", PATH="/usr/bin:/bin"):
            target = core.ensure_cli_path()
            self.assertEqual(target, t.home / ".bashrc")
            self.assertIn('export PATH="$HOME/.local/bin:$PATH"', target.read_text(encoding="utf-8"))

    def test_zsh_and_fallback_targets(self):
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/zsh", PATH="/usr/bin:/bin"):
            self.assertEqual(core.ensure_cli_path(), t.home / ".zshrc")
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/unknown-sh", PATH="/usr/bin:/bin"):
            self.assertEqual(core.ensure_cli_path(), t.home / ".profile")

    def test_skips_when_already_on_path(self):
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/fish", PATH="/usr/bin:/bin"):
            os.environ["PATH"] = f"/usr/bin:{t.home}/.local/bin:/bin"
            self.assertIsNone(core.ensure_cli_path())
            self.assertFalse((t.home / ".config" / "fish").exists())

    def test_system_mode_noop(self):
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/fish", PATH="/usr/bin:/bin"):
            t.env.run_mode = "system"
            self.assertIsNone(core.ensure_cli_path())

    def test_status_transitions(self):
        with TempEnv() as t, _EnvVar(SHELL="/usr/bin/fish", PATH="/usr/bin:/bin"):
            self.assertEqual(core.cli_path_status(), "missing")
            core.ensure_cli_path()
            self.assertEqual(core.cli_path_status(), "pending")
            os.environ["PATH"] = f"/usr/bin:{t.home}/.local/bin"
            self.assertEqual(core.cli_path_status(), "active")

    def test_announce_first_run_writes_marker(self):
        with TempEnv() as t:
            link = t.home / ".local" / "bin" / "ZEK-niri"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.write_text("#!/bin/sh\n", encoding="utf-8")
            cli.announce_self_install(None)
            self.assertTrue((t.home / ".local" / "state" / "ZEKniri" / ".installed").is_file())


if __name__ == "__main__":
    unittest.main()
