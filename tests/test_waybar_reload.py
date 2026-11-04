from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "configs" / "waybar" / "scripts" / "reload-waybar.sh"


class WaybarReloadScriptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.config_home = self.root / "xdg-config"
        self.cache_home = self.root / "xdg-cache"
        self.runtime = self.root / "runtime"
        self.bin = self.root / "bin"
        for directory in (self.home, self.config_home, self.cache_home, self.runtime, self.bin):
            directory.mkdir(parents=True, exist_ok=True)
        self.config = self.config_home / "waybar"
        self.config.mkdir()
        self.log = self.root / "pkill.log"
        fake_pkill = self.bin / "pkill"
        fake_pkill.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_PKILL_LOG\"\n"
            "if [[ -n ${FAKE_PKILL_DELAY:-} ]]; then sleep \"$FAKE_PKILL_DELAY\"; fi\n"
            "exit \"${FAKE_PKILL_STATUS:-0}\"\n",
            encoding="utf-8",
        )
        fake_pkill.chmod(0o755)
        self.write_css()

    def tearDown(self):
        self.temp.cleanup()

    def write_css(self, *, base_comment="base", palette_comment="palette", color="#123456"):
        (self.config / "style.css").write_text(
            f"/* {base_comment} */\n@import \"colors-active.css\";\n",
            encoding="utf-8",
        )
        (self.config / "colors-active.css").write_text(
            "/* active selector */\n@import url(\"palettes/colors.css\");\n",
            encoding="utf-8",
        )
        palette = self.config / "palettes"
        palette.mkdir(exist_ok=True)
        (palette / "colors.css").write_text(
            f"/* {palette_comment} */\n@define-color primary {color};\n",
            encoding="utf-8",
        )

    def env(self, **extra):
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_home),
                "XDG_CACHE_HOME": str(self.cache_home),
                "XDG_RUNTIME_DIR": str(self.runtime),
                "PATH": f"{self.bin}:/usr/bin:/bin",
                "FAKE_PKILL_LOG": str(self.log),
                "WAYBAR_RELOAD_GAP_MS": "0",
            }
        )
        for key in (
            "WAYBAR_CONFIG_DIR",
            "WAYBAR_FORCE",
            "WAYBAR_NO_RELOAD",
            "WAYBAR_RELOAD_DEBUG",
            "FAKE_PKILL_STATUS",
            "FAKE_PKILL_DELAY",
        ):
            env.pop(key, None)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_script(self, **extra):
        return subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=self.env(**extra),
            timeout=10,
            check=False,
        )

    def signals(self):
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_cache_uses_xdg_config_home_and_ignores_css_comments(self):
        first = self.run_script()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.signals(), ["-USR2 -x waybar"])

        self.write_css(base_comment="changed base comment", palette_comment="changed metadata")
        second = self.run_script()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(self.signals()), 1)

    def test_effective_import_change_reloads_and_force_bypasses_cache(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.write_css(color="#abcdef")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(len(self.signals()), 2)

        forced = self.run_script(WAYBAR_FORCE="1")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(len(self.signals()), 3)

    def test_no_reload_does_not_mark_new_fingerprint_as_applied(self):
        suppressed = self.run_script(WAYBAR_NO_RELOAD="1")
        self.assertEqual(suppressed.returncode, 0, suppressed.stderr)
        self.assertEqual(self.signals(), [])

        normal = self.run_script()
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(len(self.signals()), 1)

    def test_no_waybar_signal_does_not_consume_fingerprint(self):
        missing = self.run_script(FAKE_PKILL_STATUS="1")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertEqual(self.signals(), ["-USR2 -x waybar"])

        running = self.run_script(FAKE_PKILL_STATUS="0")
        self.assertEqual(running.returncode, 0, running.stderr)
        self.assertEqual(len(self.signals()), 2)

    def test_concurrent_identical_requests_send_one_signal(self):
        env = self.env(FAKE_PKILL_DELAY="0.15")
        commands = [["bash", str(SCRIPT)], ["bash", str(SCRIPT)]]
        processes = [subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for command in commands]
        results = [process.communicate(timeout=10) + (process.returncode,) for process in processes]
        self.assertTrue(all(result[2] == 0 for result in results), results)
        self.assertEqual(len(self.signals()), 1)

    def test_different_config_trees_share_signal_throttle(self):
        other = self.root / "second-waybar"
        other.mkdir()
        (other / "style.css").write_text("window { color: #abcdef; }\n", encoding="utf-8")
        env_one = self.env(WAYBAR_RELOAD_GAP_MS="120", WAYBAR_CONFIG_DIR=self.config, FAKE_PKILL_DELAY="0.04")
        env_two = self.env(WAYBAR_RELOAD_GAP_MS="120", WAYBAR_CONFIG_DIR=other, FAKE_PKILL_DELAY="0.04")
        start = __import__("time").monotonic()
        processes = [
            subprocess.Popen(["bash", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for env in (env_one, env_two)
        ]
        results = [process.communicate(timeout=10) + (process.returncode,) for process in processes]
        elapsed = __import__("time").monotonic() - start
        self.assertTrue(all(result[2] == 0 for result in results), results)
        self.assertEqual(len(self.signals()), 2)
        self.assertGreaterEqual(elapsed, 0.14)

    def test_missing_import_fails_without_signaling(self):
        (self.config / "colors-active.css").write_text('@import "missing.css";\n', encoding="utf-8")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing CSS import", result.stderr)
        self.assertEqual(self.signals(), [])

    def test_invalid_gap_is_rejected(self):
        result = self.run_script(WAYBAR_RELOAD_GAP_MS="-1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.signals(), [])

    def test_config_dir_override_and_absolute_css_import(self):
        other = self.root / "custom waybar"
        other.mkdir()
        absolute_css = self.root / "absolute palette.css"
        absolute_css.write_text("@define-color accent #010203;\n", encoding="utf-8")
        (other / "style.css").write_text(f'@import "{absolute_css}";\n', encoding="utf-8")
        result = self.run_script(WAYBAR_CONFIG_DIR=other)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.signals()), 1)


if __name__ == "__main__":
    unittest.main()
