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
        secret_prefix = "s" + "k-"
        self.assertNotRegex(
            content,
            rf"(?im)^OPENAI_API_KEY\s*=\s*{re.escape(secret_prefix)}",
        )
        self.assertNotRegex(content, r"(?im)^SOOPBOT_TOKEN\s*=\s*[A-Za-z0-9]{24,}\s*$")

    def test_macrodroid_trigger_separates_exact_title_and_message_filters(self) -> None:
        content = (ROOT / "docs" / "macrodroid-setup.md").read_text(encoding="utf-8")
        trigger_section = content.split("## 1. 새 매크로와 트리거 만들기", 1)[1].split(
            "## 2. 응답 변수 초기화하기", 1
        )[0]

        self.assertIn("Separate title and message", trigger_section)
        self.assertRegex(trigger_section, r"Title.*Matches.*정확한 방 제목")
        self.assertRegex(trigger_section, r"Message.*Contains.*`숲봇아`")

    def test_macrodroid_response_variables_are_global_and_use_global_reference(self) -> None:
        content = (ROOT / "docs" / "macrodroid-setup.md").read_text(encoding="utf-8")

        self.assertIn("전역 문자열 변수 `soopbot_reply`", content)
        self.assertIn("전역 정수 변수 `soopbot_status`", content)
        self.assertIn("[v=soopbot_reply]", content)
        self.assertNotRegex(content, r"지역 .*`soopbot_(?:reply|status)`")


if __name__ == "__main__":
    unittest.main()
