import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MARKDOWN_FILES = (
    README,
    ROOT / "docs" / "macrodroid-setup.md",
    ROOT / "docs" / "customize.md",
    ROOT / "docs" / "troubleshooting.md",
    ROOT / "SECURITY.md",
)


class DocumentationContractTests(unittest.TestCase):
    def test_vercel_clone_link_requires_only_the_two_secrets(self) -> None:
        if not README.is_file():
            self.fail("README.md must provide the public deployment entry point")

        content = README.read_text(encoding="utf-8")
        matches = re.findall(r"https://vercel\.com/clone\?[^\s)>]+", content)
        self.assertEqual(len(matches), 1, "README must contain one canonical Vercel clone URL")

        parsed = urlparse(matches[0])
        query = parse_qs(parsed.query, keep_blank_values=True)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "vercel.com")
        self.assertEqual(parsed.path, "/clone")
        self.assertEqual(
            query.get("repository-url"),
            ["https://github.com/chegom/soopbot"],
        )
        self.assertEqual(
            set(query.get("env", [""])[0].split(",")),
            {"OPENAI_API_KEY", "SOOPBOT_TOKEN"},
        )

        defaults = query.get("envDefaults", [])
        self.assertFalse(
            any(secret in value for value in defaults for secret in ("OPENAI_API_KEY", "SOOPBOT_TOKEN")),
            "secret environment variables must not have deploy-link defaults",
        )

    def test_all_documentation_pages_and_relative_links_exist(self) -> None:
        for markdown_file in MARKDOWN_FILES:
            with self.subTest(document=markdown_file.relative_to(ROOT)):
                self.assertTrue(markdown_file.is_file(), f"missing documentation file: {markdown_file}")
                content = markdown_file.read_text(encoding="utf-8")
                for target in re.findall(r"(?<!!)\[[^]]*]\(([^)]+)\)", content):
                    target = target.strip().split(maxsplit=1)[0].strip("<>")
                    parsed = urlparse(target)
                    if parsed.scheme or parsed.netloc or target.startswith("#"):
                        continue
                    linked_path = (markdown_file.parent / parsed.path).resolve()
                    self.assertTrue(
                        linked_path.is_file(),
                        f"broken relative link in {markdown_file.relative_to(ROOT)}: {target}",
                    )

    def test_example_environment_contains_no_secret_values(self) -> None:
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(content, r"(?im)^OPENAI_API_KEY\s*=\s*sk-")
        self.assertNotRegex(content, r"(?im)^SOOPBOT_TOKEN\s*=\s*[A-Za-z0-9]{24,}\s*$")


if __name__ == "__main__":
    unittest.main()
