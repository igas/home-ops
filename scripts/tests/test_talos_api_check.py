"""Exercise the operational check's CLI boundary without cluster access."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TalosApiCheck(unittest.TestCase):
    def test_successful_debug_exit_without_completed_probe_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "talosctl"
            cli.write_text("#!/bin/sh\necho 'debug stream ended before completion'\nexit 0\n")
            cli.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/talos-api-check.py")],
                env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]},
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("All Talos hosts passed", result.stdout)
        self.assertIn("debug stream ended without a completed probe", result.stderr)


if __name__ == "__main__":
    unittest.main()
