import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_public_tree.py"


class PublicTreeCheckTests(unittest.TestCase):
    def _run_checker(self, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(
                ["git", "init", "-q", "-b", "main"],
                cwd=repository,
                check=True,
            )
            for relative_path, content in files.items():
                path = repository / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            subprocess.run(
                ["git", "add", "--", "."],
                cwd=repository,
                check=True,
            )
            return subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(repository)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_clean_public_tree_with_example_environment_passes(self) -> None:
        safe_prefix_labels = ", ".join(
            ("s" + "k-", "g" + "ho_", "s" + "b_" + "secret_")
        )
        result = self._run_checker(
            {
                ".env.example": "OPENAI_API_KEY=replace-me\n",
                "README.md": f"Never commit keys beginning with {safe_prefix_labels}.\n",
                "src/main.py": "print('hello')\n",
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("public tree check passed", result.stdout)

    def test_tracked_generated_or_environment_paths_fail(self) -> None:
        result = self._run_checker(
            {
                ".env.local": "SAFE_PLACEHOLDER=replace-me\n",
                ".vercel/project.json": "{}\n",
                "src/__pycache__/main.pyc": "not-bytecode\n",
                "src/soopbot.egg-info/PKG-INFO": "generated metadata\n",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env.local", result.stderr)
        self.assertIn(".vercel/project.json", result.stderr)
        self.assertIn("src/__pycache__/main.pyc", result.stderr)
        self.assertIn("src/soopbot.egg-info/PKG-INFO", result.stderr)

    def test_obvious_secret_value_in_tracked_content_fails(self) -> None:
        secret_prefix = "s" + "k-"
        result = self._run_checker(
            {"notes.txt": f"OPENAI_API_KEY={secret_prefix}this-is-not-a-real-key\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt", result.stderr)
        self.assertIn("secret-like content", result.stderr)

    def test_github_fine_grained_token_in_tracked_content_fails(self) -> None:
        secret_prefix = "github" + "_pat_"
        result = self._run_checker(
            {"notes.txt": f"TOKEN={secret_prefix}{'x' * 24}\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt", result.stderr)
        self.assertIn("secret-like content", result.stderr)

    def test_github_user_token_in_tracked_content_fails(self) -> None:
        secret_prefix = "g" + "hu_"
        result = self._run_checker(
            {"notes.txt": f"TOKEN={secret_prefix}{'x' * 24}\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt", result.stderr)
        self.assertIn("secret-like content", result.stderr)

    def test_private_key_in_tracked_content_fails(self) -> None:
        private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
        result = self._run_checker(
            {"private.pem": f"{private_key_marker}\nnot-a-real-key\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private.pem", result.stderr)
        self.assertIn("secret-like content", result.stderr)

    def test_dsa_private_key_in_tracked_content_fails(self) -> None:
        private_key_marker = "-----BEGIN " + "DSA PRIVATE KEY-----"
        result = self._run_checker(
            {"private.pem": f"{private_key_marker}\nnot-a-real-key\n"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private.pem", result.stderr)
        self.assertIn("secret-like content", result.stderr)

    def test_machine_specific_path_in_tracked_content_fails(self) -> None:
        local_path = "/" + "Users" + "/" + "u" + "huru" + "/project"
        result = self._run_checker({"notes.txt": f"workspace={local_path}\n"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt", result.stderr)
        self.assertIn("machine-specific content", result.stderr)


if __name__ == "__main__":
    unittest.main()
