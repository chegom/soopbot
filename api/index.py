"""Secure, stateless HTTP entry point for the Soopbot Vercel function."""

from dataclasses import dataclass
import hashlib
import hmac
import logging
from pathlib import Path
import sys
import time
from typing import Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response


_SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIRECTORY))

from soopbot.config import Settings
from soopbot.provider import OpenAIProvider
from soopbot.reply import ReplyService
from soopbot.request_guard import MemoryRequestGuard


logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 16_384
_MAX_EVENT_ID_CHARS = 300
_RATE_WINDOW_SECONDS = 60
_DEDUPE_WINDOW_SECONDS = 120
_FALLBACK_EVENT_BUCKET_SECONDS = 15
_SERVICE_UNAVAILABLE_MESSAGE = (
    "잠시 연결이 불안정해요. 조금 뒤에 숲봇을 다시 불러 주세요."
)


@dataclass(frozen=True)
class Runtime:
    """Dependencies that persist for a warm serverless function instance."""

    settings: Settings
    reply_service: ReplyService
    request_guard: MemoryRequestGuard


def build_runtime(environ: Mapping[str, str] | None = None) -> Runtime:
    """Build the production dependencies only when the reply route needs them."""
    settings = Settings.from_environ(environ)
    provider = OpenAIProvider(settings)
    return Runtime(
        settings=settings,
        reply_service=ReplyService(settings, provider),
        request_guard=MemoryRequestGuard(),
    )


def create_app(runtime_provider: Callable[[], Runtime]) -> FastAPI:
    """Create a testable app whose production runtime is initialized lazily."""
    app = FastAPI()
    cached_runtime: Runtime | None = None

    def get_runtime() -> Runtime:
        nonlocal cached_runtime
        if cached_runtime is None:
            cached_runtime = runtime_provider()
        return cached_runtime

    @app.get("/", response_class=PlainTextResponse)
    @app.get("/api/reply", response_class=PlainTextResponse)
    def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/api/reply")
    async def reply(request: Request, room: str | None = None) -> Response:
        try:
            runtime = get_runtime()
        except Exception as error:
            return _service_unavailable("runtime", error)

        provided_token = request.headers.get("x-bot-token", "")
        if not hmac.compare_digest(
            provided_token.encode("utf-8"), runtime.settings.bot_token.encode("utf-8")
        ):
            return PlainTextResponse("unauthorized", status_code=401)

        if room != runtime.settings.room_key:
            return Response(status_code=204)

        content_type = request.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "text/plain":
            return PlainTextResponse("bad request", status_code=400)

        body = await request.body()
        if not body or len(body) > _MAX_BODY_BYTES:
            return PlainTextResponse("bad request", status_code=400)

        event_id = request.headers.get("x-event-id")
        if event_id is not None and len(event_id) > _MAX_EVENT_ID_CHARS:
            return PlainTextResponse("bad request", status_code=400)

        try:
            content = body.decode("utf-8")
        except UnicodeDecodeError:
            return PlainTextResponse("bad request", status_code=400)

        event_key, room_key = _request_keys(room, body, event_id)
        try:
            claim = runtime.request_guard.claim(
                event_key,
                room_key,
                limit=runtime.settings.requests_per_minute,
                rate_window_seconds=_RATE_WINDOW_SECONDS,
                dedupe_window_seconds=_DEDUPE_WINDOW_SECONDS,
            )
        except Exception as error:
            return _service_unavailable("guard", error)

        if claim == "duplicate":
            return Response(status_code=204)
        if claim == "rate_limited":
            return PlainTextResponse(
                "too many requests", status_code=429, headers={"Retry-After": "60"}
            )

        try:
            outcome = runtime.reply_service.handle(content)
        except ValueError:
            return PlainTextResponse("bad request", status_code=400)
        except Exception as error:
            return _service_unavailable("reply", error)

        if outcome.kind == "no_trigger":
            return Response(status_code=204)
        return PlainTextResponse(outcome.content)

    return app


def _request_keys(room: str, body: bytes, event_id: str | None) -> tuple[str, str]:
    room_key = _digest(room.encode("utf-8"))
    body_key = _digest(body)
    identifier = event_id or str(int(time.time() // _FALLBACK_EVENT_BUCKET_SECONDS))
    identifier_key = _digest(identifier.encode("utf-8"))
    event_key = _digest(f"{room_key}:{body_key}:{identifier_key}".encode("ascii"))
    return event_key, room_key


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _service_unavailable(stage: str, error: Exception) -> PlainTextResponse:
    logger.warning(
        "stage=%s error_code=service_unavailable error_type=%s",
        stage,
        type(error).__name__,
    )
    return PlainTextResponse(
        _SERVICE_UNAVAILABLE_MESSAGE,
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


app = create_app(build_runtime)
