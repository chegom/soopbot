import unittest
from dataclasses import replace

from soopbot.config import Settings
from soopbot.conversation import MemoryConversationLog, Turn
from soopbot.reply import ReplyService, extract_question


class RecordingProvider:
    def __init__(self) -> None:
        self.questions: list[str] = []
        self.personas: list[str] = []
        self.contexts: list[tuple] = []
        self.response = "답변입니다"
        self.error: Exception | None = None

    def generate(self, *, persona: str, question: str, context=()) -> str:
        self.personas.append(persona)
        self.questions.append(question)
        self.contexts.append(tuple(context))
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

    def _service_with_history(self, turns: int) -> ReplyService:
        settings = replace(self.settings, max_history_turns=turns)
        return ReplyService(settings, self.provider, MemoryConversationLog())

    def test_previous_turn_becomes_context_for_the_next_question(self) -> None:
        service = self._service_with_history(4)
        self.provider.response = "파이썬을 추천해요"
        service.handle("숲봇아 어떤 언어를 배울까?")

        service.handle("숲봇아 왜 그렇지?")

        self.assertEqual((), self.provider.contexts[0])
        self.assertEqual(
            (Turn("어떤 언어를 배울까?", "파이썬을 추천해요"),),
            self.provider.contexts[1],
        )

    def test_context_keeps_only_the_newest_turns(self) -> None:
        service = self._service_with_history(2)
        for index in range(1, 4):
            self.provider.response = f"답변{index}"
            service.handle(f"숲봇아 질문{index}")

        service.handle("숲봇아 이어서")

        self.assertEqual(
            (Turn("질문2", "답변2"), Turn("질문3", "답변3")),
            self.provider.contexts[-1],
        )

    def test_zero_history_turns_keeps_replies_stateless(self) -> None:
        service = self._service_with_history(0)
        service.handle("숲봇아 첫 질문")

        service.handle("숲봇아 두번째 질문")

        self.assertEqual((), self.provider.contexts[-1])

    def test_failed_answers_are_never_remembered(self) -> None:
        service = self._service_with_history(4)
        self.provider.error = RuntimeError("provider down")
        with self.assertLogs("soopbot.reply", level="WARNING"):
            service.handle("숲봇아 실패할 질문")
        self.provider.error = None

        service.handle("숲봇아 다음 질문")

        self.assertEqual((), self.provider.contexts[-1])

    def test_bare_trigger_introduction_is_never_remembered(self) -> None:
        service = self._service_with_history(4)
        service.handle("숲봇아")

        service.handle("숲봇아 진짜 질문")

        self.assertEqual((), self.provider.contexts[-1])

    def test_provider_output_is_truncated_to_configured_limit(self) -> None:
        self.provider.response = "가" * 120

        outcome = self.service.handle("숲봇아 길게 답해줘")

        self.assertEqual("reply", outcome.kind)
        self.assertEqual("가" * 100, outcome.content)
        self.assertEqual(["길게 답해줘"], self.provider.questions)
