"""Secure, stateless HTTP entry point for the Soopbot Vercel function."""

import hashlib
import hmac
import logging
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Security
from fastapi.responses import PlainTextResponse, Response
from fastapi.security import APIKeyHeader

_SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SOURCE_DIRECTORY))

from soopbot.config import Settings, load_bot_token
from soopbot.conversation import Turn
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
    request_guard: MemoryRequestGuard
    reply_service: ReplyService | None = None


def build_runtime(environ: Mapping[str, str] | None = None) -> Runtime:
    """Build settings and local safeguards without initializing OpenAI."""
    settings = Settings.from_environ(environ)
    return Runtime(
        settings=settings,
        request_guard=MemoryRequestGuard(),
    )


def build_reply_service(settings: Settings) -> ReplyService:
    """Build the external provider only after a request is authenticated."""
    return ReplyService(settings, _LazyOpenAIProvider(settings))


class _LazyOpenAIProvider:
    """Initialize the SDK only when a validated question needs generation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider: OpenAIProvider | None = None
        self._lock = threading.Lock()

    def generate(
        self, *, persona: str, question: str, context: tuple[Turn, ...] = ()
    ) -> str:
        if self._provider is None:
            with self._lock:
                if self._provider is None:
                    self._provider = OpenAIProvider(self._settings)
        return self._provider.generate(
            persona=persona, question=question, context=context
        )


class _UnauthorizedRequest(Exception):
    """Signal a failed bot-token check without exposing token details."""


class _UnavailableDependency(Exception):
    """Carry a sanitized service-unavailable stage to the response handler."""

    def __init__(self, stage: str, error: Exception) -> None:
        super().__init__(stage)
        self.stage = stage
        self.error = error


def create_app(
    runtime_provider: Callable[[], Runtime],
    *,
    bot_token_provider: Callable[[], str] = load_bot_token,
    reply_service_provider: Callable[[Settings], ReplyService] = build_reply_service,
) -> FastAPI:
    """Create a testable app whose production runtime is initialized lazily."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    cached_bot_token: str | None = None
    cached_runtime: Runtime | None = None
    cached_reply_service: ReplyService | None = None
    cache_lock = threading.Lock()
    bot_token_header = APIKeyHeader(name="X-Bot-Token", auto_error=False)

    def get_bot_token() -> str:
        nonlocal cached_bot_token
        if cached_bot_token is None:
            with cache_lock:
                if cached_bot_token is None:
                    cached_bot_token = bot_token_provider()
        return cached_bot_token

    def get_runtime() -> Runtime:
        nonlocal cached_runtime
        if cached_runtime is None:
            with cache_lock:
                if cached_runtime is None:
                    cached_runtime = runtime_provider()
        return cached_runtime

    def get_reply_service(runtime: Runtime) -> ReplyService:
        nonlocal cached_reply_service
        if runtime.reply_service is not None:
            return runtime.reply_service
        if cached_reply_service is None:
            with cache_lock:
                if cached_reply_service is None:
                    cached_reply_service = reply_service_provider(runtime.settings)
        return cached_reply_service

    async def authenticated_runtime(
        provided_token: Annotated[str | None, Security(bot_token_header)],
    ) -> Runtime:
        try:
            expected_token = get_bot_token()
        except Exception as error:
            raise _UnavailableDependency("auth", error) from error

        candidate = provided_token or ""
        if not hmac.compare_digest(
            candidate.encode("utf-8"), expected_token.encode("utf-8")
        ):
            raise _UnauthorizedRequest

        try:
            runtime = get_runtime()
        except Exception as error:
            raise _UnavailableDependency("runtime", error) from error
        return runtime

    @app.exception_handler(_UnauthorizedRequest)
    async def unauthorized_response(
        _request: Request, _error: _UnauthorizedRequest
    ) -> PlainTextResponse:
        return PlainTextResponse("unauthorized", status_code=401)

    @app.exception_handler(_UnavailableDependency)
    async def unavailable_dependency_response(
        _request: Request, error: _UnavailableDependency
    ) -> PlainTextResponse:
        return _service_unavailable(error.stage, error.error)

    @app.get("/", response_class=PlainTextResponse)
    @app.get("/api/reply", response_class=PlainTextResponse)
    def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/api/reply")
    async def reply(
        request: Request,
        runtime: Annotated[Runtime, Depends(authenticated_runtime)],
        room: str | None = None,
    ) -> Response:
        if room != runtime.settings.room_key:
            return Response(status_code=204)

        content_type = request.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "text/plain":
            return PlainTextResponse("bad request", status_code=400)

        try:
            body = await _read_limited_body(request)
        except Exception as error:
            return _service_unavailable("body", error)
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
            outcome = get_reply_service(runtime).handle(content)
        except ValueError:
            return PlainTextResponse("bad request", status_code=400)
        except Exception as error:
            return _service_unavailable("reply", error)

        if outcome.kind == "no_trigger":
            return Response(status_code=204)
        return PlainTextResponse(outcome.content)

    return app


async def _read_limited_body(request: Request) -> bytes | None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdecimal():
            return None
        if int(content_length) > _MAX_BODY_BYTES:
            return None

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            return None
        body.extend(chunk)
    return bytes(body)


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
