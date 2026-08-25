import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_test_discovery.py"


class TestDiscoveryCheckTests(unittest.TestCase):
    def _run_checker(self, minimum: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--minimum", str(minimum)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_current_suite_meets_public_artifact_minimum(self) -> None:
        result = self._run_checker(40)

        self.assertEqual(result.returncode, 0, result.stderr)
        discovered = int(result.stdout.split()[1])
        self.assertGreaterEqual(discovered, 40)

    def test_minimum_above_current_suite_fails(self) -> None:
        result = self._run_checker(10_000)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fewer than required", result.stderr)


if __name__ == "__main__":
    unittest.main()
