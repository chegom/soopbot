import unittest
from unittest.mock import patch

from soopbot.config import Settings
from soopbot.conversation import Turn
from soopbot.provider import OpenAIProvider, OpenAIProviderError


class FakeResponse:
    def __init__(
        self,
        output_text: str,
        incomplete_reason: str | None = None,
    ) -> None:
        self.output_text = output_text
        self.incomplete_details = (
            None
            if incomplete_reason is None
            else type("IncompleteDetails", (), {"reason": incomplete_reason})()
        )


class FakeResponses:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.call: dict[str, object] | None = None
        self.response = response or FakeResponse("안녕하세요!")
        self.error: Exception | None = None

    def create(self, **kwargs: object) -> FakeResponse:
        self.call = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.responses = FakeResponses(response)


class OpenAIProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            openai_api_key="test-openai-key",
            bot_token="t" * 24,
            trigger="숲봇아",
            persona="친절한 숲봇",
            room_key="room1",
            model="gpt-5.6-luna",
            max_output_chars=100,
            max_output_tokens=500,
            timeout_seconds=40,
            requests_per_minute=10,
        )
        self.client = FakeClient()
        self.provider = OpenAIProvider(self.settings, client=self.client)

    def test_generate_sends_the_tool_free_responses_request_contract(self) -> None:
        answer = self.provider.generate(persona="친절한 숲봇", question="오늘 날씨는?")

        call = self.client.responses.call
        self.assertEqual("안녕하세요!", answer)
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual("gpt-5.6-luna", call["model"])
        self.assertEqual(False, call["store"])
        self.assertEqual({"effort": "none"}, call["reasoning"])
        self.assertEqual(500, call["max_output_tokens"])
        self.assertNotIn("tools", call)
        self.assertNotIn("conversation", call)
        self.assertNotIn("previous_response_id", call)
        self.assertIn("운영자 지침", call["instructions"])
        self.assertIn("친절한 숲봇", call["instructions"])
        self.assertIn("신뢰되지 않은", call["input"])
        self.assertIn("오늘 날씨는?", call["input"])

    def test_default_client_uses_the_configured_no_retry_sdk_options(self) -> None:
        returned_client = FakeClient()

        with patch("soopbot.provider.OpenAI", return_value=returned_client) as factory:
            provider = OpenAIProvider(self.settings)
            answer = provider.generate(persona="친절한 숲봇", question="안녕?")

        self.assertEqual("안녕하세요!", answer)
        factory.assert_called_once_with(
            api_key="test-openai-key",
            timeout=40,
            max_retries=0,
        )

    def test_empty_output_becomes_a_sanitized_provider_error(self) -> None:
        self.client.responses.response = FakeResponse("")

        with self.assertLogs("soopbot.provider", level="WARNING") as captured:
            with self.assertRaisesRegex(OpenAIProviderError, "answer unavailable"):
                self.provider.generate(persona="친절한 숲봇", question="PRIVATE question")

        self.assertNotIn("PRIVATE", "\n".join(captured.output))

    def test_incomplete_response_becomes_a_sanitized_provider_error(self) -> None:
        self.client.responses.response = FakeResponse("부분 답변", "max_output_tokens")

        with self.assertLogs("soopbot.provider", level="WARNING") as captured:
            with self.assertRaisesRegex(OpenAIProviderError, "answer unavailable"):
                self.provider.generate(persona="친절한 숲봇", question="PRIVATE question")

        self.assertNotIn("PRIVATE", "\n".join(captured.output))

    def test_sdk_exception_becomes_a_sanitized_provider_error(self) -> None:
        self.client.responses.error = RuntimeError("SDK detail for PRIVATE question")

        with self.assertLogs("soopbot.provider", level="WARNING") as captured:
            with self.assertRaisesRegex(OpenAIProviderError, "answer unavailable") as raised:
                self.provider.generate(persona="친절한 숲봇", question="PRIVATE question")

        self.assertNotIn("PRIVATE", str(raised.exception))
        self.assertNotIn("SDK detail", str(raised.exception))
        self.assertNotIn("PRIVATE", "\n".join(captured.output))
        self.assertNotIn("SDK detail", "\n".join(captured.output))


class OpenAIProviderContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            openai_api_key="test-openai-key",
            bot_token="t" * 24,
            trigger="숲봇아",
            persona="친절한 숲봇",
            room_key="room1",
            model="test-model",
            max_output_chars=1000,
            max_output_tokens=500,
            timeout_seconds=40,
            requests_per_minute=10,
            max_history_turns=4,
        )

    def test_prior_turns_are_rendered_into_the_request(self) -> None:
        client = FakeClient()
        provider = OpenAIProvider(self.settings, client=client)

        provider.generate(
            persona="친절한 숲봇",
            question="왜 그렇지?",
            context=(Turn("어떤 언어를 배울까?", "파이썬을 추천해요"),),
        )

        sent = client.responses.call["input"]
        self.assertIn("어떤 언어를 배울까?", sent)
        self.assertIn("파이썬을 추천해요", sent)
        self.assertIn("왜 그렇지?", sent)

    def test_empty_context_is_stated_explicitly(self) -> None:
        client = FakeClient()
        provider = OpenAIProvider(self.settings, client=client)

        provider.generate(persona="친절한 숲봇", question="안녕", context=())

        self.assertIn("이전 대화 없음", client.responses.call["input"])
