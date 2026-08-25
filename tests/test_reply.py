import unittest

from soopbot.config import Settings
from soopbot.reply import ReplyService, extract_question


class RecordingProvider:
    def __init__(self) -> None:
        self.questions: list[str] = []
        self.personas: list[str] = []
        self.response = "답변입니다"
        self.error: Exception | None = None

    def generate(self, *, persona: str, question: str) -> str:
        self.personas.append(persona)
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return self.response


class ReplyServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = RecordingProvider()
        self.settings = Settings(
            openai_api_key="test-openai-key",
            bot_token="t" * 24,
            trigger="숲봇아",
            persona="친절한 숲봇",
            room_key="room1",
            model="test-model",
            max_output_chars=100,
            max_output_tokens=100,
            timeout_seconds=40,
            requests_per_minute=10,
        )
        self.service = ReplyService(self.settings, self.provider)

    def test_trigger_inside_notification_extracts_only_the_question(self) -> None:
        self.assertEqual(
            "오늘 기분 어때?",
            extract_question("홍길동: 숲봇아 오늘 기분 어때?", "숲봇아"),
        )

    def test_message_without_trigger_never_calls_provider(self) -> None:
        outcome = self.service.handle("그냥 대화예요")

        self.assertEqual("no_trigger", outcome.kind)
        self.assertEqual([], self.provider.questions)

    def test_provider_failure_returns_natural_korean_message(self) -> None:
        self.provider.error = RuntimeError("PRIVATE question and token")

        with self.assertLogs("soopbot.reply", level="WARNING") as captured:
            outcome = self.service.handle("숲봇아 안녕")

        self.assertEqual("provider_failure", outcome.kind)
        self.assertIn("다시 불러", outcome.content)
        self.assertNotIn("PRIVATE", "\n".join(captured.output))

    def test_bare_trigger_returns_three_line_introduction_without_provider(self) -> None:
        outcome = self.service.handle("숲봇아")

        self.assertEqual("reply", outcome.kind)
        self.assertEqual(3, len(outcome.content.splitlines()))
        self.assertEqual([], self.provider.questions)

    def test_message_of_4000_or_more_characters_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.handle("숲봇아" + "가" * 3997)

    def test_provider_output_is_truncated_to_configured_limit(self) -> None:
        self.provider.response = "가" * 120

        outcome = self.service.handle("숲봇아 길게 답해줘")

        self.assertEqual("reply", outcome.kind)
        self.assertEqual("가" * 100, outcome.content)
        self.assertEqual(["길게 답해줘"], self.provider.questions)
