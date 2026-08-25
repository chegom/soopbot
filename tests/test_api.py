import asyncio
import unittest
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.requests import ClientDisconnect

from api.index import Runtime, build_runtime, create_app
from soopbot.config import Settings
from soopbot.reply import ReplyService
from soopbot.request_guard import MemoryRequestGuard


class RecordingProvider:
    def __init__(self) -> None:
        self.questions: list[str] = []
        self.response = "생성한 답변"

    def generate(self, *, persona: str, question: str) -> str:
        self.questions.append(question)
        return self.response


class ExplodingGuard:
    def claim(self, *args: object, **kwargs: object) -> str:
        raise RuntimeError("guard detail must never reach logs")


class ApiBoundaryTest(unittest.TestCase):
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
            requests_per_minute=2,
        )

    def client_for(
        self,
        *,
        settings: Settings | None = None,
        guard: MemoryRequestGuard | ExplodingGuard | None = None,
    ) -> TestClient:
        active_settings = settings or self.settings
        runtime = Runtime(
            settings=active_settings,
            reply_service=ReplyService(active_settings, self.provider),
            request_guard=guard or MemoryRequestGuard(),
        )
        return TestClient(create_app(lambda: runtime))

    def request(
        self,
        client: TestClient,
        content: str = "숲봇아 안녕",
        *,
        room: str = "room1",
        token: str | None = None,
        event_id: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ):
        headers = {"Content-Type": content_type}
        if token is not None:
            headers["X-Bot-Token"] = token
        if event_id is not None:
            headers["X-Event-ID"] = event_id
        return client.post(f"/api/reply?room={room}", content=content, headers=headers)

    def test_health_never_loads_runtime_or_secrets(self) -> None:
        def unavailable_runtime() -> Runtime:
            raise RuntimeError("secret loading must not happen")

        client = TestClient(create_app(unavailable_runtime))

        for path in ("/", "/api/reply"):
            response = client.get(path)
            self.assertEqual(200, response.status_code)
            self.assertEqual("ok", response.text)
            self.assertTrue(response.headers["content-type"].startswith("text/plain"))

    def test_framework_documentation_routes_are_not_public(self) -> None:
        client = self.client_for()

        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(404, response.status_code)

    def test_runtime_composition_uses_only_the_supplied_environment(self) -> None:
        runtime = build_runtime(
            {
                "OPENAI_API_KEY": "test-openai-key",
                "SOOPBOT_TOKEN": "t" * 24,
            }
        )

        self.assertEqual("room1", runtime.settings.room_key)
        self.assertEqual("no_trigger", runtime.reply_service.handle("일반 메시지").kind)
        self.assertEqual(
            "accepted",
            runtime.request_guard.claim(
                "event", "room", limit=1, rate_window_seconds=60, dedupe_window_seconds=60, now=1
            ),
        )

    def test_missing_or_wrong_token_is_rejected_before_reply_generation(self) -> None:
        client = self.client_for()

        for token in (None, "wrong-token"):
            with self.subTest(token=token):
                response = self.request(client, token=token)
                self.assertEqual(401, response.status_code)
                self.assertTrue(response.headers["content-type"].startswith("text/plain"))

        self.assertEqual([], self.provider.questions)

    def test_unknown_room_returns_no_content(self) -> None:
        client = self.client_for()

        response = self.request(client, room="other", token=self.settings.bot_token)

        self.assertEqual(204, response.status_code)
        self.assertEqual([], self.provider.questions)

    def test_invalid_request_shapes_are_rejected(self) -> None:
        client = self.client_for()
        cases = (
            ("숲봇아 안녕", "application/json", None),
            ("", "text/plain", None),
            ("a" * 16_385, "text/plain", None),
            ("숲봇아 안녕", "text/plain", "e" * 301),
        )

        for content, content_type, event_id in cases:
            with self.subTest(content_type=content_type, length=len(content), event_id=event_id):
                response = self.request(
                    client,
                    content,
                    token=self.settings.bot_token,
                    event_id=event_id,
                    content_type=content_type,
                )
                self.assertEqual(400, response.status_code)
                self.assertTrue(response.headers["content-type"].startswith("text/plain"))

        self.assertEqual([], self.provider.questions)

    def test_invalid_or_oversized_content_length_is_rejected_before_body_use(self) -> None:
        client = self.client_for()
        headers = {
            "Content-Type": "text/plain",
            "X-Bot-Token": self.settings.bot_token,
        }

        for content_length in ("not-a-length", "-1", "16385"):
            with self.subTest(content_length=content_length):
                response = client.post(
                    "/api/reply?room=room1",
                    content="숲봇아 안녕",
                    headers={**headers, "Content-Length": content_length},
                )

                self.assertEqual(400, response.status_code)

        self.assertEqual([], self.provider.questions)

    def test_chunked_oversized_body_stops_after_the_first_overflow_chunk(self) -> None:
        client_app = self.client_for().app
        chunks_read: list[str] = []

        async def oversized_chunks():
            chunks_read.append("at-cap")
            yield b"a" * 16_384
            chunks_read.append("overflow")
            yield b"b"
            chunks_read.append("past-cap")
            yield b"c"

        async def send_request():
            async with AsyncClient(
                transport=ASGITransport(app=client_app), base_url="http://testserver"
            ) as client:
                return await client.post(
                    "/api/reply?room=room1",
                    content=oversized_chunks(),
                    headers={
                        "Content-Type": "text/plain",
                        "X-Bot-Token": self.settings.bot_token,
                    },
                )

        response = asyncio.run(send_request())

        self.assertEqual(400, response.status_code)
        self.assertEqual(["at-cap", "overflow"], chunks_read)
        self.assertEqual([], self.provider.questions)

    def test_client_disconnect_while_streaming_is_safe_and_sanitized(self) -> None:
        client = self.client_for()

        async def disconnected_stream(request):
            if False:
                yield b""
            raise ClientDisconnect("private body and token must never reach logs")

        with (
            patch("api.index.Request.stream", new=disconnected_stream),
            self.assertLogs("api.index", level="WARNING") as captured,
        ):
            response = self.request(
                client,
                "숲봇아 private-question",
                token=self.settings.bot_token,
                event_id="private-event-id",
            )

        self.assertEqual(503, response.status_code)
        self.assertEqual("no-store", response.headers["cache-control"])
        self.assertEqual(
            "잠시 연결이 불안정해요. 조금 뒤에 숲봇을 다시 불러 주세요.", response.text
        )
        log_message = "\n".join(captured.output)
        self.assertIn("stage=body", log_message)
        self.assertIn("error_code=service_unavailable", log_message)
        self.assertIn("error_type=ClientDisconnect", log_message)
        for secret in (
            "private body",
            "private-question",
            self.settings.bot_token,
            "private-event-id",
        ):
            self.assertNotIn(secret, log_message)

    def test_trigger_returns_plain_text_generated_reply(self) -> None:
        client = self.client_for()

        response = self.request(client, token=self.settings.bot_token, event_id="event-1")

        self.assertEqual(200, response.status_code)
        self.assertEqual("생성한 답변", response.text)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertEqual(["안녕"], self.provider.questions)

    def test_duplicate_explicit_event_does_not_generate_twice(self) -> None:
        client = self.client_for()

        first = self.request(client, token=self.settings.bot_token, event_id="event-1")
        duplicate = self.request(client, token=self.settings.bot_token, event_id="event-1")

        self.assertEqual(200, first.status_code)
        self.assertEqual(204, duplicate.status_code)
        self.assertEqual(["안녕"], self.provider.questions)

    def test_missing_event_id_uses_a_fifteen_second_bucket(self) -> None:
        client = self.client_for()

        with patch("api.index.time.time", return_value=0):
            first = self.request(client, token=self.settings.bot_token)
        with patch("api.index.time.time", return_value=15):
            later_bucket = self.request(client, token=self.settings.bot_token)

        self.assertEqual(200, first.status_code)
        self.assertEqual(200, later_bucket.status_code)
        self.assertEqual(["안녕", "안녕"], self.provider.questions)

    def test_room_limit_includes_retry_after(self) -> None:
        limited_settings = replace(self.settings, requests_per_minute=1)
        client = self.client_for(settings=limited_settings)

        accepted = self.request(client, token=limited_settings.bot_token, event_id="one")
        limited = self.request(client, token=limited_settings.bot_token, event_id="two")

        self.assertEqual(200, accepted.status_code)
        self.assertEqual(429, limited.status_code)
        self.assertEqual("60", limited.headers["retry-after"])
        self.assertEqual(["안녕"], self.provider.questions)

    def test_unexpected_runtime_or_guard_failure_is_safe_and_sanitized(self) -> None:
        secret_body = "숲봇아 body-not-for-logs"
        secret_event_id = "event-not-for-logs"
        secret_token = self.settings.bot_token
        cases = (
            (
                "runtime",
                TestClient(
                    create_app(
                        lambda: (_ for _ in ()).throw(
                            RuntimeError("runtime detail must never reach logs")
                        )
                    )
                ),
            ),
            ("guard", self.client_for(guard=ExplodingGuard())),
        )

        for stage, client in cases:
            with self.subTest(stage=stage), self.assertLogs("api.index", level="WARNING") as captured:
                response = self.request(
                    client,
                    secret_body,
                    token=secret_token,
                    event_id=secret_event_id,
                )

            self.assertEqual(503, response.status_code)
            self.assertEqual("no-store", response.headers["cache-control"])
            self.assertEqual(
                "잠시 연결이 불안정해요. 조금 뒤에 숲봇을 다시 불러 주세요.", response.text
            )
            log_message = "\n".join(captured.output)
            self.assertIn(f"stage={stage}", log_message)
            self.assertIn("error_code=service_unavailable", log_message)
            self.assertIn("error_type=RuntimeError", log_message)
            for secret in ("detail", secret_body, secret_token, secret_event_id):
                self.assertNotIn(secret, log_message)


if __name__ == "__main__":
    unittest.main()
